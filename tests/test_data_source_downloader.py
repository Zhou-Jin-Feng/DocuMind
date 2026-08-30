import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.data_source_downloader import (
    BudgetError,
    IntegrityError,
    _download_once,
    acquire,
    destination_for,
    iter_file_specs,
)
from evaluation.data_source_validation import (
    _runtime_policy,
    _validate_parquet,
    _validate_tsv,
    render_markdown,
)


def _manifest(content: bytes = b"abcdef") -> dict:
    return {
        "schema_version": "p2-data-source-manifest-v1",
        "download_authorized": True,
        "download_authorization": {"source_ids": ["approved"]},
        "budget": {
            "raw_plus_normalized_limit_bytes": 1024,
            "single_source_limit_bytes": 1024,
            "minimum_free_space_bytes": 0,
            "automatic_download_attempts": 3,
        },
        "sources": [
            {
                "id": "approved",
                "decision": "approved_for_ds02",
                "selected_artifact": {
                    "dataset_id": "owner/dataset",
                    "revision": "a" * 40,
                    "files": [
                        {
                            "path": "folder/file.bin",
                            "bytes": len(content),
                            "sha256": hashlib.sha256(content).hexdigest(),
                            "kind": "corpus",
                        }
                    ],
                },
            }
        ],
    }


class _Response(io.BytesIO):
    def __init__(self, value: bytes, status: int):
        super().__init__(value)
        self.status = status

    def getcode(self):
        return self.status


class DataSourceDownloaderTests(unittest.TestCase):
    def test_runtime_policy_freezes_launch_and_hard_limits(self):
        manifest = _manifest()
        manifest["budget"].update(
            {
                "maximum_launch_projection_hours": 18,
                "maximum_end_to_end_runtime_hours": 24,
            }
        )
        self.assertEqual(_runtime_policy(manifest), (18.0, 24.0))

    def test_runtime_policy_rejects_launch_limit_above_hard_limit(self):
        manifest = _manifest()
        manifest["budget"].update(
            {
                "maximum_launch_projection_hours": 25,
                "maximum_end_to_end_runtime_hours": 24,
            }
        )
        with self.assertRaisesRegex(ValueError, "runtime policy"):
            _runtime_policy(manifest)

    def test_manifest_level_download_gate_is_enforced(self):
        manifest = _manifest()
        manifest["download_authorized"] = False
        with self.assertRaisesRegex(ValueError, "does not authorize"):
            iter_file_specs(manifest)

    def test_plan_contains_only_authorized_sources(self):
        manifest = _manifest()
        manifest["sources"].append(
            {
                "id": "conditional",
                "decision": "conditional_local_only",
                "selected_artifact": {
                    "dataset_id": "owner/other",
                    "revision": "b" * 40,
                    "files": [
                        {
                            "path": "forbidden.bin",
                            "bytes": 1,
                            "sha256": "0" * 64,
                            "kind": "corpus",
                        }
                    ],
                },
            }
        )
        specs = iter_file_specs(manifest)
        self.assertEqual([spec.source_id for spec in specs], ["approved"])
        with self.assertRaisesRegex(ValueError, "not authorized"):
            iter_file_specs(manifest, ["conditional"])

    def test_download_resumes_partial_file_and_replaces_atomically(self):
        spec = iter_file_specs(_manifest())[0]
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "file.bin"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.with_name("file.bin.part").write_bytes(b"abc")
            requests = []

            def fake_open(request, timeout):
                requests.append((request, timeout))
                return _Response(b"def", 206)

            with patch(
                "evaluation.data_source_downloader.urlopen", side_effect=fake_open
            ):
                _download_once(spec, destination, timeout=5)
            self.assertEqual(destination.read_bytes(), b"abcdef")
            self.assertFalse(destination.with_name("file.bin.part").exists())
            self.assertEqual(requests[0][0].headers["Range"], "bytes=3-")

    def test_complete_partial_file_is_verified_without_network(self):
        spec = iter_file_specs(_manifest())[0]
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "file.bin"
            destination.with_name("file.bin.part").write_bytes(b"abcdef")
            with patch("evaluation.data_source_downloader.urlopen") as network:
                _download_once(spec, destination, timeout=5)
            network.assert_not_called()
            self.assertEqual(destination.read_bytes(), b"abcdef")

    def test_complete_corrupt_partial_file_is_replaced_from_network(self):
        spec = iter_file_specs(_manifest())[0]
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "file.bin"
            destination.with_name("file.bin.part").write_bytes(b"xxxxxx")

            with patch(
                "evaluation.data_source_downloader.urlopen",
                return_value=_Response(b"abcdef", 200),
            ) as network:
                _download_once(spec, destination, timeout=5)

            network.assert_called_once()
            self.assertEqual(destination.read_bytes(), b"abcdef")
            self.assertFalse(destination.with_name("file.bin.part").exists())

    def test_existing_corrupt_cache_is_rejected_without_overwrite(self):
        manifest = _manifest()
        spec = iter_file_specs(manifest)[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw"
            target = destination_for(spec, raw_root)
            target.parent.mkdir(parents=True)
            target.write_bytes(b"xxxxxx")
            with self.assertRaisesRegex(IntegrityError, "existing file"):
                acquire(
                    manifest, raw_root, root / "normalized", sleep_fn=lambda _: None
                )
            self.assertEqual(target.read_bytes(), b"xxxxxx")

    def test_total_budget_is_enforced_before_network_access(self):
        manifest = _manifest()
        manifest["budget"]["raw_plus_normalized_limit_bytes"] = 5
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(BudgetError):
                acquire(manifest, root / "raw", root / "normalized")

    def test_explicit_zero_retries_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "at least one"):
                acquire(_manifest(), root / "raw", root / "normalized", retries=0)

    def test_tsv_validator_checks_columns_and_rows(self):
        manifest = _manifest(b"unused")
        entry = manifest["sources"][0]["selected_artifact"]["files"][0]
        entry.update(
            {
                "path": "qrels.tsv",
                "kind": "qrels",
                "rows": 2,
                "columns": ["query-id", "corpus-id", "score"],
            }
        )
        spec = iter_file_specs(manifest)[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qrels.tsv"
            path.write_text(
                "query-id\tcorpus-id\tscore\nq1\td1\t2\nq2\td2\t1\n", encoding="utf-8"
            )
            result = _validate_tsv(spec, path)
            self.assertEqual(result["rows"], 2)
            self.assertEqual(result["columns"], ["query-id", "corpus-id", "score"])

    def test_parquet_validator_reads_schema_rows_and_sample(self):
        import pyarrow as arrow
        import pyarrow.parquet as parquet

        manifest = _manifest(b"unused")
        entry = manifest["sources"][0]["selected_artifact"]["files"][0]
        entry.update(
            {
                "path": "corpus.parquet",
                "kind": "corpus",
                "rows": 2,
                "columns": ["_id", "title", "text"],
            }
        )
        spec = iter_file_specs(manifest)[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.parquet"
            table = arrow.table(
                {
                    "_id": ["d1", "d2"],
                    "title": ["one", "two"],
                    "text": ["alpha", "beta"],
                }
            )
            parquet.write_table(table, path)
            result = _validate_parquet(spec, path)
            self.assertEqual(result["rows"], 2)
            self.assertEqual(result["columns"], ["_id", "title", "text"])
            self.assertEqual(result["sample_rows_read"], 2)

    def test_markdown_renders_without_embedding_projection(self):
        evidence = {
            "all_hashes_match": True,
            "file_count": 1,
            "total_bytes": 6,
            "authorized_source_ids": ["approved"],
            "structure": {
                "ok": True,
                "aggregate_rows": {"approved": {"corpus": 2}},
            },
            "read_pilot": {"rows": 2, "seconds": 0.1, "rows_per_second": 20.0},
            "embedding_pilot": None,
            "miracl_assessment": {
                "decision": "DEFER_FULL_DOWNLOAD",
                "raw_float32_vector_bytes": 10,
                "projected_free_after_raw_and_vectors_bytes": 20,
                "meets_disk_floor_before_milvus_overhead": False,
                "meets_launch_projection_limit": False,
                "meets_end_to_end_runtime_limit": False,
                "eligible_to_start": False,
                "license_status": "UNRESOLVED_CONFLICT",
                "embedding_only_projection_hours": None,
            },
        }

        markdown = render_markdown(evidence)

        self.assertIn("embedding-only projection: `not measured`", markdown)


if __name__ == "__main__":
    unittest.main()
