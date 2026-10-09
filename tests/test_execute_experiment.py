from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from backend.app.schemas.edit import FileEditProposal, TaskFileEditRead
from backend.app.schemas.experiment import ExperimentCase, ExperimentPreparation, ExperimentEditCandidate
from backend.app.schemas.run_config import AgentRunConfig
from backend.app.schemas.task import TaskRead
from backend.app.schemas.task_report import TaskExecutionReport
from backend.app.schemas.testing import TestRunRead
from backend.app.services.workspace_edit_service import WorkspaceWriteResult
from scripts import execute_experiment as cli


class ExecuteExperimentTests(unittest.TestCase):
    """真实读写临时操作记录；所有数据库、模型、容器操作均被替换。"""

    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.preparation_path = self.root / "preparation.json"
        now = datetime.now(timezone.utc)
        self.preparation = ExperimentPreparation(
            experiment_id=uuid4(), created_at=now, status="prepared", stage="create_task",
            case=ExperimentCase(case_id="sample", case_version="v1", task_type="bug_fix",
                user_request="fix", repository_commit="a" * 40, editable_files=["task_list.py"],
                protected_test_files=["tests/test_task_list.py"], test_profile="python-basic"),
            run_config=AgentRunConfig(retrieval_policy="vector"), repository_id=uuid4(),
            task_id=uuid4(), workspace_path=str(self.root / "workspace"),
            protected_test_file_hashes={"tests/test_task_list.py": "c" * 64},
        )
        self.preparation_path.write_text(self.preparation.model_dump_json(), encoding="utf-8")
        self.candidate = TaskFileEditRead(
            task_id=self.preparation.task_id, repository_id=self.preparation.repository_id,
            base_file_hash="b" * 64,
            proposal=FileEditProposal(file_path="task_list.py", summary="fix", content="value = 1\n"),
        )
        self.artifact = ExperimentEditCandidate(
            experiment_id=self.preparation.experiment_id, created_at=now, candidate=self.candidate,
        )
        self.candidate_path = self.root / "input-candidate.json"
        self.candidate_path.write_text(self.artifact.model_dump_json(), encoding="utf-8")
        self.run = TestRunRead(
            id=uuid4(), task_id=self.preparation.task_id, status="finished", image="test-image",
            timeout_seconds=120, started_at=now, completed_at=now, exit_code=0, timed_out=False,
            stdout="8 passed", stderr="", stdout_truncated=False, stderr_truncated=False,
            error=None, snapshot_hash="d" * 64,
        )
        self.completed = TaskRead(
            id=self.preparation.task_id, repository_id=self.preparation.repository_id,
            user_request="fix", task_type="plan", status="completed", created_at=now,
            started_at=now, completed_at=now, result=None, error=None, review_decision="approved",
            review_comment=None, reviewed_at=now, run_config=self.preparation.run_config,
        )
        self.report = TaskExecutionReport(
            task=self.completed, completion_event_sequence=10, test_run=self.run, final_diff=None,
        )
        self.mocks = {}
        for action, function, result in (
            ("generate", "generate_experiment_file_edit", self.candidate),
            ("apply", "apply_experiment_file_edit", WorkspaceWriteResult("task_list.py", False, 10)),
            ("test", "run_experiment_tests", self.run),
            ("complete", "complete_experiment", self.completed),
            ("report", "read_experiment_report", self.report),
        ):
            self.mocks[action] = self.enterContext(patch.object(cli.service, function, return_value=result))
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def invoke(self, action, *options):
        with patch.object(cli.sys, "argv", ["execute_experiment", action,
                          "--preparation", str(self.preparation_path), *options]), \
                redirect_stdout(self.stdout), redirect_stderr(self.stderr):
            cli.main()

    def records(self, filename):
        return sorted((self.root / "operations").glob(f"*/{filename}"))

    def payload(self, filename):
        paths = self.records(filename)
        self.assertEqual(len(paths), 1)
        return json.loads(paths[0].read_text(encoding="utf-8"))

    def assert_only_called(self, action, count=1):
        for name, mock in self.mocks.items():
            self.assertEqual(mock.call_count, count if name == action else 0, name)

    def fail_save(self, filename):
        original = cli.save_new_json

        def save(path, payload):
            if path.name == filename:
                raise OSError("simulated disk failure")
            original(path, payload)

        return patch.object(cli, "save_new_json", side_effect=save)

    def test_invalid_arguments_never_start_business_operations(self):
        for action, options in (
            ("generate", ("--file-path", "task_list.py")),
            ("generate", ("--allow-model",)),
            ("apply", ("--candidate", str(self.candidate_path))),
            ("apply", ("--confirm-apply",)),
            ("complete", ()),
            ("test", ("--allow-model",)),
            ("report", ("--confirm-apply",)),
        ):
            with self.subTest(action=action, options=options), self.assertRaises(SystemExit) as raised:
                self.invoke(action, *options)
            self.assertEqual(raised.exception.code, 2)
        for mock in self.mocks.values():
            mock.assert_not_called()
        self.assertFalse((self.root / "operations").exists())

    def test_generate_saves_full_candidate_without_applying_or_overwriting(self):
        self.invoke("generate", "--file-path", "task_list.py", "--allow-model")
        self.assert_only_called("generate")
        saved = ExperimentEditCandidate.model_validate(self.payload("candidate.json"))
        self.assertEqual(saved.experiment_id, self.preparation.experiment_id)
        self.assertEqual(saved.candidate, self.candidate)
        first = self.records("candidate.json")[0]
        original = first.read_bytes()
        # 两次显式操作产生不同目录；这不是失败后的自动重试。
        self.invoke("generate", "--file-path", "task_list.py", "--allow-model")
        self.assertEqual(len(self.records("candidate.json")), 2)
        self.assertEqual(first.read_bytes(), original)
        self.assert_only_called("generate", 2)

    def test_apply_requires_confirmation_and_saves_write_result(self):
        self.invoke("apply", "--candidate", str(self.candidate_path), "--confirm-apply")
        self.assert_only_called("apply")
        self.mocks["apply"].assert_called_once_with(self.preparation, artifact=self.artifact)
        saved = self.payload("apply-result.json")
        self.assertEqual(saved["task_id"], str(self.preparation.task_id))
        self.assertEqual(saved["result"], {"file_path": "task_list.py", "created": False, "bytes_written": 10})

    def test_failed_test_is_saved_before_exit_without_completing(self):
        self.mocks["test"].return_value = self.run.model_copy(update={"exit_code": 1, "stdout": "1 failed"})
        with self.assertRaises(SystemExit) as raised:
            self.invoke("test")
        self.assertEqual(raised.exception.code, 1)
        saved = self.payload("test-result.json")["test_run"]
        self.assertEqual(saved["id"], str(self.run.id))
        self.assertEqual(saved["exit_code"], 1)
        self.assertEqual(self.records("error.json"), [])
        self.assert_only_called("test")

    def test_complete_passes_explicit_id_without_retesting(self):
        self.invoke("complete", "--test-run-id", str(self.run.id))
        self.mocks["complete"].assert_called_once_with(self.preparation, test_run_id=self.run.id)
        self.assertEqual(self.payload("complete-result.json")["test_run_id"], str(self.run.id))
        self.assert_only_called("complete")

    def test_request_save_failure_stops_all_side_effects(self):
        with self.fail_save("request.json"), self.assertRaises(SystemExit) as raised:
            self.invoke("generate", "--file-path", "task_list.py", "--allow-model")
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.payload("error.json")["stage"], "保存请求记录")
        for mock in self.mocks.values():
            mock.assert_not_called()

    def test_result_save_failure_never_repeats_business_operation(self):
        for action, options, filename, stage in (
            ("generate", ("--file-path", "task_list.py", "--allow-model"), "candidate.json", "保存候选修改"),
            ("apply", ("--candidate", str(self.candidate_path), "--confirm-apply"), "apply-result.json", "保存应用结果"),
            ("test", (), "test-result.json", "保存测试结果"),
            ("complete", ("--test-run-id", str(self.run.id)), "complete-result.json", "保存完成结果"),
        ):
            for mock in self.mocks.values():
                mock.reset_mock()
            before = set(self.records("error.json"))
            with self.subTest(action=action), self.fail_save(filename), self.assertRaises(SystemExit) as raised:
                self.invoke(action, *options)
            self.assertEqual(raised.exception.code, 2)
            self.assert_only_called(action)
            new_errors = set(self.records("error.json")) - before
            self.assertEqual(len(new_errors), 1)
            error = json.loads(new_errors.pop().read_text(encoding="utf-8"))
            self.assertEqual(error["stage"], stage)
            self.assertEqual(error["error_type"], "OSError")

    def test_model_timeout_is_recorded_without_retry(self):
        self.mocks["generate"].side_effect = TimeoutError("model timeout")
        with self.assertRaises(SystemExit) as raised:
            self.invoke("generate", "--file-path", "task_list.py", "--allow-model")
        self.assertEqual(raised.exception.code, 2)
        self.assert_only_called("generate")
        self.assertEqual(self.payload("error.json")["stage"], "生成候选修改")

    def test_report_export_retry_only_reads_history(self):
        with patch.object(cli, "export_report", side_effect=OSError("disk failure")), \
                self.assertRaises(SystemExit) as raised:
            self.invoke("report")
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.payload("error.json")["stage"], "导出实验报告")
        self.invoke("report")
        self.assert_only_called("report", 2)
        result = self.payload("report-result.json")
        self.assertEqual(result["experiment_id"], str(self.preparation.experiment_id))
        self.assertEqual(result["test_run_id"], str(self.run.id))
        exported = TaskExecutionReport.model_validate_json(Path(result["json_path"]).read_text(encoding="utf-8"))
        self.assertEqual(exported, self.report)
        markdown = Path(result["markdown_path"]).read_text(encoding="utf-8")
        self.assertIn(str(self.run.id), markdown)
