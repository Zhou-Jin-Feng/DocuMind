"""Reproducible, bounded acquisition for the DS-02 public snapshots.

The downloader intentionally uses the standard library so acquiring the raw
cache does not depend on the production application or a Hugging Face client.
Dataset-specific structure checks live in ``data_source_validation``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

LOGGER = logging.getLogger("documind.ds02.download")
DEFAULT_MANIFEST = Path("evaluation/data_sources/manifest.json")
DEFAULT_RAW_ROOT = Path("data/evaluation_sources/raw")
DEFAULT_NORMALIZED_ROOT = Path("data/evaluation_sources/normalized")
CHUNK_SIZE = 1024 * 1024


class DownloadError(RuntimeError):
    """A source file could not be downloaded or verified."""


class BudgetError(DownloadError):
    """The configured storage or disk budget would be exceeded."""


class IntegrityError(DownloadError):
    """A downloaded file does not match its pinned manifest metadata."""


@dataclass(frozen=True)
class FileSpec:
    source_id: str
    dataset_id: str
    revision: str
    path: str
    expected_bytes: int
    expected_sha256: str
    kind: str
    split: str | None = None
    rows: int | None = None
    columns: tuple[str, ...] = ()

    @property
    def url(self) -> str:
        dataset_path = quote(self.dataset_id, safe="/")
        relative_path = quote(self.path, safe="/")
        return (
            f"https://huggingface.co/datasets/{dataset_path}/resolve/"
            f"{self.revision}/{relative_path}"
        )


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest must contain a JSON object")
    return manifest


def _as_file_spec(
    source_id: str, dataset_id: str, revision: str, entry: Mapping
) -> FileSpec:
    try:
        expected_bytes = int(entry["bytes"])
        expected_sha256 = str(entry["sha256"]).lower()
        path = str(entry["path"])
        kind = str(entry["kind"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid file entry for {source_id}: {entry!r}") from exc
    try:
        int(expected_sha256, 16)
        int(revision, 16)
    except ValueError as exc:
        raise ValueError(f"invalid revision/hash for {source_id}/{path}") from exc
    if expected_bytes < 0 or len(expected_sha256) != 64 or len(revision) != 40:
        raise ValueError(f"invalid size/hash for {source_id}/{path}")
    return FileSpec(
        source_id=source_id,
        dataset_id=dataset_id,
        revision=revision,
        path=path,
        expected_bytes=expected_bytes,
        expected_sha256=expected_sha256,
        kind=kind,
        split=str(entry["split"]) if entry.get("split") is not None else None,
        rows=int(entry["rows"]) if entry.get("rows") is not None else None,
        columns=tuple(str(value) for value in entry.get("columns", ())),
    )


def iter_file_specs(
    manifest: Mapping, source_ids: Iterable[str] | None = None
) -> list[FileSpec]:
    if not manifest.get("download_authorized"):
        raise ValueError("manifest does not authorize downloads")
    wanted = set(source_ids) if source_ids is not None else None
    authorized = set(manifest.get("download_authorization", {}).get("source_ids", ()))
    specs: list[FileSpec] = []
    for source in manifest.get("sources", ()):
        source_id = str(source.get("id", ""))
        if source_id not in authorized or (
            wanted is not None and source_id not in wanted
        ):
            continue
        artifact = source.get("selected_artifact") or {}
        direct_revision = str(artifact.get("revision", ""))
        direct_dataset = str(artifact.get("dataset_id", ""))
        if direct_dataset and direct_revision and artifact.get("files"):
            for entry in artifact["files"]:
                specs.append(
                    _as_file_spec(source_id, direct_dataset, direct_revision, entry)
                )
        for repository in artifact.get("repositories", ()):
            dataset_id = str(repository["dataset_id"])
            revision = str(repository["revision"])
            for entry in repository.get("files", ()):
                specs.append(_as_file_spec(source_id, dataset_id, revision, entry))
    if wanted is not None:
        unknown = wanted - authorized
        if unknown:
            raise ValueError(f"sources are not authorized for DS-02: {sorted(unknown)}")
    if not specs:
        raise ValueError("no authorized DS-02 files found in manifest")
    return specs


def _safe_relative(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or candidate.drive or ".." in candidate.parts:
        raise ValueError(f"unsafe manifest path: {path!r}")
    return candidate


def destination_for(spec: FileSpec, raw_root: Path) -> Path:
    dataset_slug = spec.dataset_id.replace("/", "__")
    return raw_root / spec.source_id / dataset_slug / _safe_relative(spec.path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(item.stat().st_size for item in root.rglob("*") if item.is_file())


def _check_budget(
    specs: Sequence[FileSpec], raw_root: Path, normalized_root: Path, manifest: Mapping
) -> None:
    budget = manifest.get("budget", {})
    total_limit = int(budget.get("raw_plus_normalized_limit_bytes", 0))
    single_limit = int(budget.get("single_source_limit_bytes", 0))
    minimum_free = int(budget.get("minimum_free_space_bytes", 0))
    expected_by_source: dict[str, int] = {}
    for spec in specs:
        expected_by_source[spec.source_id] = (
            expected_by_source.get(spec.source_id, 0) + spec.expected_bytes
        )
    for source_id, size in expected_by_source.items():
        if single_limit and size > single_limit:
            raise BudgetError(
                f"source {source_id} is {size} bytes, above {single_limit} byte limit"
            )
    current_total = _tree_bytes(raw_root) + _tree_bytes(normalized_root)
    planned_new = sum(
        spec.expected_bytes
        for spec in specs
        if not (destination_for(spec, raw_root).exists())
    )
    if total_limit and current_total + planned_new > total_limit:
        raise BudgetError(
            f"planned cache is {current_total + planned_new} bytes, above {total_limit} byte limit"
        )
    usage = shutil.disk_usage(raw_root.anchor or raw_root.resolve().anchor)
    if minimum_free and usage.free - planned_new < minimum_free:
        raise BudgetError(
            f"free disk after acquisition would be {usage.free - planned_new} bytes, "
            f"below {minimum_free} byte floor"
        )


def _download_once(spec: FileSpec, destination: Path, timeout: float) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")
    existing_size = part.stat().st_size if part.exists() else 0
    if existing_size > spec.expected_bytes:
        part.unlink()
        existing_size = 0
    if existing_size == spec.expected_bytes:
        actual_hash = sha256_file(part)
        if actual_hash == spec.expected_sha256:
            os.replace(part, destination)
            return True
        part.unlink()
        existing_size = 0
    headers = {"User-Agent": "DocuMind-DS02/1.0"}
    if existing_size:
        headers["Range"] = f"bytes={existing_size}-"
    request = Request(spec.url, headers=headers)
    try:
        response = urlopen(request, timeout=timeout)
    except HTTPError as exc:
        raise DownloadError(f"HTTP {exc.code} for {spec.url}") from exc
    except URLError as exc:
        raise DownloadError(f"network error for {spec.url}: {exc.reason}") from exc
    status = getattr(response, "status", response.getcode())
    append = bool(existing_size and status == 206)
    if existing_size and not append:
        part.unlink()
        existing_size = 0
    mode = "ab" if append else "wb"
    written = existing_size
    with response, part.open(mode) as handle:
        while True:
            chunk = response.read(CHUNK_SIZE)
            if not chunk:
                break
            written += len(chunk)
            if written > spec.expected_bytes:
                raise IntegrityError(f"download exceeded expected size for {spec.url}")
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())
    if written != spec.expected_bytes:
        raise IntegrityError(
            f"size mismatch for {spec.path}: got {written}, expected {spec.expected_bytes}"
        )
    actual_hash = sha256_file(part)
    if actual_hash != spec.expected_sha256:
        raise IntegrityError(
            f"sha256 mismatch for {spec.path}: got {actual_hash}, expected {spec.expected_sha256}"
        )
    os.replace(part, destination)
    return True


def acquire(
    manifest: Mapping,
    raw_root: Path = DEFAULT_RAW_ROOT,
    normalized_root: Path = DEFAULT_NORMALIZED_ROOT,
    source_ids: Iterable[str] | None = None,
    retries: int | None = None,
    timeout: float = 60.0,
    sleep_fn=time.sleep,
) -> dict:
    specs = iter_file_specs(manifest, source_ids)
    retry_limit = int(
        retries
        if retries is not None
        else manifest.get("budget", {}).get("automatic_download_attempts", 3)
    )
    if retry_limit < 1:
        raise ValueError("retries must be at least one")
    _check_budget(specs, raw_root, normalized_root, manifest)
    raw_root.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    for spec in specs:
        destination = destination_for(spec, raw_root)
        if destination.exists():
            actual_size = destination.stat().st_size
            actual_hash = sha256_file(destination)
            if (
                actual_size != spec.expected_bytes
                or actual_hash != spec.expected_sha256
            ):
                raise IntegrityError(
                    f"existing file failed integrity check: {destination}"
                )
            records.append(
                {
                    "source_id": spec.source_id,
                    "path": str(destination),
                    "status": "cached",
                    "bytes": actual_size,
                    "sha256": actual_hash,
                }
            )
            continue
        last_error: Exception | None = None
        for attempt in range(1, retry_limit + 1):
            try:
                LOGGER.info(
                    "downloading %s (attempt %s/%s)", spec.url, attempt, retry_limit
                )
                _download_once(spec, destination, timeout)
                last_error = None
                break
            except (DownloadError, OSError) as exc:
                last_error = exc
                if attempt < retry_limit:
                    sleep_fn(float(2 ** (attempt - 1)))
        if last_error is not None:
            raise DownloadError(
                f"failed after {retry_limit} attempts: {spec.url}: {last_error}"
            ) from last_error
        records.append(
            {
                "source_id": spec.source_id,
                "path": str(destination),
                "status": "downloaded",
                "bytes": spec.expected_bytes,
                "sha256": spec.expected_sha256,
            }
        )
    return {
        "schema_version": "p2-ds02-acquisition-v1",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "raw_root": str(raw_root),
        "files": records,
        "total_bytes": sum(int(record["bytes"]) for record in records),
    }


def verify(
    manifest: Mapping,
    raw_root: Path = DEFAULT_RAW_ROOT,
    source_ids: Iterable[str] | None = None,
) -> dict:
    specs = iter_file_specs(manifest, source_ids)
    records: list[dict] = []
    errors: list[str] = []
    for spec in specs:
        destination = destination_for(spec, raw_root)
        if not destination.exists():
            errors.append(f"missing: {destination}")
            continue
        actual_size = destination.stat().st_size
        actual_hash = sha256_file(destination)
        record = {
            "source_id": spec.source_id,
            "path": str(destination),
            "bytes": actual_size,
            "sha256": actual_hash,
            "expected_bytes": spec.expected_bytes,
            "expected_sha256": spec.expected_sha256,
            "ok": actual_size == spec.expected_bytes
            and actual_hash == spec.expected_sha256,
        }
        records.append(record)
        if not record["ok"]:
            errors.append(f"integrity mismatch: {destination}")
    return {
        "schema_version": "p2-ds02-verification-v1",
        "ok": not errors,
        "files": records,
        "errors": errors,
    }


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Acquire and verify pinned DocuMind DS-02 snapshots"
    )
    parser.add_argument("command", choices=("download", "verify"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--normalized-root", type=Path, default=DEFAULT_NORMALIZED_ROOT)
    parser.add_argument("--source", action="append", dest="sources")
    parser.add_argument("--retries", type=int)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        manifest = load_manifest(args.manifest)
        result = (
            acquire(
                manifest,
                args.raw_root,
                args.normalized_root,
                args.sources,
                args.retries,
            )
            if args.command == "download"
            else verify(manifest, args.raw_root, args.sources)
        )
    except (DownloadError, OSError, TypeError, ValueError) as exc:
        print(f"DS-02 acquisition: ERROR\n- {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
