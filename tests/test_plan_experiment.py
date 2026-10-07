from datetime import datetime, timezone
import io
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx

from backend.app.schemas.experiment import ExperimentCase, ExperimentPreparation
from backend.app.schemas.run_config import AgentRunConfig
from backend.app.schemas.task import TaskRead, TaskPlanResult
from scripts import plan_experiment as script


class PlanExperimentTests(unittest.TestCase):
    def setUp(self):
        self.preparation = ExperimentPreparation(
            experiment_id=uuid4(), created_at=datetime.now(timezone.utc),
            case=ExperimentCase(case_id="sample", case_version="v1", task_type="bug_fix",
                user_request=" fix ", repository_commit="a" * 40, editable_files=["task_list.py"],
                protected_test_files=["tests/test_task_list.py"], test_profile="python-basic"),
            run_config=AgentRunConfig(retrieval_policy="vector"), status="prepared", stage="create_task",
            repository_id=uuid4(), task_id=uuid4(), workspace_path="D:/workspace",
            protected_test_file_hashes={"tests/test_task_list.py": "hash"},
        )
        self.task = TaskRead(id=self.preparation.task_id, repository_id=self.preparation.repository_id,
            user_request="fix", task_type="plan", status="created", created_at=datetime.now(timezone.utc),
            started_at=None, completed_at=None, result=None, error=None, review_decision=None,
            review_comment=None, reviewed_at=None, run_config=self.preparation.run_config)
        self.repository = dict(id=str(self.preparation.repository_id), name="sample", source_path="D:/source",
            workspace_path=self.preparation.workspace_path, status="created", git_branch=None,
            commit_hash=self.preparation.case.repository_commit, language="python",
            created_at=self.task.created_at.isoformat(), updated_at=self.task.created_at.isoformat(),
            indexed_at=None, test_profile=self.preparation.case.test_profile)
        self.requests = []

    def planned_task(self, files):
        result = TaskPlanResult.model_validate(dict(repository_id=self.preparation.repository_id,
            plan=dict(summary="fix", steps=[dict(id=1, description="fix", files=files,
                source_ids=["chunk"], verification="pytest")])))
        return self.task.model_copy(update={"status": "awaiting_review", "result": result})

    def client(self, *, task=None, run_task=None, run_error=None, repository=None):
        def handler(request):
            self.requests.append(request)
            if request.method == "POST":
                if run_error:
                    raise run_error
                return httpx.Response(200, json=run_task.model_dump(mode="json"))
            if "/repositories/" in request.url.path:
                return httpx.Response(200, json=repository or self.repository)
            return httpx.Response(200, json=(task or self.task).model_dump(mode="json"))
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_scope_is_exact_and_preserves_original_plan(self):
        files = ["task_list.py", "Task_list.py", "./task_list.py", "tests/test_task_list.py", "Task_list.py"]
        task = self.planned_task(files)
        before = task.model_dump(mode="json")
        inspection = script.inspect_task_plan(self.preparation, task=task)
        self.assertEqual(inspection.scope_status, "invalid")
        self.assertEqual(inspection.outside_scope_files,
            ["./task_list.py", "Task_list.py", "tests/test_task_list.py"])
        self.assertEqual(task.model_dump(mode="json"), before)
        self.assertEqual(inspection.task.model_dump(mode="json"), before)
        valid = script.inspect_task_plan(self.preparation, task=self.planned_task(["task_list.py"]))
        self.assertEqual(valid.scope_status, "valid")

    def test_inspection_rejects_wrong_identity_or_missing_plan(self):
        for update in ({"id": uuid4()}, {"repository_id": uuid4()}, {"status": "awaiting_review"}):
            with self.subTest(update=update), self.assertRaises(RuntimeError):
                script.inspect_task_plan(self.preparation, task=self.task.model_copy(update=update))
        task = self.planned_task(["task_list.py"])
        task.result.repository_id = uuid4()
        with self.assertRaises(RuntimeError):
            script.inspect_task_plan(self.preparation, task=task)

    def test_refresh_running_and_failed_never_posts(self):
        for status in ("running", "failed"):
            with self.subTest(status=status), self.client(task=self.task.model_copy(
                    update={"status": status, "error": "controlled failure"})) as client:
                inspection = script.run_or_refresh_plan(client, base_url="http://test/",
                    preparation=self.preparation, run=False)
            self.assertEqual(inspection.task_status, status)
            self.assertEqual(inspection.scope_status, "not_checked")
            self.assertEqual(inspection.task.error, "controlled failure")
        self.assertTrue(all(request.method == "GET" for request in self.requests))

    def test_run_posts_once_and_checks_response(self):
        with self.client(run_task=self.planned_task(["task_list.py"])) as client:
            inspection = script.run_or_refresh_plan(client, base_url="http://test",
                preparation=self.preparation, run=True)
        self.assertEqual(inspection.task_status, "awaiting_review")
        self.assertEqual([r.method for r in self.requests], ["GET", "GET", "POST"])
        self.assertEqual(self.requests[-1].url.path, f"/api/v1/tasks/{self.task.id}/run")

    def test_run_rejects_noncreated_and_timeout_is_not_retried(self):
        with self.client(task=self.task.model_copy(update={"status": "running"})) as client:
            with self.assertRaisesRegex(RuntimeError, "read-only refresh"):
                script.run_or_refresh_plan(client, base_url="http://test", preparation=self.preparation, run=True)
        self.assertTrue(all(r.method == "GET" for r in self.requests))
        self.requests.clear()
        with self.client(run_error=httpx.ReadTimeout("timeout")) as client:
            with self.assertRaises(httpx.ReadTimeout):
                script.run_or_refresh_plan(client, base_url="http://test", preparation=self.preparation, run=True)
        self.assertEqual(sum(r.method == "POST" for r in self.requests), 1)

    def test_association_mismatch_prevents_post(self):
        for field, value in (("id", uuid4()), ("repository_id", uuid4()), ("task_type", "question"),
                             ("run_config", AgentRunConfig(retrieval_policy="hybrid")), ("user_request", "other")):
            with self.subTest(field=field), self.client(task=self.task.model_copy(update={field: value})) as client:
                with self.assertRaisesRegex(RuntimeError, field):
                    script.run_or_refresh_plan(client, base_url="http://test", preparation=self.preparation, run=True)
        for field, value in (("id", str(uuid4())), ("commit_hash", "b" * 40),
                             ("workspace_path", "D:/other"), ("test_profile", "other")):
            with self.subTest(field=field), self.client(repository={**self.repository, field: value}) as client:
                with self.assertRaisesRegex(RuntimeError, field):
                    script.run_or_refresh_plan(client, base_url="http://test", preparation=self.preparation, run=True)
        self.assertTrue(all(r.method == "GET" for r in self.requests))

    def test_run_response_must_match_and_await_review(self):
        planned = self.planned_task(["task_list.py"])
        for update in ({"id": uuid4()}, {"repository_id": uuid4()},
                       {"run_config": AgentRunConfig(retrieval_policy="hybrid")}, {"status": "failed"}):
            self.requests.clear()
            with self.subTest(update=update), self.client(run_task=planned.model_copy(update=update)) as client:
                with self.assertRaises(RuntimeError):
                    script.run_or_refresh_plan(client, base_url="http://test", preparation=self.preparation, run=True)
            self.assertEqual(sum(r.method == "POST" for r in self.requests), 1)

    def test_http_error_is_not_retried(self):
        def handler(request):
            self.requests.append(request)
            if request.method == "POST":
                return httpx.Response(500, json={"detail": "Task execution failed"})
            if "/repositories/" in request.url.path:
                return httpx.Response(200, json=self.repository)
            return httpx.Response(200, json=self.task.model_dump(mode="json"))

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(httpx.HTTPStatusError):
                script.run_or_refresh_plan(client, base_url="http://test", preparation=self.preparation, run=True)
        self.assertEqual(sum(r.method == "POST" for r in self.requests), 1)

    def test_loading_and_unique_snapshot_files_leave_preparation_unchanged(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "preparation.json"
            original = self.preparation.model_dump_json()
            path.write_text(original, encoding="utf-8")
            self.assertEqual(script.load_prepared_experiment(path), self.preparation)
            inspection = script.inspect_task_plan(self.preparation, task=self.task)
            first = script.save_plan_inspection(inspection, output_dir=path.parent)
            second = script.save_plan_inspection(inspection, output_dir=path.parent)
            self.assertNotEqual(first, second)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            for update in ({"status": "error"}, {"task_id": None}, {"repository_id": None},
                           {"workspace_path": ""}, {"run_config": AgentRunConfig()}):
                path.write_text(self.preparation.model_copy(update=update).model_dump_json(), encoding="utf-8")
                with self.subTest(update=update), self.assertRaises(RuntimeError):
                    script.load_prepared_experiment(path)

    def test_cli_requires_model_authorization_before_client_creation(self):
        with patch.object(script.sys, "argv", ["plan_experiment", "--preparation", "missing.json", "--run"]), \
                patch.object(script.httpx, "Client") as client, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                script.main()
        self.assertEqual(raised.exception.code, 2)
        client.assert_not_called()
