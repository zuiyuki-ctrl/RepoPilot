import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.routes import tasks
from backend.app.core.exceptions import (
    RepositoryBusyError,
    SandboxPreparationError,
    TaskExecutionError,
    TaskStateConflictError,
)
from backend.app.schemas.task import TaskRead


class TaskCompletionRouteTests(unittest.TestCase):
    def setUp(self):
        self.task_id = UUID("00000000-0000-0000-0000-000000000301")
        self.test_run_id = UUID("00000000-0000-0000-0000-000000000401")
        self.url = f"/api/v1/tasks/{self.task_id}/complete"
        self.body = {"test_run_id": str(self.test_run_id)}
        app = FastAPI()
        app.include_router(tasks.router)
        self.client = self.enterContext(TestClient(app))
        self.complete = self.enterContext(
            patch.object(tasks.task_completion_service, "complete_plan_task")
        )

    # 验证请求中的测试 ID 以 UUID 传给服务，并按 TaskRead 序列化响应。
    def test_success_returns_task(self):
        now = datetime.now(timezone.utc)
        result = TaskRead(
            id=self.task_id,
            repository_id=UUID("00000000-0000-0000-0000-000000000001"),
            user_request="修复示例",
            task_type="plan",
            status="completed",
            created_at=now,
            started_at=now,
            completed_at=now,
            result=None,
            error=None,
            review_decision="approved",
            review_comment=None,
            reviewed_at=now,
        )
        self.complete.return_value = result

        response = self.client.post(self.url, json=self.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), result.model_dump(mode="json"))
        self.complete.assert_called_once_with(self.task_id, test_run_id=self.test_run_id)

    def test_missing_task_returns_404(self):
        self.complete.return_value = None
        response = self.client.post(self.url, json=self.body)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Task not found"})

    # 服务错误返回固定说明，避免把内部异常内容直接暴露到响应中。
    def test_service_error_mapping(self):
        cases = [
            (TaskStateConflictError, 409, "Task state or test result does not allow completion"),
            (RepositoryBusyError, 409, "Repository is busy"),
            (SandboxPreparationError, 503, "Current workspace snapshot is unavailable"),
            (SQLAlchemyError, 503, "Database unavailable"),
            (TaskExecutionError, 500, "Stored plan, test or event data is invalid"),
        ]
        for error_type, status, detail in cases:
            with self.subTest(error=error_type.__name__):
                self.complete.side_effect = error_type("internal diagnostic")
                with patch.object(tasks.logger, "exception") as log:
                    response = self.client.post(self.url, json=self.body)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json(), {"detail": detail})
                if status >= 500:
                    log.assert_called_once()
                else:
                    log.assert_not_called()

    def test_invalid_request_does_not_call_service(self):
        for body in ({}, {"test_run_id": "invalid"}):
            with self.subTest(body=body):
                response = self.client.post(self.url, json=body)
                self.assertEqual(response.status_code, 422)
        self.complete.assert_not_called()
