import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from backend.app.api.routes import tasks
from backend.app.core.exceptions import (
    SandboxExecutionError,
    TaskStateConflictError,
)
from backend.app.services import task_test_service
from backend.app.services.docker_test_service import SandboxTestResult


class TaskSandboxExecutionTests(unittest.TestCase):
    def setUp(self):
        self.task_id = UUID(
            "00000000-0000-0000-0000-000000000301"
        )
        self.repository_id = UUID(
            "00000000-0000-0000-0000-000000000001"
        )
        self.workspace_path = Path("D:/RepoPilot-workspaces/example")

        self.task = SimpleNamespace(
            id=self.task_id,
            repository_id=self.repository_id,
            task_type="plan",
            status="executing",
            review_decision="approved",
            error=None,
            completed_at=None,
        )
        self.repository = SimpleNamespace(
            id=self.repository_id,
            workspace_path=str(self.workspace_path),
        )

        self.session = Mock(name="session")

        session_patch = patch.object(
            task_test_service,
            "SessionLocal",
        )
        self.session_local = session_patch.start()
        self.addCleanup(session_patch.stop)
        self.session_local.begin.side_effect = (
            lambda: nullcontext(self.session)
        )

        task_patch = patch.object(
            task_test_service.task_repo,
            "get_task_for_update",
            return_value=self.task,
        )
        self.get_task_for_update = task_patch.start()
        self.addCleanup(task_patch.stop)

        repository_patch = patch.object(
            task_test_service.repository_repo,
            "get_repository",
            return_value=self.repository,
        )
        self.get_repository = repository_patch.start()
        self.addCleanup(repository_patch.stop)

        testing_patch = patch.object(
            task_test_service.task_repo,
            "mark_task_testing",
            side_effect=lambda session, task: setattr(task, "status", "testing"),
        )
        self.mark_task_testing = testing_patch.start()
        self.addCleanup(testing_patch.stop)

        executing_patch = patch.object(
            task_test_service.task_repo,
            "mark_task_executing",
            side_effect=lambda session, task: setattr(task, "status", "executing"),
        )
        self.mark_task_executing = executing_patch.start()
        self.addCleanup(executing_patch.stop)

        event_patch = patch.object(
            task_test_service.task_event_repo,
            "append_task_event",
        )
        self.append_task_event = event_patch.start()
        self.addCleanup(event_patch.stop)

    def test_successful_test_run_records_start_and_finish(self):
        result = SandboxTestResult(
            exit_code=0,
            stdout="1 passed",
            stderr="",
            timed_out=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )

        with patch.object(
                task_test_service,
                "run_workspace_pytest",
                return_value=result,
        ) as run_workspace:
            actual = task_test_service.run_task_pytest(self.task_id)

        self.assertIs(actual, result)
        run_workspace.assert_called_once_with(
            self.workspace_path,
            image=task_test_service.DEFAULT_TEST_IMAGE,
            timeout_seconds=task_test_service.DEFAULT_TEST_TIMEOUT_SECONDS,
            max_output_chars=task_test_service.MAX_TEST_OUTPUT_CHARS,
        )
        self.assertEqual(self.task.status, "executing")
        self.assertEqual(self.append_task_event.call_count, 2)
        event_types = [
            call.kwargs["event_type"]
            for call in self.append_task_event.call_args_list
        ]
        self.assertEqual(
            event_types,
            ["TEST_EXECUTION_STARTED", "TEST_EXECUTION_FINISHED"],
        )
        finish_event = self.append_task_event.call_args_list[-1]
        self.assertIs(finish_event.kwargs["payload"]["passed"], True)

    def test_pytest_failure_is_finished_result(self):
        result = SandboxTestResult(
            exit_code=1,
            stdout="1 failed",
            stderr="",
            timed_out=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )

        with patch.object(
                task_test_service,
                "run_workspace_pytest",
                return_value=result,
        ):
            actual = task_test_service.run_task_pytest(self.task_id)

        self.assertIs(actual, result)
        self.assertEqual(actual.exit_code, 1)
        finish_event = self.append_task_event.call_args_list[-1]
        self.assertEqual(
            finish_event.kwargs["event_type"],
            "TEST_EXECUTION_FINISHED",
        )
        self.assertIs(finish_event.kwargs["payload"]["passed"], False)
        self.assertEqual(self.task.status, "executing")

    def test_sandbox_error_restores_task_and_records_failure(self):
        error = SandboxExecutionError("Docker unavailable")

        with patch.object(
                task_test_service,
                "run_workspace_pytest",
                side_effect=error,
        ):
            with self.assertRaises(SandboxExecutionError) as raised:
                task_test_service.run_task_pytest(self.task_id)

        self.assertIs(raised.exception, error)
        self.assertEqual(self.task.status, "executing")
        event_types = [
            call.kwargs["event_type"]
            for call in self.append_task_event.call_args_list
        ]
        self.assertEqual(
            event_types,
            ["TEST_EXECUTION_STARTED", "TEST_EXECUTION_FAILED"],
        )
        failure_event = self.append_task_event.call_args_list[-1]
        self.assertEqual(
            failure_event.kwargs["payload"]["error_type"],
            "SandboxExecutionError",
        )

    def test_testing_task_cannot_start_second_container(self):
        self.task.status = "testing"

        with patch.object(
                task_test_service,
                "run_workspace_pytest",
        ) as run_workspace:
            with self.assertRaises(TaskStateConflictError):
                task_test_service.run_task_pytest(self.task_id)

        run_workspace.assert_not_called()
        self.append_task_event.assert_not_called()

    def test_route_returns_200_style_result_for_failed_tests(self):
        result = SandboxTestResult(
            exit_code=1,
            stdout="1 failed",
            stderr="",
            timed_out=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )

        with patch.object(
                tasks.task_test_service,
                "run_task_pytest",
                return_value=result,
        ):
            response = tasks.run_task_tests(self.task_id)

        self.assertFalse(response.passed)
        self.assertEqual(response.exit_code, 1)
