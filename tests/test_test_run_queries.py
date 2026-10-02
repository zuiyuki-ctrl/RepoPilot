import unittest
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.routes import tasks
from backend.app.core.exceptions import InvalidTaskInputError
from backend.app.services import test_run_service


class TestRunServiceTests(unittest.TestCase):
    def setUp(self):
        self.task_id = UUID(
            "00000000-0000-0000-0000-000000000301"
        )
        self.test_run_id = UUID(
            "00000000-0000-0000-0000-000000000401"
        )

        self.session = Mock(name="session")
        self.task = SimpleNamespace(id=self.task_id)
        self.test_run = SimpleNamespace(
            id=self.test_run_id,
            task_id=self.task_id,
            status="finished",
            image="python:3.11-slim",
            timeout_seconds=120,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            exit_code=0,
            timed_out=False,
            stdout="1 passed",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            error=None,
            snapshot_hash="a" * 64,
        )

        session_patch = patch.object(
            test_run_service,
            "SessionLocal",
        )
        self.session_local = session_patch.start()
        self.addCleanup(session_patch.stop)
        self.session_local.return_value = nullcontext(self.session)

        task_patch = patch.object(
            test_run_service.task_repo,
            "get_task",
            return_value=self.task,
        )
        self.get_task = task_patch.start()
        self.addCleanup(task_patch.stop)

        get_run_patch = patch.object(
            test_run_service.test_run_repo,
            "get_test_run",
            return_value=self.test_run,
        )
        self.get_test_run = get_run_patch.start()
        self.addCleanup(get_run_patch.stop)

        list_runs_patch = patch.object(
            test_run_service.test_run_repo,
            "list_test_runs",
            return_value=[self.test_run],
        )
        self.list_test_runs = list_runs_patch.start()
        self.addCleanup(list_runs_patch.stop)

    def test_get_and_list_test_runs(self):
        record = test_run_service.get_task_test_run(
            self.task_id,
            self.test_run_id,
        )

        self.assertEqual(record.id, self.test_run_id)
        self.assertEqual(record.task_id, self.task_id)
        self.assertEqual(record.status, "finished")
        self.get_test_run.assert_called_once_with(
            self.session,
            task_id=self.task_id,
            test_run_id=self.test_run_id,
        )

        records = test_run_service.list_task_test_runs(
            self.task_id,
            limit=20,
            offset=5,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].id, self.test_run_id)
        self.list_test_runs.assert_called_once_with(
            self.session,
            task_id=self.task_id,
            limit=20,
            offset=5,
        )

    def test_missing_task_and_invalid_pagination(self):
        self.get_task.return_value = None

        self.assertIsNone(
            test_run_service.get_task_test_run(
                self.task_id,
                self.test_run_id,
            )
        )
        self.assertIsNone(
            test_run_service.list_task_test_runs(self.task_id)
        )
        self.get_test_run.assert_not_called()
        self.list_test_runs.assert_not_called()

        self.get_task.return_value = self.task
        cases = [
            {"limit": 0, "offset": 0},
            {"limit": 101, "offset": 0},
            {"limit": 50, "offset": -1},
        ]

        for parameters in cases:
            with self.subTest(parameters=parameters):
                with self.assertRaises(InvalidTaskInputError):
                    test_run_service.list_task_test_runs(
                        self.task_id,
                        **parameters,
                    )


class TestRunRouteTests(unittest.TestCase):
    def setUp(self):
        self.task_id = UUID(
            "00000000-0000-0000-0000-000000000301"
        )
        self.test_run_id = UUID(
            "00000000-0000-0000-0000-000000000401"
        )

        app = FastAPI()
        app.include_router(tasks.router)
        self.client = self.enterContext(TestClient(app))

    def make_record(self):
        return test_run_service.TestRunRead(
            id=self.test_run_id,
            task_id=self.task_id,
            status="finished",
            image="python:3.11-slim",
            timeout_seconds=120,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            exit_code=0,
            timed_out=False,
            stdout="1 passed",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            error=None,
            snapshot_hash="a" * 64,
        )

    def test_list_and_get_routes(self):
        record = self.make_record()
        with patch.object(
            tasks.test_run_service,
            "list_task_test_runs",
            return_value=[record],
        ) as list_runs:
            response = self.client.get(
                f"/api/v1/tasks/{self.task_id}/test-runs",
                params={"limit": 20, "offset": 5},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], str(self.test_run_id))
        list_runs.assert_called_once_with(
            self.task_id,
            limit=20,
            offset=5,
        )

        with patch.object(
            tasks.test_run_service,
            "get_task_test_run",
            return_value=record,
        ) as get_run:
            response = self.client.get(
                f"/api/v1/tasks/{self.task_id}/test-runs/{self.test_run_id}"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.test_run_id))
        get_run.assert_called_once_with(self.task_id, self.test_run_id)

    def test_query_route_errors(self):
        with patch.object(
            tasks.test_run_service,
            "list_task_test_runs",
            return_value=None,
        ):
            response = self.client.get(
                f"/api/v1/tasks/{self.task_id}/test-runs"
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Task not found")

        with patch.object(
            tasks.test_run_service,
            "get_task_test_run",
            return_value=None,
        ):
            response = self.client.get(
                f"/api/v1/tasks/{self.task_id}/test-runs/{self.test_run_id}"
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Test run not found")

        with patch.object(
            tasks.test_run_service,
            "list_task_test_runs",
        ) as list_runs:
            response = self.client.get(
                f"/api/v1/tasks/{self.task_id}/test-runs",
                params={"limit": 0},
            )
        self.assertEqual(response.status_code, 422)
        list_runs.assert_not_called()

        with patch.object(
            tasks.test_run_service,
            "list_task_test_runs",
            side_effect=SQLAlchemyError("database unavailable"),
        ):
            response = self.client.get(
                f"/api/v1/tasks/{self.task_id}/test-runs"
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Database unavailable")


if __name__ == "__main__":
    unittest.main()
