import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from backend.app.core.exceptions import RetryBudgetExceededError, TaskExecutionError, TaskStateConflictError
from backend.app.services import reflection_service as service


class ReflectionBudgetTests(unittest.TestCase):
    def setUp(self):
        self.task_id = UUID(int=1)
        self.repository_id = UUID(int=2)
        self.task = SimpleNamespace(
            id=self.task_id, repository_id=self.repository_id, task_type="plan",
            status="executing", review_decision="approved", retry_count=1,
            max_retries=1, error=None, completed_at=None, user_request="修复筛选",
            result=dict(repository_id=str(self.repository_id), plan=dict(
                summary="修复筛选", steps=[dict(id=1, description="调整顺序",
                    files=["task_list.py"], source_ids=["S1"], verification="测试通过")]))
        )
        self.plan = deepcopy(self.task.result)
        self.payload = dict(step_id="run_tests", attempt=1, passed=False, exit_code=1,
            timed_out=False, stdout="1 failed", stderr="", stdout_truncated=False,
            stderr_truncated=False, sequence=8, schema_version=1, test_run_id=str(UUID(int=3)))
        self.events = {"TEST_EXECUTION_FINISHED": SimpleNamespace(sequence=8, payload=self.payload)}
        self.session = Mock()
        self.transaction = MagicMock()
        self.transaction.__enter__.return_value = self.session
        self.transaction.__exit__.return_value = False
        sessions = self.enterContext(patch.object(service, "SessionLocal"))
        sessions.begin.return_value = self.transaction
        self.get_task = self.enterContext(patch.object(service.task_repo, "get_task_for_update", return_value=self.task))
        self.enterContext(patch.object(service.task_event_repo, "get_latest_task_event_by_type",
            side_effect=lambda session, *, task_id, event_type: self.events.get(event_type)))
        self.append = self.enterContext(patch.object(service.task_event_repo, "append_task_event"))
        self.get_run = self.enterContext(patch.object(service.test_run_repo, "get_test_run",
            return_value=SimpleNamespace(status="finished", exit_code=1, timed_out=False)))
        self.snapshot = self.enterContext(patch.object(service, "check_test_run_snapshot",
            return_value=SimpleNamespace(is_current=True)))
        self.mark_failed = self.enterContext(patch.object(service.task_repo, "mark_plan_task_failed",
            wraps=service.task_repo.mark_plan_task_failed))
        self.mark_reflecting = self.enterContext(patch.object(service.task_repo, "mark_task_reflecting",
            wraps=service.task_repo.mark_task_reflecting))
        self.model = self.enterContext(patch.object(service, "generate_reflection_decision"))

    # 预算异常必须在事务正常退出之后才出现；真实状态修改方法仍执行，数据库会话模拟。
    def test_exhaustion_leaves_transaction_normally_before_raising(self):
        with self.assertRaisesRegex(RetryBudgetExceededError, "Task retry budget is exhausted"):
            service.run_task_reflection(self.task_id)
        self.transaction.__exit__.assert_called_once_with(None, None, None)
        self.assertEqual(self.task.status, "failed")
        self.assertEqual(self.task.result, self.plan)
        self.assertEqual(self.task.retry_count, 1)
        self.assertIsNotNone(self.task.completed_at)
        self.mark_reflecting.assert_not_called()
        self.model.assert_not_called()
        self.snapshot.assert_called_once()
        self.append.assert_called_once_with(self.session, task_id=self.task_id,
            event_type="TASK_FAILED", node_name="reflection_service",
            message=self.task.error, payload=dict(step_id="reflect", attempt=2,
                reason_code="retry_budget_exhausted", retry_count=1, max_retries=1,
                test_event_sequence=8, error=self.task.error))

    def assert_not_started_or_failed(self):
        self.mark_failed.assert_not_called()
        self.mark_reflecting.assert_not_called()
        self.append.assert_not_called()
        self.model.assert_not_called()
        self.assertEqual(self.task.status, "executing")

    def test_duplicate_reflection_is_rejected_before_budget_and_snapshot(self):
        self.events["REFLECTION_STARTED"] = SimpleNamespace(sequence=9)
        with self.assertRaises(TaskStateConflictError):
            service.run_task_reflection(self.task_id)
        self.snapshot.assert_not_called()
        self.assert_not_started_or_failed()

    def test_stale_or_missing_snapshot_does_not_fail_task(self):
        for current in (False, None):
            with self.subTest(current=current):
                self.snapshot.return_value.is_current = current
                with self.assertRaises(TaskStateConflictError):
                    service.run_task_reflection(self.task_id)
        self.assert_not_started_or_failed()

    def test_inconsistent_test_record_does_not_fail_task(self):
        self.get_run.return_value.exit_code = 0
        with self.assertRaises(TaskExecutionError):
            service.run_task_reflection(self.task_id)
        self.snapshot.assert_not_called()
        self.assert_not_started_or_failed()

    def test_newer_activity_requires_retesting(self):
        for event_type in ("TEST_EXECUTION_STARTED", "TEST_EXECUTION_FAILED", "FILE_MODIFIED"):
            with self.subTest(event_type=event_type):
                self.events[event_type] = SimpleNamespace(sequence=9)
                with self.assertRaises(TaskStateConflictError):
                    service.begin_task_reflection(self.task_id)
                del self.events[event_type]
        self.snapshot.assert_not_called()
        self.assert_not_started_or_failed()

    def test_passed_result_does_not_fail_task(self):
        self.payload.update(passed=True, exit_code=0)
        with self.assertRaises(TaskStateConflictError):
            service.begin_task_reflection(self.task_id)
        self.assert_not_started_or_failed()

    def test_available_budget_returns_context(self):
        self.task.retry_count = 0
        self.events["REFLECTION_STARTED"] = SimpleNamespace(sequence=5)
        context = service.begin_task_reflection(self.task_id)
        self.assertEqual(context.retry_count, 1)
        self.assertEqual(context.test_event_sequence, 8)
        self.assertEqual(context.plan.model_dump(mode="json"), self.plan)
        self.assertEqual(self.task.status, "reflecting")
        self.mark_failed.assert_not_called()
        self.assertEqual(self.append.call_args.kwargs["event_type"], "REFLECTION_STARTED")
        self.transaction.__exit__.assert_called_once_with(None, None, None)

    def test_event_write_failure_is_not_reported_as_budget_exhaustion(self):
        error = SQLAlchemyError("write failed")
        self.append.side_effect = error
        with self.assertRaises(SQLAlchemyError) as raised:
            service.begin_task_reflection(self.task_id)
        self.assertIs(raised.exception, error)
        self.assertIs(self.transaction.__exit__.call_args.args[1], error)

    def test_commit_failure_is_not_reported_as_budget_exhaustion(self):
        error = SQLAlchemyError("commit failed")
        self.transaction.__exit__.side_effect = error
        with self.assertRaises(SQLAlchemyError) as raised:
            service.begin_task_reflection(self.task_id)
        self.assertIs(raised.exception, error)

    def test_missing_task_returns_none(self):
        self.get_task.return_value = None
        self.assertIsNone(service.begin_task_reflection(self.task_id))
        self.assert_not_started_or_failed()
