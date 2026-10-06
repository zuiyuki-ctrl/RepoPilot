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
    TestEnvironmentNotConfiguredError,
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
            test_profile="repopilot-dev",
        )
        self.test_run_id = UUID(
            "00000000-0000-0000-0000-000000000401"
        )
        self.test_run = SimpleNamespace(
            id=self.test_run_id,
            task_id=self.task_id,
            status="running",
            snapshot_hash=None,
        )
        self.snapshot_hash = "b" * 64
        self.snapshot = SimpleNamespace(
            snapshot_hash=self.snapshot_hash,
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

        create_test_run_patch = patch.object(
            task_test_service.test_run_repo,
            "create_test_run",
            return_value=self.test_run,
        )
        self.create_test_run = create_test_run_patch.start()
        self.addCleanup(create_test_run_patch.stop)

        get_test_run_patch = patch.object(
            task_test_service.test_run_repo,
            "get_test_run",
            return_value=self.test_run,
        )
        self.get_test_run = get_test_run_patch.start()
        self.addCleanup(get_test_run_patch.stop)

        def set_snapshot_hash(
            session,
            test_run,
            *,
            snapshot_hash,
        ):
            test_run.snapshot_hash = snapshot_hash

        snapshot_hash_patch = patch.object(
            task_test_service.test_run_repo,
            "set_test_run_snapshot_hash",
            side_effect=set_snapshot_hash,
        )
        self.set_snapshot_hash = snapshot_hash_patch.start()
        self.addCleanup(snapshot_hash_patch.stop)

        def finish_test_run(session, test_run, **kwargs):
            test_run.status = "finished"

        finish_test_run_patch = patch.object(
            task_test_service.test_run_repo,
            "finish_test_run",
            side_effect=finish_test_run,
        )
        self.finish_test_run = finish_test_run_patch.start()
        self.addCleanup(finish_test_run_patch.stop)

        def fail_test_run(session, test_run, *, error):
            test_run.status = "error"
            test_run.error = error

        fail_test_run_patch = patch.object(
            task_test_service.test_run_repo,
            "fail_test_run",
            side_effect=fail_test_run,
        )
        self.fail_test_run = fail_test_run_patch.start()
        self.addCleanup(fail_test_run_patch.stop)

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

        snapshot_patch = patch.object(
            task_test_service,
            "_prepare_task_test_snapshot",
            return_value=self.snapshot,
        )
        self.prepare_snapshot = snapshot_patch.start()
        self.addCleanup(snapshot_patch.stop)

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
                "run_pytest_in_docker",
                return_value=result,
        ) as run_docker:
            actual = task_test_service.run_task_pytest(self.task_id)

        self.assertIs(actual.sandbox_result, result)
        self.assertEqual(actual.test_run_id, self.test_run_id)
        self.create_test_run.assert_called_once_with(
            self.session,
            task_id=self.task_id,
            image="repopilot-pytest:repopilot-v1",
            timeout_seconds=task_test_service.DEFAULT_TEST_TIMEOUT_SECONDS,
        )
        self.finish_test_run.assert_called_once()
        self.assertEqual(self.test_run.status, "finished")
        self.set_snapshot_hash.assert_called_once_with(
            self.session,
            test_run=self.test_run,
            snapshot_hash=self.snapshot_hash,
        )
        self.assertEqual(
            self.test_run.snapshot_hash,
            self.snapshot_hash,
        )
        self.prepare_snapshot.assert_called_once()
        run_docker.assert_called_once_with(
            self.prepare_snapshot.return_value,
            image="repopilot-pytest:repopilot-v1",
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
        for event_call in self.append_task_event.call_args_list:
            self.assertEqual(
                event_call.kwargs["payload"]["test_run_id"],
                str(self.test_run_id),
            )

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
                "run_pytest_in_docker",
                return_value=result,
        ):
            actual = task_test_service.run_task_pytest(self.task_id)

        self.assertIs(actual.sandbox_result, result)
        self.assertEqual(actual.test_run_id, self.test_run_id)
        self.assertEqual(actual.sandbox_result.exit_code, 1)
        finish_event = self.append_task_event.call_args_list[-1]
        self.assertEqual(
            finish_event.kwargs["event_type"],
            "TEST_EXECUTION_FINISHED",
        )
        self.assertIs(finish_event.kwargs["payload"]["passed"], False)
        self.assertEqual(self.task.status, "executing")

    # 测试进程成功不代表持久化成功；收尾异常必须继续抛出，不能返回运行结果。
    def test_finish_persistence_failure_does_not_return_execution_result(self):
        result = SandboxTestResult(
            exit_code=0, stdout="1 passed", stderr="", timed_out=False,
            stdout_truncated=False, stderr_truncated=False,
        )
        error = RuntimeError("commit failed")
        with patch.object(task_test_service, "run_pytest_in_docker", return_value=result), \
             patch.object(task_test_service, "_finish_task_pytest", side_effect=error) as finish:
            with self.assertRaises(RuntimeError) as raised:
                task_test_service.run_task_pytest(self.task_id)
        self.assertIs(raised.exception, error)
        finish.assert_called_once()
        self.assertEqual(finish.call_args.args[0].test_run_id, self.test_run_id)
        self.assertIs(finish.call_args.args[1], result)

    def test_sandbox_error_restores_task_and_records_failure(self):
        error = SandboxExecutionError("Docker unavailable")

        with patch.object(
                task_test_service,
                "run_pytest_in_docker",
                side_effect=error,
        ):
            with self.assertRaises(SandboxExecutionError) as raised:
                task_test_service.run_task_pytest(self.task_id)

        self.assertIs(raised.exception, error)
        self.set_snapshot_hash.assert_called_once()
        self.assertEqual(
            self.test_run.snapshot_hash,
            self.snapshot_hash,
        )
        self.fail_test_run.assert_called_once_with(
            self.session,
            self.test_run,
            error="Sandbox test execution failed; see server logs.",
        )
        self.assertEqual(self.test_run.status, "error")
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
            failure_event.kwargs["payload"]["test_run_id"],
            str(self.test_run_id),
        )
        self.assertEqual(
            failure_event.kwargs["payload"]["error_type"],
            "SandboxExecutionError",
        )

    def test_testing_task_cannot_start_second_container(self):
        self.task.status = "testing"

        with patch.object(
                task_test_service,
                "run_pytest_in_docker",
        ) as run_docker:
            with self.assertRaises(TaskStateConflictError):
                task_test_service.run_task_pytest(self.task_id)

        self.prepare_snapshot.assert_not_called()
        run_docker.assert_not_called()
        self.append_task_event.assert_not_called()

    # 未配置测试环境时，在创建记录、改变状态和准备快照之前拒绝启动。
    def test_missing_profile_does_not_start_test_run(self):
        self.repository.test_profile = None

        with patch.object(
                task_test_service,
                "run_pytest_in_docker",
        ) as run_docker:
            with self.assertRaises(TestEnvironmentNotConfiguredError):
                task_test_service.run_task_pytest(self.task_id)

        self.create_test_run.assert_not_called()
        self.mark_task_testing.assert_not_called()
        self.append_task_event.assert_not_called()
        self.prepare_snapshot.assert_not_called()
        run_docker.assert_not_called()
        self.assertEqual(self.task.status, "executing")

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
                return_value=task_test_service.TaskTestExecutionResult(
                    test_run_id=self.test_run_id, sandbox_result=result,
                ),
        ):
            response = tasks.run_task_tests(self.task_id)

        self.assertFalse(response.passed)
        self.assertEqual(response.test_run_id, self.test_run_id)
        self.assertEqual(response.exit_code, 1)
