import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import subprocess
import stat
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from backend.app.schemas.experiment import ExperimentCase
from backend.app.services.repository_scanner import read_file_snapshot
from scripts import prepare_experiment as script


def case_data():
    return dict(case_id="sample", case_version="v1", task_type="bug_fix",
        user_request="修复示例", repository_commit="a" * 40,
        editable_files=["example.py"], protected_test_files=["tests/test_example.py"],
        test_profile="python-basic")


class ExperimentCaseTests(unittest.TestCase):
    def test_valid_case_and_categories(self):
        for category in ("bug_fix", "feature"):
            case = ExperimentCase.model_validate({**case_data(), "task_type": category})
            self.assertEqual(case.schema_version, 1)

    def test_scope_rejects_duplicates_and_overlap(self):
        for update in (
            {"editable_files": ["example.py", "example.py"]},
            {"protected_test_files": ["test.py", "test.py"]},
            {"protected_test_files": ["example.py"]},
            {"editable_files": []}, {"protected_test_files": []},
        ):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                ExperimentCase.model_validate({**case_data(), **update})

    def test_raw_invalid_paths_in_both_scopes(self):
        for field in ("editable_files", "protected_test_files"):
            for path in ("", "/secret.py", "D:/secret.py", "D:secret.py", "a\\b.py",
                         "a//b.py", "./a.py", "a/../b.py", ".git/a.py", "a/.GIT/b.py",
                         "a.txt", "a.py/", " a.py", "a.py\x00"):
                with self.subTest(field=field, path=path), self.assertRaises(ValidationError):
                    ExperimentCase.model_validate({**case_data(), field: [path]})

    def test_schema_and_commit_are_validated(self):
        for update in ({"source_path": "D:/sample"}, {"task_type": "plan"},
                       {"schema_version": 2}, {"repository_commit": "a1862aa"},
                       {"repository_commit": "A" * 40}):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                ExperimentCase.model_validate({**case_data(), **update})

    def test_shipped_cases_have_valid_configuration(self):
        root = Path(__file__).resolve().parents[1] / "evals/experiments/cases"
        self.assertEqual(script.load_experiment_case(root / "task-list-v1.json").case_id, "task-list")
        for case_id, category in (("deduplicate", "bug_fix"), ("statistics", "feature")):
            with self.subTest(case_id=case_id):
                case = script.load_experiment_case(root / f"{case_id}-v1.json")
                self.assertEqual(case.case_id, case_id)
                self.assertEqual(case.task_type, category)
                self.assertEqual(case.editable_files, [f"{case_id}.py"])
                self.assertEqual(case.protected_test_files, [f"tests/test_{case_id}.py"])


# 使用临时 Git 仓库验证实际只读检查，不调用模型、数据库或 Docker。
class ExperimentInspectionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        (self.root / "tests").mkdir()
        (self.root / "example.py").write_text("value = 1\n", encoding="utf-8")
        (self.root / "tests/test_example.py").write_text("def test_value():\n    assert True\n", encoding="utf-8")
        self.git("init")
        self.git("add", ".")
        self.git("-c", "user.name=Experiment Test", "-c", "user.email=test@example.invalid",
                 "commit", "-m", "baseline")
        self.case = ExperimentCase.model_validate({**case_data(), "repository_commit": self.git("rev-parse", "HEAD").strip()})

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout

    def test_summary_uses_snapshot_hash_without_changes(self):
        summary = script.inspect_experiment_source(self.case, source_path=self.root)
        snapshot = read_file_snapshot(self.root, self.root / "tests/test_example.py")
        self.assertEqual(summary["protected_test_file_hashes"], {"tests/test_example.py": snapshot.metadata.file_hash})
        self.assertEqual(summary["image"], "repopilot-pytest:py311")
        self.assertEqual(summary["repository_commit"], self.case.repository_commit)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.case.repository_commit)

    def test_wrong_commit_or_profile_stops_before_file_reads(self):
        for field, value in (("repository_commit", "b" * 40), ("test_profile", "unknown")):
            with self.subTest(field=field), patch.object(script, "read_file_snapshot") as read:
                case = self.case.model_copy(update={field: value})
                with self.assertRaises(ValueError):
                    script.inspect_experiment_source(case, source_path=self.root)
                read.assert_not_called()

    def test_dirty_repository_is_rejected(self):
        (self.root / "extra.py").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "clean working tree"):
            script.inspect_experiment_source(self.case, source_path=self.root)

    def test_non_root_and_relative_paths_are_rejected(self):
        for source in (self.root / "tests", Path("relative")):
            with self.subTest(source=source), self.assertRaises(ValueError):
                script.inspect_experiment_source(self.case, source_path=source)

    def test_missing_files_are_rejected(self):
        for field in ("editable_files", "protected_test_files"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "must be tracked by Git"):
                script.inspect_experiment_source(self.case.model_copy(update={field: ["missing.py"]}), source_path=self.root)

    def test_existing_ignored_untracked_file_is_rejected(self):
        (self.root / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("-c", "user.name=Experiment Test", "-c", "user.email=test@example.invalid",
                 "commit", "-m", "ignore local-only file")
        (self.root / "ignored.py").write_text("assert True\n", encoding="utf-8")
        self.assertEqual(self.git("status", "--porcelain"), "")
        commit = self.git("rev-parse", "HEAD").strip()
        for field in ("editable_files", "protected_test_files"):
            with self.subTest(field=field):
                case = self.case.model_copy(update={"repository_commit": commit, field: ["ignored.py"]})
                with self.assertRaisesRegex(ValueError, "must be tracked by Git: ignored.py"):
                    script.inspect_experiment_source(case, source_path=self.root)

    def test_link_is_rejected(self):
        original_lstat = Path.lstat
        def linked_stat(path, *args, **kwargs):
            if path == self.root / "example.py":
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
            return original_lstat(path, *args, **kwargs)
        with patch.object(Path, "lstat", linked_stat):
            with self.assertRaises(ValueError):
                script.inspect_experiment_source(self.case, source_path=self.root)

    def test_cli_outputs_json_and_rejects_bad_config(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "case.json"
            path.write_text(self.case.model_dump_json(), encoding="utf-8")
            args = ["prepare_experiment", "--case", str(path), "--source-path", str(self.root)]
            output = io.StringIO()
            with patch("sys.argv", args), redirect_stdout(output):
                script.main()
            self.assertEqual(json.loads(output.getvalue())["message"], "准备检查通过，尚未创建实验运行")
            path.write_text("{}", encoding="utf-8")
            with patch("sys.argv", args), redirect_stderr(io.StringIO()), \
                 patch.object(script, "inspect_experiment_source") as inspect:
                with self.assertRaises(SystemExit) as raised:
                    script.main()
                self.assertNotEqual(raised.exception.code, 0)
                inspect.assert_not_called()
