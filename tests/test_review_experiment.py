from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from pydantic import ValidationError

from backend.app.schemas.experiment import ExperimentCase, ExperimentPreparation
from backend.app.schemas.run_config import AgentRunConfig
from backend.app.schemas.task import TaskRead, TaskPlanResult
from scripts import review_experiment as script


class ReviewExperimentTests(unittest.TestCase):
    def setUp(self):
        self.preparation = ExperimentPreparation(
            experiment_id=uuid4(), created_at=datetime.now(timezone.utc),
            case=ExperimentCase(case_id="sample", case_version="v1", task_type="bug_fix",
                user_request="fix", repository_commit="a" * 40, editable_files=["task_list.py"],
                protected_test_files=["tests/test_task_list.py"], test_profile="python-basic"),
            run_config=AgentRunConfig(retrieval_policy="vector"), status="prepared", stage="create_task",
            repository_id=uuid4(), task_id=uuid4(), workspace_path="D:/workspace",
            protected_test_file_hashes={},
        )
        result = TaskPlanResult.model_validate(dict(repository_id=self.preparation.repository_id,
            plan=dict(summary="fix", steps=[dict(id=1, description="fix", files=["task_list.py"],
                source_ids=["chunk"], verification="pytest")])))
        self.task = TaskRead(id=self.preparation.task_id, repository_id=self.preparation.repository_id,
            user_request="fix", task_type="plan", status="awaiting_review", created_at=datetime.now(timezone.utc),
            started_at=None, completed_at=None, result=result, error=None, review_decision=None,
            review_comment=None, reviewed_at=None, run_config=self.preparation.run_config)
        self.fetch = self.enterContext(patch.object(script, "fetch_checked_task", return_value=self.task))
        self.requests = []

    def reviewed(self, decision="approved", **changes):
        return self.task.model_copy(update={"status": decision, "review_decision": decision,
            "reviewed_at": datetime.now(timezone.utc), **changes})

    def client(self, task=None, error=None, status_code=200):
        def handler(request):
            self.requests.append(request)
            if error is not None:
                raise error
            return httpx.Response(status_code, json=(task or self.reviewed()).model_dump(mode="json"))
        return httpx.Client(transport=httpx.MockTransport(handler))

    def review(self, client, decision="approved", comment=None):
        return script.review_experiment_plan(client, base_url="http://test/",
            preparation=self.preparation, decision=decision, comment=comment)

    def test_approval_posts_once_and_preserves_plan(self):
        before = self.task.model_dump(mode="json")
        with self.client() as client:
            inspection = self.review(client, comment=" checked ")
        self.assertEqual(inspection.task_status, "approved")
        self.assertEqual(inspection.scope_status, "valid")
        self.assertEqual(inspection.task.result, self.task.result)
        self.assertEqual(self.task.model_dump(mode="json"), before)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].method, "POST")
        self.assertEqual(self.requests[0].url.path, f"/api/v1/tasks/{self.task.id}/review")
        self.assertEqual(json.loads(self.requests[0].content), {"decision": "approved", "comment": "checked"})
        self.fetch.assert_called_once_with(client, base_url="http://test/", preparation=self.preparation)

    def test_outside_scope_blocks_approval_but_allows_rejection(self):
        self.task.result.plan.steps[0].files.append("tests/test_task_list.py")
        with self.client() as client:
            with self.assertRaisesRegex(RuntimeError, "tests/test_task_list.py"):
                self.review(client)
        self.assertEqual(self.requests, [])
        with self.client(task=self.reviewed("rejected")) as client:
            inspection = self.review(client, decision="rejected")
        self.assertEqual(inspection.task_status, "rejected")
        self.assertEqual(inspection.scope_status, "invalid")
        self.assertEqual(len(self.requests), 1)

    def test_invalid_input_is_checked_before_fetch(self):
        for kwargs in ({"decision": "failed"}, {"comment": "x" * 1001}):
            with self.subTest(kwargs=kwargs), self.client() as client:
                with self.assertRaises(ValidationError):
                    self.review(client, **kwargs)
        self.fetch.assert_not_called()
        self.assertEqual(self.requests, [])

    def test_existing_decision_or_wrong_status_blocks_post(self):
        for update in ({"status": "created"}, {"status": "approved"}, {"review_decision": "rejected"}):
            self.fetch.return_value = self.task.model_copy(update=update)
            with self.subTest(update=update), self.client() as client:
                with self.assertRaises(RuntimeError):
                    self.review(client)
        self.assertEqual(self.requests, [])

    def test_response_validation_rejects_changed_plan_and_association(self):
        changed_result = self.task.result.model_copy(deep=True)
        changed_result.plan.summary = "changed"
        for update in ({"id": uuid4()}, {"repository_id": uuid4()}, {"user_request": "other"},
                       {"run_config": AgentRunConfig(retrieval_policy="hybrid")},
                       {"status": "failed"}, {"review_decision": "rejected"},
                       {"reviewed_at": None}, {"result": changed_result}):
            self.requests.clear()
            with self.subTest(update=update), self.client(task=self.reviewed(**update)) as client:
                with self.assertRaises(RuntimeError):
                    self.review(client)
            self.assertEqual(len(self.requests), 1)

    def test_timeout_and_conflict_never_retry(self):
        for error, code, expected in ((httpx.ReadTimeout("timeout"), 200, httpx.TimeoutException),
                                       (None, 409, httpx.HTTPStatusError)):
            self.requests.clear()
            with self.client(error=error, status_code=code) as client:
                with self.assertRaises(expected):
                    self.review(client)
            self.assertEqual(len(self.requests), 1)

    def test_cli_recovery_messages(self):
        request = httpx.Request("POST", "http://test/review")
        conflict = httpx.HTTPStatusError("conflict", request=request,
            response=httpx.Response(409, request=request))
        inspection = script.inspect_task_plan(self.preparation, task=self.reviewed())
        for error, save_error, message in (
            (httpx.ReadTimeout("timeout"), None, "后端可能已经保存决定"),
            (conflict, None, "不重试"),
            (None, OSError("disk failed"), "失败发生在本地快照保存"),
        ):
            stderr = io.StringIO()
            with self.subTest(message=message), \
                    patch.object(script.sys, "argv", ["review_experiment", "--preparation", "preparation.json", "--decision", "approved"]), \
                    patch.object(script, "load_prepared_experiment", return_value=self.preparation), \
                    patch.object(script.httpx, "Client"), \
                    patch.object(script, "review_experiment_plan", return_value=inspection, side_effect=error) as review, \
                    patch.object(script, "save_plan_inspection", side_effect=save_error, return_value=Path("snapshot.json")) as save, \
                    redirect_stderr(stderr), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    script.main()
            self.assertEqual(raised.exception.code, 1)
            self.assertIn(message, stderr.getvalue())
            self.assertIn("scripts.plan_experiment", stderr.getvalue())
            review.assert_called_once()
            if error:
                save.assert_not_called()
            else:
                save.assert_called_once()
                self.assertIn("不要重新审批", stderr.getvalue())
