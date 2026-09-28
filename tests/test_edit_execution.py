import unittest
from contextlib import nullcontext
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from backend.app.agent.edit_generation import (
    parse_file_edit,
    validate_file_edit_proposal,
)
from backend.app.core.exceptions import (
    InvalidEditProposalError,
    PlanScopeViolationError,
    WorkspaceFileConflictError,
    WorkspaceWritePersistenceError,
)
from backend.app.schemas.edit import FileEditProposal
from backend.app.services import plan_execution_service
from backend.app.services.workspace_git_service import read_workspace_diff
from backend.app.services.workspace_edit_service import (
    WorkspaceWriteResult,
)

class EditExecutionTests(unittest.TestCase):
    # 构造审核已通过、当前处于执行中的计划任务，供写入分支测试使用。
    def make_executing_task(self):
        repository_id = UUID("00000000-0000-0000-0000-000000000001")
        return SimpleNamespace(
            id=UUID("00000000-0000-0000-0000-000000000101"),
            repository_id=repository_id,
            task_type="plan",
            status="executing",
            review_decision="approved",
            result={
                "repository_id": str(repository_id),
                "plan": {
                    "summary": "修改示例文件",
                    "steps": [
                        {
                            "id": 1,
                            "description": "调整示例实现",
                            "files": ["backend/app/example.py"],
                            "source_ids": ["S1"],
                            "verification": "运行单元测试",
                        }
                    ],
                },
            },
        )

    def test_candidate_validation_accepts_valid_python(self):
        proposal = FileEditProposal(
            file_path="backend/app/example.py",
            summary="调整返回值",
            content="def example():\n    return 2\n",
        )

        result = validate_file_edit_proposal(
            proposal,
            expected_file_path="backend/app/example.py",
        )

        self.assertIs(result, proposal)

    def test_candidate_validation_rejects_invalid_proposals(self):
        cases = (
            (
                "wrong path",
                FileEditProposal(
                    file_path="other.py",
                    summary="修改",
                    content="value = 1\n",
                ),
                "expected.py",
            ),
            (
                "blank content",
                FileEditProposal(
                    file_path="expected.py",
                    summary="修改",
                    content=" \n",
                ),
                "expected.py",
            ),
            (
                "invalid syntax",
                FileEditProposal(
                    file_path="expected.py",
                    summary="修改",
                    content="def broken(:\n",
                ),
                "expected.py",
            ),
        )

        for name, proposal, expected_path in cases:
            with self.subTest(name=name):
                with self.assertRaises(InvalidEditProposalError):
                    validate_file_edit_proposal(
                        proposal,
                        expected_file_path=expected_path,
                    )

    def test_apply_valid_candidate_passes_hash_and_content(self):
        proposal = FileEditProposal(
            file_path="backend/app/example.py",
            summary="调整返回值",
            content="def example():\n    return 2\n",
        )
        expected_result = Mock()

        with patch.object(
            plan_execution_service,
            "write_approved_plan_file",
            return_value=expected_result,
        ) as writer:
            result = plan_execution_service.apply_task_file_edit(
                UUID("00000000-0000-0000-0000-000000000101"),
                base_file_hash="a" * 64,
                proposal=proposal,
            )

        self.assertIs(result, expected_result)
        writer.assert_called_once_with(
            UUID("00000000-0000-0000-0000-000000000101"),
            file_path="backend/app/example.py",
            content="def example():\n    return 2\n",
            expected_file_hash="a" * 64,
        )

    def test_invalid_candidate_does_not_call_writer(self):
        proposal = FileEditProposal(
            file_path="backend/app/example.py",
            summary="无效语法",
            content="def broken(:\n",
        )

        with patch.object(
            plan_execution_service,
            "write_approved_plan_file",
        ) as writer:
            with self.assertRaises(InvalidEditProposalError):
                plan_execution_service.apply_task_file_edit(
                    UUID("00000000-0000-0000-0000-000000000101"),
                    base_file_hash="a" * 64,
                    proposal=proposal,
                )

        writer.assert_not_called()

    def test_hash_conflict_does_not_write_or_emit_event(self):
        # 1. 模拟审核已通过且处于 executing 状态的计划任务。
        task = self.make_executing_task()
        task_id = task.id
        session = Mock(name="session")
        # 2. 模拟计划包含目标文件。
        # 3. 模拟 repository.workspace_path。
        repository = SimpleNamespace(workspace_path="C:/workspace/repopilot")
        # 4. 模拟 snapshot hash 与 expected hash 不同。
        snapshot = SimpleNamespace(
            metadata=SimpleNamespace(file_hash="b" * 64),
        )
        # 5. patch write_workspace_file 和 append_task_event。
        with (
            patch.object(plan_execution_service, "SessionLocal") as session_local,
            patch.object(
                plan_execution_service.task_repo,
                "get_task_for_update",
                return_value=task,
            ),
            patch.object(
                plan_execution_service.repository_repo,
                "get_repository_for_update",
                return_value=repository,
            ),
            patch.object(
                plan_execution_service,
                "resolve_workspace_target",
                return_value=Path("C:/workspace/repopilot/backend/app/example.py"),
            ),
            patch.object(
                plan_execution_service,
                "read_file_snapshot",
                return_value=snapshot,
            ) as snapshot_reader,
            patch.object(plan_execution_service, "write_workspace_file") as writer,
            patch.object(
                plan_execution_service.task_event_repo,
                "append_task_event",
            ) as append_event,
        ):
            session_local.begin.return_value = nullcontext(session)

            # 6. 断言 WorkspaceFileConflictError。
            with self.assertRaises(WorkspaceFileConflictError):
                plan_execution_service.write_approved_plan_file(
                    task_id,
                    file_path="backend/app/example.py",
                    content="def example():\n    return 2\n",
                    expected_file_hash="a" * 64,
                )

        snapshot_reader.assert_called_once()
        # 7. 断言两个副作用都没有发生。
        writer.assert_not_called()
        append_event.assert_not_called()

    def test_file_outside_approved_plan_is_rejected_before_write(self):
        # 计划只包含 example.py。
        task = self.make_executing_task()
        session = Mock(name="session")
        # 请求写 other.py。
        with (
            patch.object(plan_execution_service, "SessionLocal") as session_local,
            patch.object(
                plan_execution_service.task_repo,
                "get_task_for_update",
                return_value=task,
            ),
            patch.object(plan_execution_service, "read_file_snapshot") as snapshot_reader,
            patch.object(plan_execution_service, "write_workspace_file") as writer,
            patch.object(
                plan_execution_service.task_event_repo,
                "append_task_event",
            ) as append_event,
        ):
            session_local.begin.return_value = nullcontext(session)

            # 断言 PlanScopeViolationError。
            with self.assertRaises(PlanScopeViolationError):
                plan_execution_service.write_approved_plan_file(
                    task.id,
                    file_path="backend/app/other.py",
                    content="value = 2\n",
                    expected_file_hash="a" * 64,
                )

        # 断言 snapshot、writer 和事件均未调用。
        snapshot_reader.assert_not_called()
        writer.assert_not_called()
        append_event.assert_not_called()

    def test_workspace_diff_reports_tracked_and_untracked_files(self):
        # 1. TemporaryDirectory。
        with TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()

            def git(*args):
                return subprocess.run(
                    ["git", "-C", str(workspace), *args],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )

            # 2. git init。
            git("init")
            git("config", "user.name", "RepoPilot Tests")
            git("config", "user.email", "tests@repopilot.invalid")

            # 3. 创建 example.py 并提交。
            example = workspace / "example.py"
            example.write_text("value = 1\n", encoding="utf-8")
            git("add", "example.py")
            git("commit", "-m", "initial")

            # 4. 修改 example.py。
            example.write_text("value = 2\n", encoding="utf-8")
            # 5. 创建 new_file.py。
            (workspace / "new_file.py").write_text(
                "new_value = 1\n",
                encoding="utf-8",
            )

            # 6. 调用 read_workspace_diff。
            result = read_workspace_diff(workspace)

            # 7. 检查 changed_files、untracked_files、diff。
            self.assertEqual(result.changed_files, ["example.py"])
            self.assertEqual(result.untracked_files, ["new_file.py"])
            self.assertIn("-value = 1", result.diff)
            self.assertIn("+value = 2", result.diff)
            self.assertFalse(result.truncated)

            # 8. 使用很小 max_chars 再调用，检查 truncated=True。
            truncated = read_workspace_diff(workspace, max_chars=10)
            self.assertTrue(truncated.truncated)
            self.assertEqual(len(truncated.diff), 10)

    def test_approved_file_is_written_and_event_is_recorded(self):
        task = self.make_executing_task()
        session = Mock(name="session")
        repository = SimpleNamespace(
            workspace_path="C:/workspace/repopilot",
        )
        write_result = WorkspaceWriteResult(
            file_path="backend/app/example.py",
            created=False,
            bytes_written=32,
        )

        with (
            patch.object(
                plan_execution_service,
                "SessionLocal",
            ) as session_local,
            patch.object(
                plan_execution_service.task_repo,
                "get_task_for_update",
                return_value=task,
            ),
            patch.object(
                plan_execution_service.repository_repo,
                "get_repository_for_update",
                return_value=repository,
            ),
            patch.object(
                plan_execution_service,
                "write_workspace_file",
                return_value=write_result,
            ) as writer,
            patch.object(
                plan_execution_service.task_event_repo,
                "append_task_event",
            ) as append_event,
        ):
            session_local.begin.return_value = nullcontext(session)

            result = plan_execution_service.write_approved_plan_file(
                task.id,
                file_path="backend/app/example.py",
                content="def example():\n    return 2\n",
            )

        self.assertIs(result, write_result)
        writer.assert_called_once_with(
            Path("C:/workspace/repopilot"),
            file_path="backend/app/example.py",
            content="def example():\n    return 2\n",
        )
        append_event.assert_called_once_with(
            session,
            task_id=task.id,
            event_type="FILE_MODIFIED",
            node_name="plan_execution_service",
            message="Workspace file modified",
            payload={
                "step_id": "execute_plan",
                "attempt": 1,
                "file_path": "backend/app/example.py",
                "created": False,
                "bytes_written": 32,
            },
        )

    def test_event_failure_after_write_reports_persistence_uncertainty(self):
        # 准备与成功测试相同的执行中任务和 repository，审核结论仍为 approved。
        task = self.make_executing_task()
        session = Mock(name="session")
        repository = SimpleNamespace(
            workspace_path="C:/workspace/repopilot",
        )
        write_result = WorkspaceWriteResult(
            file_path="backend/app/example.py",
            created=False,
            bytes_written=32,
        )
        persistence_error = RuntimeError("event insert failed")

        with (
            patch.object(
                plan_execution_service,
                "SessionLocal",
            ) as session_local,
            patch.object(
                plan_execution_service.task_repo,
                "get_task_for_update",
                return_value=task,
            ),
            patch.object(
                plan_execution_service.repository_repo,
                "get_repository_for_update",
                return_value=repository,
            ),
            # write_workspace_file 返回成功结果。
            patch.object(
                plan_execution_service,
                "write_workspace_file",
                return_value=write_result,
            ) as writer,
            # append_task_event 抛 RuntimeError。
            patch.object(
                plan_execution_service.task_event_repo,
                "append_task_event",
                side_effect=persistence_error,
            ) as append_event,
        ):
            session_local.begin.return_value = nullcontext(session)

            # 断言 WorkspaceWritePersistenceError。
            with self.assertRaises(WorkspaceWritePersistenceError) as raised:
                plan_execution_service.write_approved_plan_file(
                    task.id,
                    file_path="backend/app/example.py",
                    content="def example():\n    return 2\n",
                )

        self.assertIs(raised.exception.__cause__, persistence_error)
        # 断言 writer 已经调用一次。
        writer.assert_called_once_with(
            Path("C:/workspace/repopilot"),
            file_path="backend/app/example.py",
            content="def example():\n    return 2\n",
        )
        append_event.assert_called_once()

if __name__ == "__main__":
    unittest.main()
