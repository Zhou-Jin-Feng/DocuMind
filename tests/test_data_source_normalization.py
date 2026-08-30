import csv
import json
import tempfile
import unittest
from pathlib import Path

import pyarrow as arrow
import pyarrow.parquet as parquet
from jsonschema import Draft202012Validator

from evaluation.data_source_downloader import sha256_file
from evaluation.data_source_normalization import (
    NormalizationError,
    build_normalized_snapshot,
    canonical_json_bytes,
    canonical_sha256,
    stable_normalized_id,
    validate_normalized_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "evaluation" / "data_sources" / "contracts"


def _write_parquet(path: Path, values: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    parquet.write_table(arrow.table(values), path)
    return {"bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _write_tsv(path: Path, rows: list[tuple[str, str, int]]) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("query-id", "corpus-id", "score"))
        writer.writerows(rows)
    return {"bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _file_entry(path: str, kind: str, rows: int, metadata: dict, **extra) -> dict:
    columns = {
        "corpus": ["_id", "title", "text"],
        "queries": ["_id", "text"],
        "qrels": ["query-id", "corpus-id", "score"],
    }[kind]
    return {
        "path": path,
        "kind": kind,
        "rows": rows,
        "columns": columns,
        **metadata,
        **extra,
    }


def _build_manifest(
    raw_root: Path,
    *,
    duplicate_t2_document: bool = False,
    duplicate_t2_qrel: bool = False,
    dangling_t2_document: bool = False,
    invalid_t2_grade: bool = False,
    conflicting_nfcorpus_split: bool = False,
) -> dict:
    revisions = {
        "t2": "a" * 40,
        "nfcorpus": "b" * 40,
        "nfcorpus_qrels": "c" * 40,
        "scifact": "d" * 40,
        "scifact_qrels": "e" * 40,
    }
    sources = []

    t2_root = raw_root / "t2ranking-mteb-dev" / "mteb__T2Retrieval"
    document_ids = ["d1", "d1" if duplicate_t2_document else "d2"]
    corpus_meta = _write_parquet(
        t2_root / "corpus" / "dev.parquet",
        {"_id": document_ids, "title": ["T1", "T2"], "text": ["甲", "乙"]},
    )
    query_meta = _write_parquet(
        t2_root / "queries" / "dev.parquet",
        {"_id": ["q1", "q2"], "text": ["问题一", "问题二"]},
    )
    second_document = "missing" if dangling_t2_document else "d2"
    grade = 4 if invalid_t2_grade else 1
    pairs = [("q1", "d1", 1), ("q2", second_document, grade)]
    if duplicate_t2_qrel:
        pairs[1] = pairs[0]
    qrel_meta = _write_parquet(
        t2_root / "data" / "dev.parquet",
        {
            "query-id": [row[0] for row in pairs],
            "corpus-id": [row[1] for row in pairs],
            "score": [row[2] for row in pairs],
        },
    )
    sources.append(
        {
            "id": "t2ranking-mteb-dev",
            "decision": "approved_for_ds02",
            "selected_artifact": {
                "dataset_id": "mteb/T2Retrieval",
                "revision": revisions["t2"],
                "counts": {"corpus": 2, "queries": 2, "qrels": 2, "split": "dev"},
                "files": [
                    _file_entry("corpus/dev.parquet", "corpus", 2, corpus_meta),
                    _file_entry("queries/dev.parquet", "queries", 2, query_meta),
                    _file_entry("data/dev.parquet", "qrels", 2, qrel_meta),
                ],
            },
        }
    )

    nf_root = raw_root / "beir-nfcorpus"
    nf_corpus = nf_root / "BeIR__nfcorpus"
    nf_qrels = nf_root / "BeIR__nfcorpus-qrels"
    corpus_meta = _write_parquet(
        nf_corpus / "corpus" / "corpus.parquet",
        {"_id": ["n1", "n2"], "title": ["N1", "N2"], "text": ["one", "two"]},
    )
    query_meta = _write_parquet(
        nf_corpus / "queries" / "queries.parquet",
        {"_id": ["nq1", "nq2"], "text": ["first", "second"]},
    )
    train_meta = _write_tsv(nf_qrels / "train.tsv", [("nq1", "n1", 2)])
    test_query = "nq1" if conflicting_nfcorpus_split else "nq2"
    test_meta = _write_tsv(nf_qrels / "test.tsv", [(test_query, "n2", 1)])
    sources.append(
        {
            "id": "beir-nfcorpus",
            "decision": "approved_for_ds02",
            "selected_artifact": {
                "counts": {"corpus": 2, "queries": 2, "qrels": 2},
                "repositories": [
                    {
                        "dataset_id": "BeIR/nfcorpus",
                        "revision": revisions["nfcorpus"],
                        "files": [
                            _file_entry(
                                "corpus/corpus.parquet", "corpus", 2, corpus_meta
                            ),
                            _file_entry(
                                "queries/queries.parquet", "queries", 2, query_meta
                            ),
                        ],
                    },
                    {
                        "dataset_id": "BeIR/nfcorpus-qrels",
                        "revision": revisions["nfcorpus_qrels"],
                        "files": [
                            _file_entry(
                                "train.tsv", "qrels", 1, train_meta, split="train"
                            ),
                            _file_entry(
                                "test.tsv", "qrels", 1, test_meta, split="test"
                            ),
                        ],
                    },
                ],
            },
        }
    )

    sf_root = raw_root / "beir-scifact"
    sf_corpus = sf_root / "BeIR__scifact"
    sf_qrels = sf_root / "BeIR__scifact-qrels"
    corpus_meta = _write_parquet(
        sf_corpus / "corpus" / "corpus.parquet",
        {"_id": ["s1"], "title": ["S1"], "text": ["evidence"]},
    )
    query_meta = _write_parquet(
        sf_corpus / "queries" / "queries.parquet",
        {"_id": ["sq1"], "text": ["claim"]},
    )
    qrel_meta = _write_tsv(sf_qrels / "test.tsv", [("sq1", "s1", 1)])
    sources.append(
        {
            "id": "beir-scifact",
            "decision": "approved_for_ds02",
            "selected_artifact": {
                "counts": {"corpus": 1, "queries": 1, "qrels": 1},
                "repositories": [
                    {
                        "dataset_id": "BeIR/scifact",
                        "revision": revisions["scifact"],
                        "files": [
                            _file_entry(
                                "corpus/corpus.parquet", "corpus", 1, corpus_meta
                            ),
                            _file_entry(
                                "queries/queries.parquet", "queries", 1, query_meta
                            ),
                        ],
                    },
                    {
                        "dataset_id": "BeIR/scifact-qrels",
                        "revision": revisions["scifact_qrels"],
                        "files": [
                            _file_entry("test.tsv", "qrels", 1, qrel_meta, split="test")
                        ],
                    },
                ],
            },
        }
    )
    return {
        "schema_version": "p2-data-source-manifest-v1",
        "download_authorized": True,
        "download_authorization": {"source_ids": [source["id"] for source in sources]},
        "sources": sources,
    }


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class DataSourceNormalizationTests(unittest.TestCase):
    def test_contract_schemas_are_valid_and_strict(self):
        for path in sorted(CONTRACT_ROOT.glob("*-v1.schema.json")):
            with self.subTest(path=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)
        document_schema = json.loads(
            (CONTRACT_ROOT / "documents-v1.schema.json").read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(document_schema)
        invalid = {
            "schema_version": "p2-normalized-document-v1",
            "id": "p2n:document:" + "a" * 64,
            "source_snapshot_id": "source",
            "source_dataset": "owner/data",
            "source_revision": "b" * 40,
            "source_document_id": "d1",
            "title": "",
            "text": "content",
            "language": "en",
            "authority_state": "official_benchmark",
            "content_sha256": "c" * 64,
            "unknown": True,
        }
        self.assertTrue(list(validator.iter_errors(invalid)))

    def test_all_adapters_rebuild_identical_ids_counts_and_fingerprints(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw"
            manifest = _build_manifest(raw_root)
            manifest_hash = canonical_sha256(manifest)
            first_root = root / "normalized-first"
            second_root = root / "normalized-second"

            first = build_normalized_snapshot(
                manifest, raw_root, first_root, manifest_sha256=manifest_hash
            )
            second = build_normalized_snapshot(
                manifest, raw_root, second_root, manifest_sha256=manifest_hash
            )

            self.assertEqual(first, second)
            self.assertEqual(first["snapshot"]["counts"]["documents"], 5)
            self.assertEqual(first["snapshot"]["counts"]["queries"], 5)
            self.assertEqual(first["snapshot"]["counts"]["qrels"], 5)
            for relative in (
                "snapshot.json",
                "t2ranking-mteb-dev/documents.jsonl",
                "t2ranking-mteb-dev/queries.jsonl",
                "t2ranking-mteb-dev/qrels.jsonl",
                "beir-nfcorpus/documents.jsonl",
                "beir-nfcorpus/queries.jsonl",
                "beir-nfcorpus/qrels.jsonl",
                "beir-scifact/documents.jsonl",
                "beir-scifact/queries.jsonl",
                "beir-scifact/qrels.jsonl",
            ):
                self.assertEqual(
                    (first_root / relative).read_bytes(),
                    (second_root / relative).read_bytes(),
                )
            self.assertTrue(
                validate_normalized_snapshot(first_root, CONTRACT_ROOT)["ok"]
            )

    def test_official_identity_split_grade_and_provenance_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw"
            manifest = _build_manifest(raw_root)
            output = root / "normalized"
            build_normalized_snapshot(
                manifest,
                raw_root,
                output,
                manifest_sha256=canonical_sha256(manifest),
            )

            queries = _read_jsonl(output / "beir-nfcorpus" / "queries.jsonl")
            qrels = _read_jsonl(output / "beir-nfcorpus" / "qrels.jsonl")
            by_source_id = {item["source_query_id"]: item for item in queries}
            self.assertEqual(by_source_id["nq1"]["split"], "train")
            self.assertEqual(by_source_id["nq2"]["split"], "test")
            self.assertTrue(all(item["answerable"] for item in queries))
            grade_two = next(item for item in qrels if item["relevance_grade"] == 2)
            self.assertEqual(grade_two["label_provenance"]["method"], "official_qrels")
            self.assertEqual(
                grade_two["label_provenance"]["source_dataset"],
                "BeIR/nfcorpus-qrels",
            )

    def test_stable_ids_are_namespaced_and_repeatable(self):
        first = stable_normalized_id("source-a", "document", "same")
        self.assertEqual(first, stable_normalized_id("source-a", "document", "same"))
        self.assertNotEqual(first, stable_normalized_id("source-b", "document", "same"))
        self.assertNotEqual(first, stable_normalized_id("source-a", "query", "same"))

    def test_duplicate_document_and_qrel_are_rejected(self):
        scenarios = (
            ({"duplicate_t2_document": True}, "duplicate document ID"),
            ({"duplicate_t2_qrel": True}, "duplicate qrel pair"),
        )
        for options, message in scenarios:
            with (
                self.subTest(options=options),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                raw_root = root / "raw"
                manifest = _build_manifest(raw_root, **options)
                with self.assertRaisesRegex(NormalizationError, message):
                    build_normalized_snapshot(
                        manifest,
                        raw_root,
                        root / "normalized",
                        manifest_sha256=canonical_sha256(manifest),
                        source_ids=["t2ranking-mteb-dev"],
                    )

    def test_dangling_qrel_and_invalid_grade_are_rejected(self):
        scenarios = (
            ({"dangling_t2_document": True}, "unknown document"),
            ({"invalid_t2_grade": True}, "outside 0-3"),
        )
        for options, message in scenarios:
            with (
                self.subTest(options=options),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                raw_root = root / "raw"
                manifest = _build_manifest(raw_root, **options)
                with self.assertRaisesRegex(NormalizationError, message):
                    build_normalized_snapshot(
                        manifest,
                        raw_root,
                        root / "normalized",
                        manifest_sha256=canonical_sha256(manifest),
                        source_ids=["t2ranking-mteb-dev"],
                    )

    def test_query_cannot_cross_official_splits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw"
            manifest = _build_manifest(raw_root, conflicting_nfcorpus_split=True)
            with self.assertRaisesRegex(NormalizationError, "multiple splits"):
                build_normalized_snapshot(
                    manifest,
                    raw_root,
                    root / "normalized",
                    manifest_sha256=canonical_sha256(manifest),
                    source_ids=["beir-nfcorpus"],
                )

    def test_existing_output_requires_explicit_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw"
            manifest = _build_manifest(raw_root)
            output = root / "normalized"
            output.mkdir()
            sentinel = output / "do-not-overwrite.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "replace=True"):
                build_normalized_snapshot(
                    manifest,
                    raw_root,
                    output,
                    manifest_sha256=canonical_sha256(manifest),
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            with self.assertRaisesRegex(NormalizationError, "unowned"):
                build_normalized_snapshot(
                    manifest,
                    raw_root,
                    output,
                    manifest_sha256=canonical_sha256(manifest),
                    replace=True,
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_owned_output_can_be_replaced_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw"
            manifest = _build_manifest(raw_root)
            output = root / "normalized"
            first = build_normalized_snapshot(
                manifest,
                raw_root,
                output,
                manifest_sha256=canonical_sha256(manifest),
            )
            second = build_normalized_snapshot(
                manifest,
                raw_root,
                output,
                manifest_sha256=canonical_sha256(manifest),
                replace=True,
            )
            self.assertEqual(first, second)
            self.assertFalse(list(root.glob(".normalized.backup-*")))

    def test_validation_rejects_snapshot_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw"
            manifest = _build_manifest(raw_root)
            output = root / "normalized"
            build_normalized_snapshot(
                manifest,
                raw_root,
                output,
                manifest_sha256=canonical_sha256(manifest),
            )
            snapshot_path = output / "snapshot.json"
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            snapshot["source_manifests"][0]["outputs"]["documents"][
                "path"
            ] = "../documents.jsonl"
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(NormalizationError, "unsafe"):
                validate_normalized_snapshot(output, CONTRACT_ROOT)

    def test_validation_recomputes_qrel_references_and_aggregate_fingerprints(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw"
            manifest = _build_manifest(raw_root)
            output = root / "normalized"
            build_normalized_snapshot(
                manifest,
                raw_root,
                output,
                manifest_sha256=canonical_sha256(manifest),
                source_ids=["t2ranking-mteb-dev"],
            )
            qrels_path = output / "t2ranking-mteb-dev" / "qrels.jsonl"
            qrels = _read_jsonl(qrels_path)
            qrels[0]["document_id"] = "p2n:document:" + "f" * 64
            qrels_path.write_bytes(
                b"".join(canonical_json_bytes(record) + b"\n" for record in qrels)
            )
            snapshot_path = output / "snapshot.json"
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            snapshot["source_manifests"][0]["outputs"]["qrels"]["sha256"] = sha256_file(
                qrels_path
            )
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            result = validate_normalized_snapshot(output, CONTRACT_ROOT)

            self.assertFalse(result["ok"])
            self.assertTrue(
                any("unknown document" in error for error in result["errors"])
            )
            self.assertIn("aggregate dataset fingerprint mismatch", result["errors"])


if __name__ == "__main__":
    unittest.main()
