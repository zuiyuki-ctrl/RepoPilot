import unittest
from unittest.mock import patch
from uuid import UUID

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.routes import tasks
from backend.app.core.exceptions import (
    InvalidReflectionError,
    RetryBudgetExceededError,
    TaskExecutionError,
    TaskStateConflictError,
)
from backend.app.schemas.reflection import ReflectionDecision, ReflectionFileAction


class TaskReflectionRouteTests(unittest.TestCase):
    def setUp(self):
        self.task_id = UUID("00000000-0000-0000-0000-000000000301")
        self.url = f"/api/v1/tasks/{self.task_id}/reflect"
        app = FastAPI()
        app.include_router(tasks.router)
        self.client = self.enterContext(TestClient(app))
        self.run_reflection = self.enterContext(
            patch.object(tasks.reflection_service, "run_task_reflection")
        )

    # 重试和停止决策都应按响应 Schema 返回，路由不负责执行修复。
    def test_returns_reflection_decision(self):
        for should_retry in (True, False):
            with self.subTest(should_retry=should_retry):
                decision = ReflectionDecision(
                    diagnosis="测试断言失败" if should_retry else "证据不足",
                    should_retry=should_retry,
                    actions=[ReflectionFileAction(
                        file_path="app/example.py",
                        instruction="根据失败断言修正空输入时的返回值。",
                    )] if should_retry else [],
                )
                self.run_reflection.return_value = decision
                self.run_reflection.reset_mock()

                response = self.client.post(self.url)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {
                    "task_id": str(self.task_id),
                    "decision": decision.model_dump(mode="json"),
                })
                self.run_reflection.assert_called_once_with(self.task_id)

    def test_missing_task_returns_404(self):
        self.run_reflection.return_value = None

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Task not found"})

    # 验证 HTTP 错误契约，特别是 InvalidReflectionError 不应落入普通 ValueError 分支。
    def test_service_errors_return_fixed_details(self):
        cases = [
            (RetryBudgetExceededError, 409, "Task reflection retry budget is exhausted"),
            (TaskStateConflictError, 409,
             "Task is not ready for reflection; a fresh failed test result is required"),
            (InvalidReflectionError, 502, "Model returned an invalid reflection decision"),
            (httpx.HTTPError, 503, "Reflection model service is unavailable"),
            (SQLAlchemyError, 503, "Database unavailable"),
            (TaskExecutionError, 500, "Stored task or test data is invalid"),
            (ValueError, 500, "Reflection processing failed"),
        ]
        for error_type, status_code, detail in cases:
            with self.subTest(error_type=error_type.__name__):
                self.run_reflection.side_effect = error_type("internal diagnostic")
                with patch.object(tasks.logger, "exception") as log_exception:
                    response = self.client.post(self.url)

                self.assertEqual(response.status_code, status_code)
                self.assertEqual(response.json(), {"detail": detail})
                if status_code >= 500:
                    log_exception.assert_called_once()
                    self.assertIn(self.task_id, log_exception.call_args.args)
                else:
                    log_exception.assert_not_called()


if __name__ == "__main__":
    unittest.main()
