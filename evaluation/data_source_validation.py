"""Structure validation and bounded throughput pilots for DS-02 data."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.request import Request, urlopen

from evaluation.data_source_downloader import (
    DEFAULT_MANIFEST,
    DEFAULT_RAW_ROOT,
    FileSpec,
    destination_for,
    iter_file_specs,
    load_manifest,
    sha256_file,
)

MIRACL_ZH_PASSAGES = 4_934_368
EMBEDDING_DIMENSIONS = 4096
FLOAT32_BYTES = 4


class StructureError(RuntimeError):
    """Raw source structure does not match the pinned contract."""


def _runtime_policy(manifest: Mapping) -> tuple[float, float]:
    budget = manifest.get("budget", {})
    hard_limit = float(budget["maximum_end_to_end_runtime_hours"])
    launch_limit = float(budget["maximum_launch_projection_hours"])
    if launch_limit <= 0 or hard_limit <= 0 or launch_limit > hard_limit:
        raise ValueError(
            "runtime policy requires 0 < maximum_launch_projection_hours "
            "<= maximum_end_to_end_runtime_hours"
        )
    return launch_limit, hard_limit


def _validate_tsv(spec: FileSpec, path: Path) -> dict:
    started = time.perf_counter()
    rows = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        columns = tuple(reader.fieldnames or ())
        for row in reader:
            rows += 1
            if spec.kind == "qrels":
                if not row.get("query-id") or not row.get("corpus-id"):
                    raise StructureError(f"blank qrel identity in {path}")
                int(row["score"])
    elapsed = time.perf_counter() - started
    return {
        "format": "tsv",
        "rows": rows,
        "columns": list(columns),
        "scan_seconds": elapsed,
    }


def _validate_parquet(spec: FileSpec, path: Path) -> dict:
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise StructureError(
            "pyarrow is required for DS-02 Parquet validation"
        ) from exc
    started = time.perf_counter()
    parquet_file = parquet.ParquetFile(path)
    rows = int(parquet_file.metadata.num_rows)
    columns = tuple(parquet_file.schema_arrow.names)
    sample_columns = [column for column in spec.columns if column in columns]
    sample_batch = next(
        parquet_file.iter_batches(batch_size=20, columns=sample_columns), None
    )
    if sample_batch is None:
        raise StructureError(f"empty Parquet file: {path}")
    sample = sample_batch.to_pydict()
    if spec.kind in {"corpus", "queries"}:
        identifiers = sample.get("_id", ())
        texts = sample.get("text", ())
        if (
            not identifiers
            or not texts
            or any(not str(value).strip() for value in identifiers)
        ):
            raise StructureError(f"missing sample identifiers/text in {path}")
        if any(not str(value).strip() for value in texts):
            raise StructureError(f"blank sample text in {path}")
    elapsed = time.perf_counter() - started
    return {
        "format": "parquet",
        "rows": rows,
        "columns": list(columns),
        "row_groups": parquet_file.num_row_groups,
        "sample_rows_read": max((len(values) for values in sample.values()), default=0),
        "scan_seconds": elapsed,
    }


def validate_structures(manifest: Mapping, raw_root: Path = DEFAULT_RAW_ROOT) -> dict:
    specs = iter_file_specs(manifest)
    records: list[dict] = []
    aggregate: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    errors: list[str] = []
    for spec in specs:
        path = destination_for(spec, raw_root)
        try:
            if not path.exists():
                raise StructureError(f"missing file: {path}")
            actual_size = path.stat().st_size
            actual_hash = sha256_file(path)
            if (
                actual_size != spec.expected_bytes
                or actual_hash != spec.expected_sha256
            ):
                raise StructureError(
                    f"integrity mismatch in {path}: got {actual_size} bytes/{actual_hash}, "
                    f"expected {spec.expected_bytes} bytes/{spec.expected_sha256}"
                )
            if path.suffix.lower() == ".parquet":
                result = _validate_parquet(spec, path)
            elif path.suffix.lower() == ".tsv":
                result = _validate_tsv(spec, path)
            else:
                raise StructureError(f"unsupported DS-02 file type: {path.suffix}")
            missing_columns = sorted(set(spec.columns) - set(result["columns"]))
            if missing_columns:
                raise StructureError(f"missing columns in {path}: {missing_columns}")
            if spec.rows is not None and result["rows"] != spec.rows:
                raise StructureError(
                    f"row mismatch in {path}: got {result['rows']}, expected {spec.rows}"
                )
            aggregate[spec.source_id][spec.kind] += int(result["rows"])
            records.append(
                {
                    "source_id": spec.source_id,
                    "dataset_id": spec.dataset_id,
                    "revision": spec.revision,
                    "path": spec.path,
                    "bytes": actual_size,
                    "sha256": actual_hash,
                    "ok": True,
                    **result,
                }
            )
        except (OSError, TypeError, ValueError, StructureError) as exc:
            errors.append(str(exc))
            records.append(
                {
                    "source_id": spec.source_id,
                    "dataset_id": spec.dataset_id,
                    "revision": spec.revision,
                    "path": spec.path,
                    "ok": False,
                    "error": str(exc),
                }
            )
    sources_by_id = {
        str(source["id"]): source for source in manifest.get("sources", ())
    }
    aggregate_records: dict[str, dict[str, int]] = {}
    for source_id, kinds in aggregate.items():
        actual = dict(kinds)
        aggregate_records[source_id] = actual
        expected = (sources_by_id[source_id].get("selected_artifact") or {}).get(
            "counts", {}
        )
        for kind in ("corpus", "queries", "qrels"):
            if kind in expected and actual.get(kind, 0) != int(expected[kind]):
                errors.append(
                    f"aggregate {source_id}/{kind}: got {actual.get(kind, 0)}, expected {expected[kind]}"
                )
    return {
        "schema_version": "p2-ds02-structure-v1",
        "ok": not errors,
        "files": records,
        "aggregate_rows": aggregate_records,
        "errors": errors,
    }


def _read_corpus_samples(
    specs: Iterable[FileSpec], raw_root: Path, per_source_rows: int
) -> tuple[dict, list[tuple[str, str]]]:
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise StructureError("pyarrow is required for the DS-02 read pilot") from exc
    by_source: dict[str, int] = defaultdict(int)
    samples: list[tuple[str, str]] = []
    rows = 0
    characters = 0
    started = time.perf_counter()
    for spec in specs:
        if spec.kind != "corpus" or not spec.path.endswith(".parquet"):
            continue
        remaining = per_source_rows - by_source[spec.source_id]
        if remaining <= 0:
            continue
        parquet_file = parquet.ParquetFile(destination_for(spec, raw_root))
        for batch in parquet_file.iter_batches(
            batch_size=min(256, remaining), columns=["title", "text"]
        ):
            values = batch.to_pydict()
            titles = values.get("title", [""] * batch.num_rows)
            bodies = values["text"]
            for title, body in zip(titles, bodies):
                text = f"{title or ''}\n{body or ''}".strip()
                samples.append((spec.source_id, text))
                rows += 1
                by_source[spec.source_id] += 1
                characters += len(text)
                remaining -= 1
                if remaining == 0:
                    break
            if remaining == 0:
                break
    elapsed = time.perf_counter() - started
    return (
        {
            "rows": rows,
            "characters": characters,
            "seconds": elapsed,
            "rows_per_second": rows / elapsed if elapsed else None,
            "characters_per_second": characters / elapsed if elapsed else None,
            "rows_by_source": dict(by_source),
        },
        samples,
    )


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("cannot calculate a percentile of an empty sequence")
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def run_ollama_embedding_pilot(
    texts: Sequence[str],
    sample_size: int,
    batch_size: int,
    model: str,
    base_url: str,
    timeout: float = 180.0,
) -> dict:
    if sample_size < 1 or batch_size < 1:
        raise ValueError("embedding sample and batch sizes must be positive")
    sample = list(texts[:sample_size])
    if len(sample) < sample_size:
        raise ValueError(
            f"only {len(sample)} corpus samples available, requested {sample_size}"
        )

    def embed(batch: Sequence[str]) -> tuple[int, float]:
        payload = json.dumps(
            {"model": model, "input": list(batch), "truncate": True}
        ).encode("utf-8")
        request = Request(
            base_url.rstrip("/") + "/api/embed",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "DocuMind-DS02/1.0",
            },
            method="POST",
        )
        started = time.perf_counter()
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        elapsed = time.perf_counter() - started
        vectors = body.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(batch):
            raise RuntimeError("Ollama returned an invalid embedding batch")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise RuntimeError("Ollama returned inconsistent embedding dimensions")
        return dimensions.pop(), elapsed

    dimension, warmup_seconds = embed(sample[:1])
    latencies: list[float] = []
    measured = 0
    characters = 0
    for offset in range(0, len(sample), batch_size):
        batch = sample[offset : offset + batch_size]
        batch_dimension, elapsed = embed(batch)
        if batch_dimension != dimension:
            raise RuntimeError("embedding dimension changed during pilot")
        latencies.append(elapsed)
        measured += len(batch)
        characters += sum(len(text) for text in batch)
    total_seconds = sum(latencies)
    documents_per_second = measured / total_seconds if total_seconds else None
    projected_hours = (
        MIRACL_ZH_PASSAGES / documents_per_second / 3600
        if documents_per_second
        else None
    )
    return {
        "provider": "ollama",
        "model": model,
        "dimension": dimension,
        "sample_size": measured,
        "batch_size": batch_size,
        "measurement_batches": len(latencies),
        "sample_characters": characters,
        "warmup_seconds": warmup_seconds,
        "measured_seconds": total_seconds,
        "documents_per_second": documents_per_second,
        "characters_per_second": characters / total_seconds if total_seconds else None,
        "batch_latency_p50_seconds": _percentile(latencies, 0.5),
        "batch_latency_p95_seconds": _percentile(latencies, 0.95),
        "miracl_passage_count": MIRACL_ZH_PASSAGES,
        "miracl_embedding_only_projection_hours": projected_hours,
        "projection_limitations": "Directional estimate only; excludes Milvus writes/indexing, WAL, retries and MIRACL length-distribution differences.",
    }


def build_evidence(
    manifest: Mapping,
    raw_root: Path,
    read_rows_per_source: int,
    embedding_sample_size: int,
    embedding_batch_size: int,
    ollama_model: str,
    ollama_url: str,
) -> dict:
    if read_rows_per_source < 1:
        raise ValueError("read_rows_per_source must be positive")
    structure = validate_structures(manifest, raw_root)
    if not structure["ok"]:
        raise StructureError("; ".join(structure["errors"]))
    specs = iter_file_specs(manifest)
    read_pilot, samples = _read_corpus_samples(specs, raw_root, read_rows_per_source)
    embedding_samples = samples[:embedding_sample_size]
    embedding = (
        run_ollama_embedding_pilot(
            [text for _, text in embedding_samples],
            embedding_sample_size,
            embedding_batch_size,
            ollama_model,
            ollama_url,
        )
        if embedding_sample_size
        else None
    )
    if embedding:
        source_counts: dict[str, int] = defaultdict(int)
        for source_id, _ in embedding_samples:
            source_counts[source_id] += 1
        embedding["sample_source_counts"] = dict(source_counts)
    files = structure["files"]
    disk_free_bytes = shutil.disk_usage(raw_root.resolve().anchor).free
    miracl_source = next(
        source for source in manifest["sources"] if source["id"] == "miracl-zh-dev"
    )
    miracl_download_bytes = int(miracl_source["selected_artifact"]["download_bytes"])
    raw_vector_bytes = MIRACL_ZH_PASSAGES * EMBEDDING_DIMENSIONS * FLOAT32_BYTES
    minimum_free_bytes = int(manifest["budget"]["minimum_free_space_bytes"])
    launch_limit_hours, hard_limit_hours = _runtime_policy(manifest)
    projected_free_bytes = disk_free_bytes - miracl_download_bytes - raw_vector_bytes
    embedding_projection_hours = (
        embedding.get("miracl_embedding_only_projection_hours") if embedding else None
    )
    meets_launch_limit = bool(
        embedding_projection_hours is not None
        and embedding_projection_hours <= launch_limit_hours
    )
    meets_hard_limit = bool(
        embedding_projection_hours is not None
        and embedding_projection_hours <= hard_limit_hours
    )
    license_status = "UNRESOLVED_CONFLICT"
    meets_disk_floor = projected_free_bytes >= minimum_free_bytes
    miracl_assessment = {
        "decision": "DEFER_FULL_DOWNLOAD",
        "raw_snapshot_bytes": miracl_download_bytes,
        "raw_float32_vector_bytes": raw_vector_bytes,
        "disk_free_bytes": disk_free_bytes,
        "minimum_free_space_bytes": minimum_free_bytes,
        "projected_free_after_raw_and_vectors_bytes": projected_free_bytes,
        "meets_disk_floor_before_milvus_overhead": meets_disk_floor,
        "maximum_launch_projection_hours": launch_limit_hours,
        "maximum_end_to_end_runtime_hours": hard_limit_hours,
        "embedding_only_projection_hours": embedding_projection_hours,
        "meets_launch_projection_limit": meets_launch_limit,
        "meets_end_to_end_runtime_limit": meets_hard_limit,
        "eligible_to_start": bool(
            meets_disk_floor
            and meets_launch_limit
            and meets_hard_limit
            and license_status == "RESOLVED"
        ),
        "license_status": license_status,
        "reopen_conditions": [
            "Resolve Apache-2.0 versus CC-BY-SA-4.0 provenance and redistribution terms.",
            "Freeze a deterministic subset or hard-negative protocol that does not require full-corpus Dense indexing.",
            "Project no more than 18 hours before launch and complete end-to-end within 24 hours.",
            "Keep projected free disk above the 120 GiB floor including Milvus index, WAL and temporary files.",
        ],
    }
    return {
        "schema_version": "p2-ds02-evidence-v1",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "manifest_schema_version": manifest["schema_version"],
        "authorized_source_ids": list(manifest["download_authorization"]["source_ids"]),
        "file_count": len(files),
        "total_bytes": sum(
            destination_for(spec, raw_root).stat().st_size for spec in specs
        ),
        "all_hashes_match": True,
        "structure": structure,
        "read_pilot": read_pilot,
        "embedding_pilot": embedding,
        "runtime_policy": {
            "maximum_launch_projection_hours": launch_limit_hours,
            "maximum_end_to_end_runtime_hours": hard_limit_hours,
            "rule": "Do not start when projected end-to-end runtime exceeds 18 hours; abort by 24 hours.",
        },
        "miracl_assessment": miracl_assessment,
    }


def render_markdown(evidence: Mapping) -> str:
    embedding = evidence.get("embedding_pilot")
    miracl = evidence["miracl_assessment"]
    projection = miracl.get("embedding_only_projection_hours")
    projection_text = (
        "not measured" if projection is None else f"{projection:.1f} hours"
    )
    lines = [
        "# DS-02 Acquisition Evidence",
        "",
        f"- Status: `{'PASS' if evidence.get('all_hashes_match') and evidence.get('structure', {}).get('ok') else 'FAIL'}`",
        f"- Files: `{evidence['file_count']}`",
        f"- Bytes: `{evidence['total_bytes']}`",
        f"- Sources: `{', '.join(evidence['authorized_source_ids'])}`",
        "",
        "## Structure",
        "",
        "| Source | Corpus rows | Query rows | Qrel rows |",
        "|---|---:|---:|---:|",
    ]
    for source_id, counts in evidence["structure"]["aggregate_rows"].items():
        lines.append(
            f"| `{source_id}` | {counts.get('corpus', 0)} | {counts.get('queries', 0)} | {counts.get('qrels', 0)} |"
        )
    read = evidence["read_pilot"]
    lines.extend(
        [
            "",
            "## Bounded Pilots",
            "",
            f"- Parquet sample read: `{read['rows']}` rows in `{read['seconds']:.4f}` s (`{read['rows_per_second']:.1f}` rows/s).",
        ]
    )
    if embedding:
        lines.extend(
            [
                f"- Ollama embedding: `{embedding['sample_size']}` passages, batch `{embedding['batch_size']}`, dimension `{embedding['dimension']}`.",
                f"- Embedding sample sources: `{embedding['sample_source_counts']}`; measured batches: `{embedding['measurement_batches']}`.",
                f"- Warmed measured throughput: `{embedding['documents_per_second']:.2f}` passages/s; batch P95 `{embedding['batch_latency_p95_seconds']:.3f}` s.",
                f"- MIRACL embedding-only directional projection: `{embedding['miracl_embedding_only_projection_hours']:.1f}` hours.",
                "- Projection excludes vector-store writes/indexing, WAL, retries and dataset length-distribution differences.",
            ]
        )
    lines.extend(
        [
            "",
            "## MIRACL Decision",
            "",
            f"- Decision: `{miracl['decision']}`.",
            f"- Raw float32 vectors alone: `{miracl['raw_float32_vector_bytes']}` bytes; projected free disk after raw snapshot and vectors: `{miracl['projected_free_after_raw_and_vectors_bytes']}` bytes.",
            f"- Meets the 120 GiB floor before Milvus overhead: `{str(miracl['meets_disk_floor_before_milvus_overhead']).lower()}`.",
            f"- Meets the 18-hour launch projection limit: `{str(miracl['meets_launch_projection_limit']).lower()}` (embedding-only projection: `{projection_text}`).",
            f"- Meets the 24-hour end-to-end hard limit: `{str(miracl['meets_end_to_end_runtime_limit']).lower()}`.",
            f"- Eligible to start: `{str(miracl['eligible_to_start']).lower()}`.",
            f"- License status: `{miracl['license_status']}`.",
            "- Reopen only after license provenance is resolved and DS-03 freezes a deterministic subset or hard-negative protocol that avoids full-corpus Dense indexing.",
        ]
    )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This evidence validates acquisition, file integrity, raw schema and a bounded local pilot. It does not authorize MIRACL acquisition, full-corpus embedding, public API changes or a retrieval-candidate rollout.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Validate DS-02 snapshots and run bounded pilots"
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--read-rows-per-source", type=int, default=1000)
    parser.add_argument("--embedding-sample-size", type=int, default=0)
    parser.add_argument("--embedding-batch-size", type=int, default=8)
    parser.add_argument("--ollama-model", default="qwen3-embedding")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence = build_evidence(
            load_manifest(args.manifest),
            args.raw_root,
            args.read_rows_per_source,
            args.embedding_sample_size,
            args.embedding_batch_size,
            args.ollama_model,
            args.ollama_url,
        )
        json_content = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
        markdown_content = render_markdown(evidence)
        _atomic_write(
            args.output_json,
            json_content,
        )
        _atomic_write(args.output_markdown, markdown_content)
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        print(f"DS-02 validation: ERROR\n- {exc}")
        return 2
    print(render_markdown(evidence))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
