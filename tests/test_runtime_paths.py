import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from app.lifecycle.registry import DocumentRegistry
from app.lifecycle.service import DocumentLifecycleService
from app.observability.logging import reset_logger, setup_logger


class RuntimePathTests(unittest.TestCase):
    @staticmethod
    def options(root):
        return dict(
            _env_file=None,
            document_registry_path=str(root / "state" / "registry.sqlite3"),
            upload_dir=str(root / "uploads"),
            log_file_path=str(root / "logs" / "app_{time:YYYY-MM-DD}.jsonl"),
        )

    def test_default_paths_are_project_relative_not_cwd_relative(self):
        project_root = Path(__file__).resolve().parents[1]
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {}, clear=True),
        ):
            old = Path.cwd()
            try:
                os.chdir(directory)
                config = Settings(_env_file=None)
            finally:
                os.chdir(old)
        self.assertEqual(
            Path(config.document_registry_path),
            project_root / "data" / "document_registry.sqlite3",
        )
        self.assertEqual(Path(config.upload_dir), project_root / "data" / "uploads")
        self.assertEqual(
            Path(config.log_file_path),
            project_root / "logs" / "rag_{time:YYYY-MM-DD}.jsonl",
        )
        self.assertEqual(Path(Settings.model_config["env_file"]), project_root / ".env")

    def test_relative_overrides_use_project_root(self):
        project_root = Path(__file__).resolve().parents[1]
        config = Settings(
            _env_file=None,
            document_registry_path="state/registry.sqlite3",
            upload_dir="content/uploads",
            log_file_path="runtime/logs/app.jsonl",
        )
        self.assertEqual(
            Path(config.document_registry_path),
            project_root / "state" / "registry.sqlite3",
        )
        self.assertEqual(Path(config.upload_dir), project_root / "content" / "uploads")
        self.assertEqual(
            Path(config.log_file_path), project_root / "runtime" / "logs" / "app.jsonl"
        )

    def test_absolute_overrides_and_log_template_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = Settings(**self.options(root))
            self.assertEqual(
                Path(config.document_registry_path), root / "state" / "registry.sqlite3"
            )
            self.assertEqual(Path(config.upload_dir), root / "uploads")
            self.assertEqual(
                Path(config.log_file_path),
                root / "logs" / "app_{time:YYYY-MM-DD}.jsonl",
            )
            self.assertEqual(list(root.iterdir()), [])

    def test_runtime_directories_are_created_explicitly_and_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = Settings(**self.options(root))
            self.assertEqual(list(root.iterdir()), [])
            config.ensure_runtime_directories()
            marker = root / "uploads" / "keep.txt"
            marker.write_text("unchanged", encoding="utf-8")
            config.ensure_runtime_directories()
            self.assertTrue((root / "state").is_dir())
            self.assertTrue((root / "logs").is_dir())
            self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")
            self.assertFalse(Path(config.document_registry_path).exists())

    def test_blank_log_path_disables_log_directory_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            options = self.options(root)
            options["log_file_path"] = ""
            config = Settings(**options)
            config.ensure_runtime_directories()
            self.assertEqual(config.log_file_path, "")
            self.assertFalse((root / "logs").exists())

    def test_empty_data_paths_fail_validation(self):
        for field in ["document_registry_path", "upload_dir"]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                Settings(_env_file=None, **{field: "   "})

    def test_directory_conflict_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blocker = root / "uploads"
            blocker.write_text("keep", encoding="utf-8")
            config = Settings(**self.options(root))
            with self.assertRaises(OSError):
                config.ensure_runtime_directories()
            self.assertEqual(blocker.read_text(encoding="utf-8"), "keep")

    def test_registry_upload_and_logs_use_configured_locations_from_other_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = Settings(**self.options(root / "runtime"))
            other = root / "elsewhere"
            other.mkdir()
            source = root / "input.txt"
            source.write_text("safe sample", encoding="utf-8")
            old = Path.cwd()
            try:
                os.chdir(other)
                config.ensure_runtime_directories()
                DocumentRegistry(config.document_registry_path)
                saved = DocumentLifecycleService.persist_source_file(
                    source, config.upload_dir
                )
                setup_logger(
                    log_file_path=config.log_file_path,
                    console_sink=io.StringIO(),
                    console_format="json",
                )
                reset_logger()
                self.assertTrue(Path(config.document_registry_path).is_file())
                self.assertEqual(saved.parent, Path(config.upload_dir))
                self.assertEqual(
                    len(list((root / "runtime" / "logs").glob("app_*.jsonl"))), 1
                )
                self.assertEqual(list(other.iterdir()), [])
            finally:
                reset_logger()
                os.chdir(old)

    def test_default_env_is_project_file_and_override_or_disable_remains_supported(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            other = root / "other"
            (project / "app").mkdir(parents=True)
            other.mkdir()
            (project / "app" / "__init__.py").write_text("", encoding="utf-8")
            shutil.copy2(
                Path(__file__).resolve().parents[1] / "app" / "config.py",
                project / "app" / "config.py",
            )
            (project / ".env").write_text(
                "SERVICE_NAME=project-config\nUPLOAD_DIR=data/from-project\n",
                encoding="utf-8",
            )
            (other / ".env").write_text(
                "SERVICE_NAME=wrong-cwd-config\n", encoding="utf-8"
            )
            custom = root / "custom.env"
            custom.write_text("SERVICE_NAME=explicit-config\n", encoding="utf-8")
            script = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from app.config import Settings
config = Settings()
print(json.dumps({
    'default': config.service_name,
    'upload': config.upload_dir,
    'explicit': Settings(_env_file=sys.argv[2]).service_name,
    'disabled': Settings(_env_file=None).service_name,
    'created_data': (Path(sys.argv[1]) / 'data').exists(),
    'created_logs': (Path(sys.argv[1]) / 'logs').exists(),
}))
"""
            env = os.environ.copy()
            for key in list(env):
                if (
                    key.upper() in Settings.model_fields
                    or key.lower() in Settings.model_fields
                ):
                    env.pop(key)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [sys.executable, "-c", script, str(project), str(custom)],
                cwd=other,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["default"], "project-config")
            self.assertEqual(payload["explicit"], "explicit-config")
            self.assertEqual(payload["disabled"], "rag-web")
            self.assertEqual(Path(payload["upload"]), project / "data" / "from-project")
            self.assertFalse(payload["created_data"])
            self.assertFalse(payload["created_logs"])

    def test_offline_runner_uses_bundled_input_and_honors_explicit_relative_output(
        self,
    ):
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(project_root)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            command = [
                sys.executable,
                "-m",
                "evaluation.runner",
                "--output-json",
                "chosen-output/result.json",
                "--output-markdown",
                "chosen-output/result.md",
            ]
            result = subprocess.run(
                command,
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "chosen-output" / "result.json").is_file())
            self.assertTrue((root / "chosen-output" / "result.md").is_file())
            self.assertFalse((root / "evaluation").exists())
            self.assertFalse((root / "data").exists())
            self.assertFalse((root / "logs").exists())

    def test_report_command_defaults_do_not_target_frozen_evidence(self):
        from evaluation import comparison_runner, production_runner, ds06_runner

        project_root = Path(__file__).resolve().parents[1]
        captured = []

        class StopBeforeExecution(Exception):
            pass

        def inspect_parser(parser, *args, **kwargs):
            captured.append({action.dest: action.default for action in parser._actions})
            raise StopBeforeExecution

        for entry in [comparison_runner.main, production_runner.main, ds06_runner._cli]:
            with patch.object(argparse.ArgumentParser, "parse_args", inspect_parser):
                with self.assertRaises(StopBeforeExecution):
                    entry()
        self.assertEqual(
            Path(captured[0]["output_json"]),
            project_root / "artifacts" / "evaluation" / "v1_7_1_comparison.json",
        )
        self.assertEqual(
            Path(captured[0]["output_markdown"]),
            project_root / "artifacts" / "evaluation" / "v1_7_1_comparison.md",
        )
        self.assertEqual(
            production_runner.DEFAULT_OUTPUT_ROOT,
            project_root / "artifacts" / "evaluation",
        )
        self.assertEqual(
            Path(captured[1]["dataset"]),
            project_root / "evaluation" / "datasets" / "golden_dataset.jsonl",
        )
        self.assertIsNone(captured[1]["output_json"])
        self.assertEqual(
            captured[2]["output_dir"],
            project_root / "artifacts" / "evaluation" / "ds06",
        )
        self.assertEqual(
            captured[2]["dataset_root"],
            project_root / "evaluation" / "datasets" / "p2_retrieval_v2",
        )


if __name__ == "__main__":
    unittest.main()
