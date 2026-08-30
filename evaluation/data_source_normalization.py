"""Deterministic DS-03 normalization for approved public retrieval snapshots."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from evaluation.data_source_downloader import (
    DEFAULT_MANIFEST,
    DEFAULT_NORMALIZED_ROOT,
    DEFAULT_RAW_ROOT,
    FileSpec,
    destination_for,
    iter_file_specs,
    load_manifest,
    sha256_file,
)

DOCUMENT_SCHEMA_VERSION = "p2-normalized-document-v1"
QUERY_SCHEMA_VERSION = "p2-normalized-query-v1"
QREL_SCHEMA_VERSION = "p2-normalized-qrel-v1"
SNAPSHOT_SCHEMA_VERSION = "p2-normalized-snapshot-v1"
EVIDENCE_SCHEMA_VERSION = "p2-ds03-normalization-evidence-v1"
ADAPTER_VERSION = 1
DEFAULT_CONTRACT_ROOT = Path("evaluation/data_sources/contracts")
_OUTPUT_NAMES = ("documents", "queries", "qrels")


class NormalizationError(RuntimeError):
    """The raw snapshot cannot be converted without violating its contract."""


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON without platform- or insertion-order-dependent bytes."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def stable_normalized_id(
    source_snapshot_id: str, entity_type: str, source_entity_id: str
) -> str:
    if entity_type not in {"document", "query", "qrel"}:
        raise ValueError(f"unsupported normalized entity type: {entity_type}")
    for name, value in (
        ("source_snapshot_id", source_snapshot_id),
        ("source_entity_id", source_entity_id),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a non-empty string")
    digest = canonical_sha256(
        {
            "entity_type": entity_type,
            "source_entity_id": source_entity_id,
            "source_snapshot_id": source_snapshot_id,
        }
    )
    return f"p2n:{entity_type}:{digest}"


def _canonical_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise NormalizationError(f"{field_name} must be a string")
    normalized = value.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        raise NormalizationError(f"{field_name} must not be blank")
    return normalized


def _optional_text(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise NormalizationError(f"{field_name} must be a string")
    return value.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def _write_json_line(handle, digest, record: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(record) + b"\n"
    handle.write(payload)
    digest.update(payload)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2
    )
    path.write_text(payload + "\n", encoding="utf-8", newline="\n")


def _safe_output_relative(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or candidate.drive or ".." in candidate.parts:
        raise NormalizationError(f"unsafe normalized output path: {value!r}")
    return candidate


def _iter_parquet_rows(path: Path, columns: Sequence[str]) -> Iterator[dict[str, Any]]:
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise NormalizationError(
            "pyarrow is required for DS-03 Parquet normalization"
        ) from exc
    parquet_file = parquet.ParquetFile(path)
    missing = sorted(set(columns) - set(parquet_file.schema_arrow.names))
    if missing:
        raise NormalizationError(f"missing columns in {path}: {missing}")
    for batch in parquet_file.iter_batches(batch_size=1024, columns=list(columns)):
        yield from batch.to_pylist()


def _source_manifest(manifest: Mapping[str, Any], source_id: str) -> Mapping[str, Any]:
    matches = [
        source
        for source in manifest.get("sources", ())
        if str(source.get("id", "")) == source_id
    ]
    if len(matches) != 1:
        raise NormalizationError(
            f"manifest must contain exactly one source entry for {source_id}"
        )
    return matches[0]


@dataclass(frozen=True)
class SourceBuildResult:
    source_snapshot_id: str
    adapter: str
    language: str
    authority_state: str
    counts: Mapping[str, int]
    fingerprints: Mapping[str, str]
    input_files: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class _QrelRow:
    source_query_id: str
    source_document_id: str
    relevance_grade: int
    split: str
    dataset_id: str
    revision: str


class PublicRetrievalAdapter:
    """Common adapter for one manifest-pinned public benchmark snapshot."""

    adapter_name = "public-retrieval-v1"
    source_snapshot_id = ""
    language = ""
    authority_state = "official_benchmark"
    default_split: str | None = None

    def __init__(
        self,
        manifest: Mapping[str, Any],
        raw_root: Path,
    ) -> None:
        self.manifest = manifest
        self.raw_root = Path(raw_root)
        self.source = _source_manifest(manifest, self.source_snapshot_id)
        self.specs = tuple(
            sorted(
                iter_file_specs(manifest, [self.source_snapshot_id]),
                key=lambda spec: (spec.kind, spec.dataset_id, spec.path),
            )
        )
        for spec in self.specs:
            path = destination_for(spec, self.raw_root)
            if not path.is_file():
                raise NormalizationError(f"raw manifest file is missing: {path}")
            if (
                path.stat().st_size != spec.expected_bytes
                or sha256_file(path) != spec.expected_sha256
            ):
                raise NormalizationError(
                    f"raw manifest file failed integrity check: {path}"
                )

    def _specs(self, kind: str) -> tuple[FileSpec, ...]:
        specs = tuple(spec for spec in self.specs if spec.kind == kind)
        if not specs:
            raise NormalizationError(
                f"{self.source_snapshot_id} has no manifest-pinned {kind} files"
            )
        return specs

    def _qrel_rows(self) -> list[_QrelRow]:
        rows: list[_QrelRow] = []
        seen_pairs: set[tuple[str, str]] = set()
        for spec in self._specs("qrels"):
            split = spec.split or self.default_split
            if not split:
                raise NormalizationError(
                    f"qrel split is missing for {self.source_snapshot_id}/{spec.path}"
                )
            path = destination_for(spec, self.raw_root)
            if path.suffix.casefold() == ".parquet":
                source_rows: Iterable[Mapping[str, Any]] = _iter_parquet_rows(
                    path, ("query-id", "corpus-id", "score")
                )
            elif path.suffix.casefold() == ".tsv":
                source_rows = self._iter_tsv_qrels(path)
            else:
                raise NormalizationError(f"unsupported qrels format: {path}")
            for row in source_rows:
                query_id = str(row["query-id"])
                document_id = str(row["corpus-id"])
                if not query_id or not document_id:
                    raise NormalizationError(f"blank qrel identity in {path}")
                grade = row["score"]
                if isinstance(grade, bool):
                    raise NormalizationError(f"boolean relevance grade in {path}")
                try:
                    grade = int(grade)
                except (TypeError, ValueError) as exc:
                    raise NormalizationError(
                        f"non-integer relevance grade in {path}"
                    ) from exc
                if not 0 <= grade <= 3:
                    raise NormalizationError(
                        f"relevance grade outside 0-3 in {path}: {grade}"
                    )
                pair = (query_id, document_id)
                if pair in seen_pairs:
                    raise NormalizationError(
                        f"duplicate qrel pair in {self.source_snapshot_id}: {pair}"
                    )
                seen_pairs.add(pair)
                rows.append(
                    _QrelRow(
                        source_query_id=query_id,
                        source_document_id=document_id,
                        relevance_grade=grade,
                        split=split,
                        dataset_id=spec.dataset_id,
                        revision=spec.revision,
                    )
                )
        return rows

    @staticmethod
    def _iter_tsv_qrels(path: Path) -> Iterator[Mapping[str, Any]]:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            required = {"query-id", "corpus-id", "score"}
            if not required <= set(reader.fieldnames or ()):
                raise NormalizationError(f"invalid qrels columns in {path}")
            yield from reader

    def build(self, output_root: Path) -> SourceBuildResult:
        source_root = output_root / self.source_snapshot_id
        source_root.mkdir(parents=True, exist_ok=False)
        qrels = self._qrel_rows()
        query_splits: dict[str, str] = {}
        answerable: dict[str, bool] = defaultdict(bool)
        for row in qrels:
            previous = query_splits.setdefault(row.source_query_id, row.split)
            if previous != row.split:
                raise NormalizationError(
                    f"query appears in multiple splits: {row.source_query_id}"
                )
            answerable[row.source_query_id] |= row.relevance_grade > 0

        document_ids, document_result = self._write_documents(source_root)
        query_ids, query_result = self._write_queries(
            source_root, query_splits, answerable
        )
        qrel_result = self._write_qrels(source_root, qrels, document_ids, query_ids)
        counts = {
            "documents": document_result["count"],
            "queries": query_result["count"],
            "qrels": qrel_result["count"],
        }
        expected = (self.source.get("selected_artifact") or {}).get("counts", {})
        for output_name, manifest_name in (
            ("documents", "corpus"),
            ("queries", "queries"),
            ("qrels", "qrels"),
        ):
            if manifest_name in expected and counts[output_name] != int(
                expected[manifest_name]
            ):
                raise NormalizationError(
                    f"normalized {self.source_snapshot_id}/{output_name} count "
                    f"{counts[output_name]} does not match manifest {expected[manifest_name]}"
                )
        fingerprints = {
            name: result["sha256"]
            for name, result in (
                ("documents", document_result),
                ("queries", query_result),
                ("qrels", qrel_result),
            )
        }
        fingerprints["dataset"] = canonical_sha256(
            {
                "counts": counts,
                "fingerprints": fingerprints,
                "source_snapshot_id": self.source_snapshot_id,
            }
        )
        return SourceBuildResult(
            source_snapshot_id=self.source_snapshot_id,
            adapter=self.adapter_name,
            language=self.language,
            authority_state=self.authority_state,
            counts=counts,
            fingerprints=fingerprints,
            input_files=tuple(self._input_file_records()),
        )

    def _write_documents(self, source_root: Path) -> tuple[set[str], dict[str, Any]]:
        path = source_root / "documents.jsonl"
        digest = hashlib.sha256()
        source_ids: set[str] = set()
        count = 0
        with path.open("wb") as handle:
            for spec in self._specs("corpus"):
                raw_path = destination_for(spec, self.raw_root)
                for row in _iter_parquet_rows(raw_path, ("_id", "title", "text")):
                    source_id = str(row["_id"])
                    if not source_id:
                        raise NormalizationError(
                            f"blank document identity in {raw_path}"
                        )
                    if source_id in source_ids:
                        raise NormalizationError(
                            f"duplicate document ID in {self.source_snapshot_id}: {source_id}"
                        )
                    source_ids.add(source_id)
                    title = _optional_text(row.get("title"), "document.title")
                    text = _canonical_text(row.get("text"), "document.text")
                    record = {
                        "authority_state": self.authority_state,
                        "content_sha256": canonical_sha256(
                            {"text": text, "title": title}
                        ),
                        "id": stable_normalized_id(
                            self.source_snapshot_id, "document", source_id
                        ),
                        "language": self.language,
                        "schema_version": DOCUMENT_SCHEMA_VERSION,
                        "source_dataset": spec.dataset_id,
                        "source_document_id": source_id,
                        "source_revision": spec.revision,
                        "source_snapshot_id": self.source_snapshot_id,
                        "text": text,
                        "title": title,
                    }
                    _write_json_line(handle, digest, record)
                    count += 1
        return source_ids, {"count": count, "sha256": digest.hexdigest()}

    def _write_queries(
        self,
        source_root: Path,
        query_splits: Mapping[str, str],
        answerable: Mapping[str, bool],
    ) -> tuple[set[str], dict[str, Any]]:
        path = source_root / "queries.jsonl"
        digest = hashlib.sha256()
        source_ids: set[str] = set()
        count = 0
        with path.open("wb") as handle:
            for spec in self._specs("queries"):
                raw_path = destination_for(spec, self.raw_root)
                columns = ("_id", "text")
                for row in _iter_parquet_rows(raw_path, columns):
                    source_id = str(row["_id"])
                    if not source_id:
                        raise NormalizationError(f"blank query identity in {raw_path}")
                    if source_id in source_ids:
                        raise NormalizationError(
                            f"duplicate query ID in {self.source_snapshot_id}: {source_id}"
                        )
                    if source_id not in query_splits:
                        raise NormalizationError(
                            f"query has no official qrels split: {source_id}"
                        )
                    source_ids.add(source_id)
                    record = {
                        "answerable": bool(answerable[source_id]),
                        "id": stable_normalized_id(
                            self.source_snapshot_id, "query", source_id
                        ),
                        "primary_category": "public_benchmark",
                        "schema_version": QUERY_SCHEMA_VERSION,
                        "source_dataset": spec.dataset_id,
                        "source_query_id": source_id,
                        "source_revision": spec.revision,
                        "source_snapshot_id": self.source_snapshot_id,
                        "split": query_splits[source_id],
                        "text": _canonical_text(row.get("text"), "query.text"),
                    }
                    _write_json_line(handle, digest, record)
                    count += 1
        if set(query_splits) != source_ids:
            missing = sorted(set(query_splits) - source_ids)[:5]
            raise NormalizationError(f"qrels reference unknown query IDs: {missing}")
        return source_ids, {"count": count, "sha256": digest.hexdigest()}

    def _write_qrels(
        self,
        source_root: Path,
        qrels: Sequence[_QrelRow],
        document_ids: set[str],
        query_ids: set[str],
    ) -> dict[str, Any]:
        path = source_root / "qrels.jsonl"
        digest = hashlib.sha256()
        count = 0
        ordered = sorted(
            qrels,
            key=lambda row: (
                stable_normalized_id(
                    self.source_snapshot_id, "query", row.source_query_id
                ),
                stable_normalized_id(
                    self.source_snapshot_id, "document", row.source_document_id
                ),
            ),
        )
        with path.open("wb") as handle:
            for row in ordered:
                if row.source_query_id not in query_ids:
                    raise NormalizationError(
                        f"qrel references unknown query: {row.source_query_id}"
                    )
                if row.source_document_id not in document_ids:
                    raise NormalizationError(
                        f"qrel references unknown document: {row.source_document_id}"
                    )
                query_id = stable_normalized_id(
                    self.source_snapshot_id, "query", row.source_query_id
                )
                document_id = stable_normalized_id(
                    self.source_snapshot_id, "document", row.source_document_id
                )
                record = {
                    "document_id": document_id,
                    "id": stable_normalized_id(
                        self.source_snapshot_id,
                        "qrel",
                        f"{row.source_query_id}\0{row.source_document_id}",
                    ),
                    "label_provenance": {
                        "method": "official_qrels",
                        "source_dataset": row.dataset_id,
                        "source_document_id": row.source_document_id,
                        "source_query_id": row.source_query_id,
                        "source_revision": row.revision,
                        "source_split": row.split,
                    },
                    "query_id": query_id,
                    "relevance_grade": row.relevance_grade,
                    "schema_version": QREL_SCHEMA_VERSION,
                    "source_snapshot_id": self.source_snapshot_id,
                }
                _write_json_line(handle, digest, record)
                count += 1
        return {"count": count, "sha256": digest.hexdigest()}

    def _input_file_records(self) -> Iterator[Mapping[str, Any]]:
        for spec in self.specs:
            record: dict[str, Any] = {
                "bytes": spec.expected_bytes,
                "dataset_id": spec.dataset_id,
                "kind": spec.kind,
                "path": spec.path,
                "revision": spec.revision,
                "sha256": spec.expected_sha256,
            }
            if spec.split is not None:
                record["split"] = spec.split
            yield record


class T2RankingAdapter(PublicRetrievalAdapter):
    adapter_name = "t2ranking-mteb-dev-v1"
    source_snapshot_id = "t2ranking-mteb-dev"
    language = "cmn-Hans"
    default_split = "dev"


class NFCorpusAdapter(PublicRetrievalAdapter):
    adapter_name = "beir-nfcorpus-v1"
    source_snapshot_id = "beir-nfcorpus"
    language = "en"


class SciFactAdapter(PublicRetrievalAdapter):
    adapter_name = "beir-scifact-v1"
    source_snapshot_id = "beir-scifact"
    language = "en"


ADAPTERS = {
    adapter.source_snapshot_id: adapter
    for adapter in (T2RankingAdapter, NFCorpusAdapter, SciFactAdapter)
}


def _conversion_configuration() -> dict[str, Any]:
    return {
        "adapter_version": ADAPTER_VERSION,
        "canonical_serialization": "utf8-canonical-json-sort-keys-compact-lf-v1",
        "qrel_grade_policy": "preserve-official-integer-0-3",
        "record_schema_versions": {
            "documents": DOCUMENT_SCHEMA_VERSION,
            "qrels": QREL_SCHEMA_VERSION,
            "queries": QUERY_SCHEMA_VERSION,
        },
        "stable_id_algorithm": "sha256-canonical-source-snapshot-entity-source-id-v1",
        "text_policy": "preserve-source-text-normalize-bom-and-line-endings-v1",
    }


def _snapshot(
    manifest: Mapping[str, Any],
    manifest_sha256: str,
    results: Sequence[SourceBuildResult],
) -> dict[str, Any]:
    by_source_counts = [
        {"source_snapshot_id": result.source_snapshot_id, **result.counts}
        for result in results
    ]
    total_counts = {
        name: sum(result.counts[name] for result in results) for name in _OUTPUT_NAMES
    }
    by_source_fingerprints = [
        {"source_snapshot_id": result.source_snapshot_id, **result.fingerprints}
        for result in results
    ]
    aggregate_fingerprints = {
        name: canonical_sha256(
            [
                {
                    "sha256": result.fingerprints[name],
                    "source_snapshot_id": result.source_snapshot_id,
                }
                for result in results
            ]
        )
        for name in _OUTPUT_NAMES
    }
    conversion = _conversion_configuration()
    dataset_fingerprint = canonical_sha256(
        {
            "conversion_configuration": conversion,
            "counts": total_counts,
            "manifest_sha256": manifest_sha256,
            "sources": by_source_fingerprints,
        }
    )
    source_manifests = []
    for result in results:
        source_manifests.append(
            {
                "adapter": result.adapter,
                "adapter_version": ADAPTER_VERSION,
                "authority_state": result.authority_state,
                "input_files": list(result.input_files),
                "language": result.language,
                "outputs": {
                    name: {
                        "count": result.counts[name],
                        "path": f"{result.source_snapshot_id}/{name}.jsonl",
                        "sha256": result.fingerprints[name],
                    }
                    for name in _OUTPUT_NAMES
                },
                "source_snapshot_id": result.source_snapshot_id,
            }
        )
    return {
        "conversion_configuration": conversion,
        "counts": {**total_counts, "by_source": by_source_counts},
        "manifest_schema_version": str(manifest.get("schema_version", "")),
        "manifest_sha256": manifest_sha256,
        "normalized_fingerprints": {
            **aggregate_fingerprints,
            "by_source": by_source_fingerprints,
            "dataset_sha256": dataset_fingerprint,
        },
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source_manifests": source_manifests,
    }


def _guard_output_root(output_root: Path, raw_root: Path, replace: bool) -> None:
    resolved = output_root.resolve()
    prohibited = {
        Path.cwd().resolve(),
        raw_root.resolve(),
        raw_root.resolve().parent,
        Path(resolved.anchor),
    }
    if resolved in prohibited:
        raise NormalizationError(f"unsafe normalized output root: {output_root}")
    if not output_root.exists():
        return
    if not output_root.is_dir():
        raise NormalizationError(
            f"normalized output root is not a directory: {output_root}"
        )
    if not any(output_root.iterdir()):
        return
    if not replace:
        raise FileExistsError(
            f"normalized output is not empty; pass replace=True: {output_root}"
        )
    marker = output_root / "snapshot.json"
    try:
        marker_payload = json.loads(marker.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        raise NormalizationError(
            f"refusing to replace unowned normalized output root: {output_root}"
        ) from exc
    if marker_payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise NormalizationError(
            f"refusing to replace unowned normalized output root: {output_root}"
        )


def _publish_directory(
    staging: Path, output_root: Path, raw_root: Path, replace: bool
) -> None:
    _guard_output_root(output_root, raw_root, replace)
    backup: Path | None = None
    try:
        if output_root.exists():
            backup = output_root.with_name(f".{output_root.name}.backup-{os.getpid()}")
            if backup.exists():
                raise FileExistsError(f"normalization backup already exists: {backup}")
            output_root.replace(backup)
        staging.replace(output_root)
    except BaseException:
        if backup is not None and backup.exists() and not output_root.exists():
            backup.replace(output_root)
        raise
    else:
        if backup is not None:
            shutil.rmtree(backup)


def build_normalized_snapshot(
    manifest: Mapping[str, Any],
    raw_root: Path = DEFAULT_RAW_ROOT,
    output_root: Path = DEFAULT_NORMALIZED_ROOT,
    *,
    manifest_sha256: str,
    source_ids: Sequence[str] | None = None,
    replace: bool = False,
) -> dict[str, Any]:
    selected = list(source_ids or ADAPTERS)
    unknown = sorted(set(selected) - set(ADAPTERS))
    if unknown:
        raise ValueError(f"no DS-03 adapter exists for sources: {unknown}")
    if len(selected) != len(set(selected)):
        raise ValueError("DS-03 source selection contains duplicates")
    output_root = Path(output_root)
    raw_root = Path(raw_root)
    _guard_output_root(output_root, raw_root, replace)
    output_parent = output_root.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.staging-", dir=output_parent)
    )
    try:
        results = [
            ADAPTERS[source_id](manifest, raw_root).build(staging)
            for source_id in selected
        ]
        snapshot = _snapshot(manifest, manifest_sha256, results)
        _write_json(staging / "snapshot.json", snapshot)
        snapshot_sha256 = sha256_file(staging / "snapshot.json")
        _publish_directory(staging, output_root, raw_root, replace)
        return {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "snapshot": snapshot,
            "snapshot_file_sha256": snapshot_sha256,
        }
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def validate_normalized_snapshot(
    output_root: Path,
    contract_root: Path = DEFAULT_CONTRACT_ROOT,
) -> dict[str, Any]:
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import ValidationError
    except ImportError as exc:
        raise NormalizationError(
            "jsonschema is required for DS-03 normalized validation"
        ) from exc
    output_root = Path(output_root)
    snapshot = json.loads((output_root / "snapshot.json").read_text(encoding="utf-8"))
    schemas = {
        name: json.loads(
            (Path(contract_root) / f"{name}-v1.schema.json").read_text(encoding="utf-8")
        )
        for name in (*_OUTPUT_NAMES, "snapshot")
    }
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
    Draft202012Validator(schemas["snapshot"]).validate(snapshot)
    counts = {name: 0 for name in _OUTPUT_NAMES}
    errors: list[str] = []
    source_count_records: list[dict[str, Any]] = []
    source_fingerprint_records: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    seen_output_paths: set[Path] = set()
    for source in snapshot["source_manifests"]:
        source_id = source["source_snapshot_id"]
        if source_id in seen_sources:
            errors.append(f"duplicate source snapshot: {source_id}")
        seen_sources.add(source_id)
        source_counts = {name: 0 for name in _OUTPUT_NAMES}
        source_hashes: dict[str, str] = {}
        record_ids = {name: set() for name in _OUTPUT_NAMES}
        qrel_pairs: set[tuple[str, str]] = set()
        for name in _OUTPUT_NAMES:
            output = source["outputs"][name]
            relative_path = _safe_output_relative(str(output["path"]))
            if relative_path.parts[0] != source_id:
                errors.append(
                    f"output source path mismatch: {source_id}/{output['path']}"
                )
            if relative_path in seen_output_paths:
                errors.append(f"duplicate normalized output path: {output['path']}")
            seen_output_paths.add(relative_path)
            path = output_root / relative_path
            actual_hash = sha256_file(path)
            source_hashes[name] = actual_hash
            if actual_hash != output["sha256"]:
                errors.append(f"fingerprint mismatch: {output['path']}")
            validator = Draft202012Validator(schemas[name])
            line_count = 0
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    try:
                        record = json.loads(line)
                        validator.validate(record)
                    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                        errors.append(
                            f"schema error: {output['path']}:{line_number}: {exc}"
                        )
                        break
                    line_count += 1
                    if record["source_snapshot_id"] != source_id:
                        errors.append(
                            f"record source mismatch: {output['path']}:{line_number}"
                        )
                    if record["id"] in record_ids[name]:
                        errors.append(f"duplicate normalized {name} ID: {record['id']}")
                    record_ids[name].add(record["id"])
                    if name == "documents":
                        expected_id = stable_normalized_id(
                            source_id, "document", record["source_document_id"]
                        )
                        if record["id"] != expected_id:
                            errors.append(
                                f"unstable document ID: {output['path']}:{line_number}"
                            )
                        if "text" in record:
                            expected_content_hash = canonical_sha256(
                                {"text": record["text"], "title": record["title"]}
                            )
                            if record["content_sha256"] != expected_content_hash:
                                errors.append(
                                    f"document content hash mismatch: "
                                    f"{output['path']}:{line_number}"
                                )
                    elif name == "queries":
                        expected_id = stable_normalized_id(
                            source_id, "query", record["source_query_id"]
                        )
                        if record["id"] != expected_id:
                            errors.append(
                                f"unstable query ID: {output['path']}:{line_number}"
                            )
                    else:
                        pair = (record["query_id"], record["document_id"])
                        if pair in qrel_pairs:
                            errors.append(f"duplicate normalized qrel pair: {pair}")
                        qrel_pairs.add(pair)
                        if record["query_id"] not in record_ids["queries"]:
                            errors.append(
                                f"qrel references unknown query: {record['query_id']}"
                            )
                        if record["document_id"] not in record_ids["documents"]:
                            errors.append(
                                f"qrel references unknown document: {record['document_id']}"
                            )
                        provenance = record["label_provenance"]
                        expected_query_id = stable_normalized_id(
                            source_id, "query", provenance["source_query_id"]
                        )
                        expected_document_id = stable_normalized_id(
                            source_id, "document", provenance["source_document_id"]
                        )
                        expected_qrel_id = stable_normalized_id(
                            source_id,
                            "qrel",
                            f"{provenance['source_query_id']}\0"
                            f"{provenance['source_document_id']}",
                        )
                        if (
                            record["query_id"] != expected_query_id
                            or record["document_id"] != expected_document_id
                            or record["id"] != expected_qrel_id
                        ):
                            errors.append(
                                f"qrel provenance identity mismatch: "
                                f"{output['path']}:{line_number}"
                            )
            if line_count != output["count"]:
                errors.append(
                    f"count mismatch: {source_id}/{name}: "
                    f"{line_count} != {output['count']}"
                )
            counts[name] += line_count
            source_counts[name] = line_count
        source_count_records.append({"source_snapshot_id": source_id, **source_counts})
        source_fingerprints = {name: source_hashes[name] for name in _OUTPUT_NAMES}
        source_fingerprints["dataset"] = canonical_sha256(
            {
                "counts": source_counts,
                "fingerprints": source_fingerprints,
                "source_snapshot_id": source_id,
            }
        )
        source_fingerprint_records.append(
            {"source_snapshot_id": source_id, **source_fingerprints}
        )
    for name in _OUTPUT_NAMES:
        if counts[name] != snapshot["counts"][name]:
            errors.append(
                f"aggregate count mismatch: {name}: "
                f"{counts[name]} != {snapshot['counts'][name]}"
            )
    if source_count_records != snapshot["counts"]["by_source"]:
        errors.append("per-source normalized counts do not match snapshot")
    fingerprints = snapshot["normalized_fingerprints"]
    if source_fingerprint_records != fingerprints["by_source"]:
        errors.append("per-source normalized fingerprints do not match snapshot")
    for name in _OUTPUT_NAMES:
        aggregate_hash = canonical_sha256(
            [
                {
                    "sha256": source[name],
                    "source_snapshot_id": source["source_snapshot_id"],
                }
                for source in source_fingerprint_records
            ]
        )
        if aggregate_hash != fingerprints[name]:
            errors.append(f"aggregate {name} fingerprint mismatch")
    dataset_hash = canonical_sha256(
        {
            "conversion_configuration": snapshot["conversion_configuration"],
            "counts": counts,
            "manifest_sha256": snapshot["manifest_sha256"],
            "sources": source_fingerprint_records,
        }
    )
    if dataset_hash != fingerprints["dataset_sha256"]:
        errors.append("aggregate dataset fingerprint mismatch")
    return {"counts": counts, "errors": errors, "ok": not errors}


def render_markdown(evidence: Mapping[str, Any]) -> str:
    snapshot = evidence["snapshot"]
    lines = [
        "# P2 DS-03 Normalization Evidence",
        "",
        f"- Schema: `{snapshot['schema_version']}`",
        f"- Manifest SHA-256: `{snapshot['manifest_sha256']}`",
        f"- Snapshot file SHA-256: `{evidence['snapshot_file_sha256']}`",
        f"- Dataset SHA-256: `{snapshot['normalized_fingerprints']['dataset_sha256']}`",
        "",
        "## Counts And Fingerprints",
        "",
        "| Source | Documents | Queries | Qrels | Dataset SHA-256 |",
        "|---|---:|---:|---:|---|",
    ]
    counts = {
        item["source_snapshot_id"]: item for item in snapshot["counts"]["by_source"]
    }
    fingerprints = {
        item["source_snapshot_id"]: item
        for item in snapshot["normalized_fingerprints"]["by_source"]
    }
    for source in snapshot["source_manifests"]:
        source_id = source["source_snapshot_id"]
        source_counts = counts[source_id]
        lines.append(
            f"| `{source_id}` | {source_counts['documents']} | "
            f"{source_counts['queries']} | {source_counts['qrels']} | "
            f"`{fingerprints[source_id]['dataset']}` |"
        )
    totals = snapshot["counts"]
    lines.extend(
        [
            f"| **Total** | **{totals['documents']}** | **{totals['queries']}** | "
            f"**{totals['qrels']}** | - |",
            "",
            "## Boundary",
            "",
            "This report records deterministic local normalization only. Raw and normalized text remains Git-ignored. No Embedding, Milvus indexing, model call, public API change or candidate rollout is authorized by this evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "validate"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_NORMALIZED_ROOT)
    parser.add_argument("--contract-root", type=Path, default=DEFAULT_CONTRACT_ROOT)
    parser.add_argument("--source", action="append", dest="sources")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--report-markdown", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "build":
            manifest = load_manifest(args.manifest)
            evidence = build_normalized_snapshot(
                manifest,
                args.raw_root,
                args.output_root,
                manifest_sha256=sha256_file(args.manifest),
                source_ids=args.sources,
                replace=args.replace,
            )
            validation = validate_normalized_snapshot(
                args.output_root, args.contract_root
            )
            if not validation["ok"]:
                raise NormalizationError(
                    f"normalized validation failed: {validation['errors']}"
                )
            evidence["validation"] = validation
            if args.report_json:
                args.report_json.parent.mkdir(parents=True, exist_ok=True)
                _write_json(args.report_json, evidence)
            if args.report_markdown:
                args.report_markdown.parent.mkdir(parents=True, exist_ok=True)
                args.report_markdown.write_text(
                    render_markdown(evidence), encoding="utf-8", newline="\n"
                )
            result = evidence
        else:
            result = validate_normalized_snapshot(args.output_root, args.contract_root)
    except (
        FileNotFoundError,
        NormalizationError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"DS-03 normalization: ERROR\n- {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", result.get("validation", {}).get("ok", True)) else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
