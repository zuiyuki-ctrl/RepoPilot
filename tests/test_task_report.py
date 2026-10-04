import unittest
from copy import deepcopy
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.routes import tasks
from backend.app.core.exceptions import TaskExecutionError
from backend.app.services import task_report_service as service


class TaskReportTests(unittest.TestCase):
    def setUp(self):
        self.task_id = UUID(int=1)
        self.repository_id = UUID(int=2)
        self.run_id = UUID(int=3)
        now = datetime.now(timezone.utc)
        self.task = SimpleNamespace(
            id=self.task_id, repository_id=self.repository_id,
            user_request="修复示例", task_type="plan", status="completed",
            created_at=now, started_at=now, completed_at=now,
            result=None, error=None, review_decision="approved",
            review_comment=None, reviewed_at=now,
        )
        self.run = SimpleNamespace(
            id=self.run_id, task_id=self.task_id, status="finished",
            image="test-image", timeout_seconds=60, started_at=now,
            completed_at=now, exit_code=0, timed_out=False,
            stdout="1 passed", stderr="", stdout_truncated=False,
            stderr_truncated=False, error=None, snapshot_hash="a" * 64,
        )
        self.diff = dict(
            task_id=str(self.task_id), repository_id=str(self.repository_id),
            diff="saved diff", changed_files=["example.py"],
            untracked_files=[], truncated=False,
        )
        self.event = SimpleNamespace(
            sequence=10,
            payload={"test_run_id": str(self.run_id), "final_diff": self.diff},
        )
        self.session = Mock()
        sessions = self.enterContext(patch.object(service, "SessionLocal"))
        sessions.begin.side_effect = lambda: nullcontext(self.session)
        self.get_task = self.enterContext(patch.object(
            service.task_repo, "get_task", return_value=self.task,
        ))
        self.get_event = self.enterContext(patch.object(
            service.task_event_repo, "get_latest_task_event_by_type", return_value=self.event,
        ))
        self.get_run = self.enterContext(patch.object(
            service.test_run_repo, "get_test_run", return_value=self.run,
        ))
        app = FastAPI()
        app.include_router(tasks.router)
        self.client = self.enterContext(TestClient(app))
        self.url = f"/api/v1/tasks/{self.task_id}/report"

    # 使用真实报告服务及响应序列化，数据库查询全部模拟。
    def test_report_uses_completion_event_evidence(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["final_diff"], self.diff)
        self.assertEqual(data["completion_event_sequence"], 10)
        self.assertEqual(data["test_run"]["id"], str(self.run_id))
        self.assertEqual(data["diff_scope"], "workspace_against_head")
        self.get_run.assert_called_once_with(
            self.session, task_id=self.task_id, test_run_id=self.run_id,
        )

    def test_legacy_report_without_diff(self):
        del self.event.payload["final_diff"]
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["final_diff"])

    def test_missing_task_returns_404(self):
        self.get_task.return_value = None
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.get_event.assert_not_called()

    def test_ineligible_task_returns_409(self):
        for field, value in (("status", "executing"), ("task_type", "question")):
            with self.subTest(field=field), patch.object(self.task, field, value):
                self.assertEqual(self.client.get(self.url).status_code, 409)
        self.get_event.assert_not_called()

    def test_invalid_test_run_id_is_rejected(self):
        for value in (None, 123, "not-a-uuid"):
            with self.subTest(value=value):
                self.event.payload["test_run_id"] = value
                with self.assertRaises(TaskExecutionError):
                    service.get_task_execution_report(self.task_id)
        self.get_run.assert_not_called()

    def test_unusable_test_run_is_rejected(self):
        for field, value in (("status", "running"), ("exit_code", 1), ("timed_out", True)):
            with self.subTest(field=field), patch.object(self.run, field, value):
                with self.assertRaises(TaskExecutionError):
                    service.get_task_execution_report(self.task_id)
        self.get_run.return_value = None
        with self.assertRaises(TaskExecutionError):
            service.get_task_execution_report(self.task_id)

    def test_invalid_diff_is_rejected(self):
        for value in ({}, {**self.diff, "task_id": str(UUID(int=9))},
                      {**self.diff, "repository_id": str(UUID(int=9))}):
            with self.subTest(value=value):
                self.event.payload["final_diff"] = value
                with self.assertRaises(TaskExecutionError):
                    service.get_task_execution_report(self.task_id)

    def test_missing_or_invalid_event_returns_500(self):
        for event in (None, SimpleNamespace(payload=[])):
            with self.subTest(event=event), patch.object(tasks.logger, "exception") as log:
                self.get_event.return_value = event
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, 500)
                self.assertEqual(response.json(), {"detail": "Stored task report data is invalid"})
                log.assert_called_once()

    def test_database_error_returns_503(self):
        self.get_task.side_effect = SQLAlchemyError("internal diagnostic")
        with patch.object(tasks.logger, "exception") as log:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Database unavailable"})
        log.assert_called_once()

    # 构造反思停止及其指定的历史测试；查询均使用已有会话。
    def prepare_failed_report(self):
        self.task.status = "failed"
        self.task.error = "证据不足，停止修复"
        self.run.exit_code = 1
        self.failure_events = {
            "TASK_FAILED": SimpleNamespace(event_type="TASK_FAILED", sequence=4, payload={}),
            "REFLECTION_FINISHED": SimpleNamespace(
                event_type="REFLECTION_FINISHED", sequence=10,
                payload=dict(step_id="reflect", attempt=1, test_event_sequence=8,
                    decision=dict(diagnosis="无法确认修复方向", should_retry=False, actions=[]),
                    sequence=10, schema_version=1),
            ),
        }
        self.get_event.side_effect = lambda session, *, task_id, event_type: self.failure_events.get(event_type)
        self.test_event = SimpleNamespace(event_type="TEST_EXECUTION_FINISHED", sequence=8,
            payload=dict(step_id="run_tests", attempt=1, passed=False, exit_code=1,
                timed_out=False, stdout="1 failed", stderr="", stdout_truncated=False,
                stderr_truncated=False, sequence=8, schema_version=1, test_run_id=str(self.run_id)))
        self.get_by_sequence = self.enterContext(patch.object(
            service.task_event_repo, "get_task_event_by_sequence", return_value=self.test_event))

    def test_reflection_failure_returns_historical_report(self):
        self.prepare_failed_report()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertEqual(report["failure"], dict(reason=self.task.error, event_sequence=10,
            event_type="REFLECTION_FINISHED",
            reflection=self.failure_events["REFLECTION_FINISHED"].payload["decision"]))
        self.assertEqual(report["test_run"]["id"], str(self.run_id))
        self.assertIsNone(report["final_diff"])
        self.assertIsNone(report["completion_event_sequence"])
        self.get_by_sequence.assert_called_once_with(self.session, task_id=self.task_id, sequence=8)
        self.get_run.assert_called_once_with(self.session, task_id=self.task_id, test_run_id=self.run_id)
        self.assertEqual(self.task.status, "failed")

    def test_task_failed_report_does_not_guess_test_evidence(self):
        self.prepare_failed_report()
        for reflection_exists in (True, False):
            with self.subTest(reflection_exists=reflection_exists):
                self.failure_events["TASK_FAILED"].sequence = 12
                if not reflection_exists:
                    self.failure_events.pop("REFLECTION_FINISHED")
                report = service.get_task_execution_report(self.task_id)
                self.assertEqual(report.failure.event_sequence, 12)
                self.assertEqual(report.failure.event_type, "TASK_FAILED")
                self.assertEqual(report.failure.reason, self.task.error)
                self.assertIsNone(report.failure.reflection)
                self.assertIsNone(report.test_run)
                self.assertIsNone(report.final_diff)
                self.assertIsNone(report.completion_event_sequence)
        self.get_by_sequence.assert_not_called()
        self.get_run.assert_not_called()

    def test_historical_reflection_without_run_id(self):
        self.prepare_failed_report()
        self.failure_events.pop("TASK_FAILED")
        del self.test_event.payload["test_run_id"]
        report = service.get_task_execution_report(self.task_id)
        self.assertIsNone(report.test_run)
        self.assertFalse(report.failure.reflection.should_retry)
        self.get_run.assert_not_called()

    def test_failed_report_requires_reason_and_event(self):
        self.prepare_failed_report()
        for reason in (None, "", "   ", 42):
            with self.subTest(reason=reason), patch.object(self.task, "error", reason):
                with self.assertRaises(TaskExecutionError):
                    service.get_task_execution_report(self.task_id)
        self.get_event.assert_not_called()
        self.failure_events.clear()
        with self.assertRaises(TaskExecutionError):
            service.get_task_execution_report(self.task_id)

    def test_invalid_stopping_reflection_is_rejected(self):
        self.prepare_failed_report()
        event = self.failure_events["REFLECTION_FINISHED"]
        original = deepcopy(event.payload)
        cases = [None, {}, {**original, "sequence": 9},
                 {**original, "test_event_sequence": 10},
                 {**original, "test_event_sequence": 11},
                 {**original, "decision": dict(diagnosis="继续修复", should_retry=True,
                     actions=[dict(file_path="example.py", instruction="修正返回值")])}]
        for payload in cases:
            with self.subTest(payload=payload):
                event.payload = payload
                with self.assertRaises(TaskExecutionError):
                    service.get_task_execution_report(self.task_id)
        self.get_by_sequence.assert_not_called()

    def test_reflection_requires_exact_finished_test_event(self):
        self.prepare_failed_report()
        for event in (None, SimpleNamespace(event_type="TEST_EXECUTION_FAILED", sequence=8),
                      SimpleNamespace(event_type="TEST_EXECUTION_FINISHED", sequence=7)):
            with self.subTest(event=event):
                self.get_by_sequence.return_value = event
                with self.assertRaises(TaskExecutionError):
                    service.get_task_execution_report(self.task_id)
        self.get_run.assert_not_called()

    def test_invalid_reflection_test_payload_is_rejected(self):
        self.prepare_failed_report()
        original = deepcopy(self.test_event.payload)
        cases = [None, {}, {**original, "sequence": 7}, {**original, "passed": True},
                 {**original, "exit_code": 0, "passed": True},
                 {**original, "test_run_id": "bad-id"}, {**original, "test_run_id": 123}]
        for payload in cases:
            with self.subTest(payload=payload):
                self.test_event.payload = payload
                with self.assertRaises(TaskExecutionError):
                    service.get_task_execution_report(self.task_id)
        self.get_run.assert_not_called()

    def test_reflection_test_run_must_match_event(self):
        self.prepare_failed_report()
        for field, value in (("status", "running"), ("exit_code", 0),
                             ("exit_code", 2), ("timed_out", True)):
            with self.subTest(field=field, value=value), patch.object(self.run, field, value):
                with self.assertRaises(TaskExecutionError):
                    service.get_task_execution_report(self.task_id)
        self.get_run.return_value = None
        with self.assertRaises(TaskExecutionError):
            service.get_task_execution_report(self.task_id)

    def test_timed_out_test_can_support_stopping_reflection(self):
        self.prepare_failed_report()
        self.run.exit_code = None
        self.run.timed_out = True
        self.test_event.payload.update(exit_code=None, timed_out=True)
        report = service.get_task_execution_report(self.task_id)
        self.assertTrue(report.test_run.timed_out)

    def test_invalid_failed_task_schema_becomes_execution_error(self):
        self.prepare_failed_report()
        self.task.created_at = "bad-date"
        with self.assertRaises(TaskExecutionError):
            service.get_task_execution_report(self.task_id)

    def prepare_budget_failure(self):
        self.prepare_failed_report()
        self.failure_events["TASK_FAILED"].sequence = 12
        self.failure_events["TASK_FAILED"].payload = {
            "reason_code": "retry_budget_exhausted", "test_event_sequence": 8,
        }

    def test_budget_failure_reports_its_historical_test(self):
        self.prepare_budget_failure()
        report = service.get_task_execution_report(self.task_id)
        self.assertEqual(report.failure.event_type, "TASK_FAILED")
        self.assertEqual(report.failure.event_sequence, 12)
        self.assertIsNone(report.failure.reflection)
        self.assertIsNone(report.final_diff)
        self.assertEqual(report.test_run.id, self.run_id)
        self.get_by_sequence.assert_called_once_with(self.session, task_id=self.task_id, sequence=8)

    def test_budget_failure_requires_positive_integer_earlier_sequence(self):
        self.prepare_budget_failure()
        for sequence in (None, True, False, 0, -1, "8", 8.0, 12, 13):
            with self.subTest(sequence=sequence):
                self.failure_events["TASK_FAILED"].payload["test_event_sequence"] = sequence
                with self.assertRaises(TaskExecutionError):
                    service.get_task_execution_report(self.task_id)
        self.get_by_sequence.assert_not_called()

    def test_budget_failure_allows_legacy_test_without_run_id(self):
        self.prepare_budget_failure()
        del self.test_event.payload["test_run_id"]
        report = service.get_task_execution_report(self.task_id)
        self.assertIsNone(report.test_run)
        self.assertIsNone(report.failure.reflection)
        self.get_run.assert_not_called()

    def test_budget_failure_rejects_inconsistent_run(self):
        self.prepare_budget_failure()
        self.run.exit_code = 0
        with self.assertRaises(TaskExecutionError):
            service.get_task_execution_report(self.task_id)

    def test_task_failed_requires_dictionary_payload(self):
        self.prepare_budget_failure()
        for payload in (None, [], "bad payload"):
            with self.subTest(payload=payload):
                self.failure_events["TASK_FAILED"].payload = payload
                with self.assertRaises(TaskExecutionError):
                    service.get_task_execution_report(self.task_id)
