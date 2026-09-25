import unittest
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from backend.app.core.exceptions import TaskExecutionError, TaskStateConflictError
from backend.app.schemas.task import TaskPlanReviewRequest, TaskRead
from backend.app.services import task_service


# 只测试计划审核的服务层行为，不连接数据库，也不真正启动并发线程。
class TaskPlanReviewTests(unittest.TestCase):
    def setUp(self):
        self.task_id = UUID("00000000-0000-0000-0000-000000000101")
        self.repository_id = UUID("00000000-0000-0000-0000-000000000001")
        self.reviewed_at = datetime(2026, 9, 25, 3, 0, tzinfo=timezone.utc)
        self.session = Mock(name="session")

        session_patch = patch.object(task_service, "SessionLocal")
        self.session_local = session_patch.start()
        self.addCleanup(session_patch.stop)
        self.session_local.begin.side_effect = lambda: nullcontext(self.session)

        get_task_patch = patch.object(task_service, "get_task_for_update")
        self.get_task_for_update = get_task_patch.start()
        self.addCleanup(get_task_patch.stop)

        save_review_patch = patch.object(task_service.task_repo, "save_plan_review")
        self.save_plan_review = save_review_patch.start()
        self.addCleanup(save_review_patch.stop)
        self.save_plan_review.side_effect = self.apply_review

        append_event_patch = patch.object(task_service.task_event_repo, "append_task_event")
        self.append_task_event = append_event_patch.start()
        self.addCleanup(append_event_patch.stop)

    def make_task(self, **overrides):
        values = {
            "id": self.task_id,
            "repository_id": self.repository_id,
            "user_request": "制定修改计划",
            "task_type": "plan",
            "status": "awaiting_review",
            "created_at": datetime(2026, 9, 25, 1, 0, tzinfo=timezone.utc),
            "started_at": datetime(2026, 9, 25, 1, 1, tzinfo=timezone.utc),
            "completed_at": None,
            "result": {
                "repository_id": str(self.repository_id),
                "plan": {
                    "summary": "修改实现并补充测试",
                    "steps": [
                        {
                            "id": 1,
                            "description": "修改目标实现",
                            "files": ["backend/app/example.py"],
                            "source_ids": ["S1"],
                            "verification": "运行单元测试",
                        }
                    ],
                },
            },
            "error": None,
            "review_decision": None,
            "review_comment": None,
            "reviewed_at": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def apply_review(self, session, task, *, decision, comment):
        self.assertIs(session, self.session)
        task.review_decision = decision
        task.review_comment = comment
        task.reviewed_at = self.reviewed_at
        task.status = decision
        task.completed_at = None if decision == "approved" else self.reviewed_at

    def review(self, task, *, decision="approved", comment=None):
        self.get_task_for_update.return_value = task
        request = TaskPlanReviewRequest(decision=decision, comment=comment)
        return task_service.review_task_plan(self.task_id, request)

    def test_awaiting_review_plan_can_be_approved(self):
        task = self.make_task()

        result = self.review(task, decision="approved", comment="  \n")

        self.assertIsInstance(result, TaskRead)
        self.assertEqual(result.status, "approved")
        self.assertIsNone(result.completed_at)
        self.assertEqual(result.review_decision, "approved")
        self.assertIsNone(result.review_comment)
        self.assertEqual(result.reviewed_at, self.reviewed_at)
        self.save_plan_review.assert_called_once_with(
            self.session,
            task,
            decision="approved",
            comment=None,
        )
        self.append_task_event.assert_called_once_with(
            self.session,
            task_id=self.task_id,
            event_type="HUMAN_APPROVED",
            node_name="task_service",
            message="Plan approved",
            payload={
                "step_id": "plan_review",
                "attempt": 1,
                "decision": "approved",
                "comment": None,
                "reviewed_at": self.reviewed_at.isoformat(),
            },
        )

    def test_awaiting_review_plan_can_be_rejected(self):
        task = self.make_task()

        result = self.review(
            task,
            decision="rejected",
            comment="  缺少回滚步骤。  ",
        )

        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.completed_at, self.reviewed_at)
        self.assertEqual(result.review_decision, "rejected")
        self.assertEqual(result.review_comment, "缺少回滚步骤。")
        self.save_plan_review.assert_called_once_with(
            self.session,
            task,
            decision="rejected",
            comment="缺少回滚步骤。",
        )
        event_call = self.append_task_event.call_args
        self.assertEqual(event_call.kwargs["event_type"], "HUMAN_REJECTED")
        self.assertEqual(event_call.kwargs["message"], "Plan rejected")
        self.assertEqual(event_call.kwargs["payload"]["comment"], "缺少回滚步骤。")

    def test_invalid_task_states_are_rejected(self):
        cases = (
            ("question task", {"task_type": "question"}),
            ("completed plan", {"status": "completed"}),
            ("running plan", {"status": "running"}),
            ("reviewed plan", {"review_decision": "approved"}),
        )

        for name, overrides in cases:
            with self.subTest(name=name):
                self.save_plan_review.reset_mock()
                self.append_task_event.reset_mock()
                task = self.make_task(**overrides)

                with self.assertRaises(TaskStateConflictError):
                    self.review(task)

                self.save_plan_review.assert_not_called()
                self.append_task_event.assert_not_called()

    def test_corrupt_stored_plan_does_not_save_review(self):
        task = self.make_task(result={"not": "a TaskPlanResult"})

        with self.assertRaises(TaskExecutionError):
            self.review(task)

        self.save_plan_review.assert_not_called()
        self.append_task_event.assert_not_called()

    def test_second_review_returns_state_conflict(self):
        task = self.make_task()

        first_result = self.review(task, decision="approved")
        self.assertEqual(first_result.review_decision, "approved")

        with self.assertRaises(TaskStateConflictError):
            self.review(task, decision="rejected", comment="改变决定")

        self.assertEqual(self.save_plan_review.call_count, 1)
        self.assertEqual(self.append_task_event.call_count, 1)


if __name__ == "__main__":
    unittest.main()
