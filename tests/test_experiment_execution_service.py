from datetime import datetime, timezone
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from backend.app.core.exceptions import (
    TaskExecutionError, TaskStateConflictError, PlanScopeViolationError,
    WorkspaceFileConflictError, InvalidWorkspacePathError, RepositoryScanError,
)
from backend.app.schemas.edit import TaskFileEditRead, FileEditProposal
from backend.app.schemas.experiment import ExperimentCase, ExperimentPreparation
from backend.app.schemas.run_config import AgentRunConfig
from backend.app.schemas.task import TaskRead, TaskPlanResult
from backend.app.services import experiment_execution_service as service


class ExperimentExecutionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        (self.root / "tests").mkdir()
        self.test_path = self.root / "tests/test_task_list.py"
        self.test_path.write_bytes(b"def test_example():\n    assert True\n")
        self.preparation = ExperimentPreparation(
            experiment_id=uuid4(), created_at=datetime.now(timezone.utc),
            case=ExperimentCase(case_id="sample", case_version="v1", task_type="bug_fix",
                user_request=" fix ", repository_commit="a" * 40, editable_files=["task_list.py", "other.py"],
                protected_test_files=["tests/test_task_list.py"], test_profile="python-basic"),
            run_config=AgentRunConfig(retrieval_policy="vector"), status="prepared", stage="create_task",
            repository_id=uuid4(), task_id=uuid4(), workspace_path=str(self.root),
            protected_test_file_hashes={"tests/test_task_list.py": hashlib.sha256(self.test_path.read_bytes()).hexdigest()},
        )
        result = TaskPlanResult.model_validate(dict(repository_id=self.preparation.repository_id,
            plan=dict(summary="fix", steps=[dict(id=1, description="fix", files=["task_list.py"],
                source_ids=["chunk"], verification="pytest")])))
        self.task = TaskRead(id=self.preparation.task_id, repository_id=self.preparation.repository_id,
            user_request="fix", task_type="plan", status="approved", created_at=datetime.now(timezone.utc),
            started_at=None, completed_at=None, result=result, error=None, review_decision="approved",
            review_comment=None, reviewed_at=datetime.now(timezone.utc), run_config=self.preparation.run_config)
        self.repository = SimpleNamespace(id=self.preparation.repository_id, commit_hash=self.preparation.case.repository_commit,
            workspace_path=str(self.root), test_profile="python-basic")
        self.get_task = self.enterContext(patch.object(service.task_service, "get_task", return_value=self.task))
        self.get_repository = self.enterContext(patch.object(service.repository_service, "get_repository", return_value=self.repository))
        self.begin = self.enterContext(patch.object(service.task_service, "begin_plan_execution", side_effect=self.start))
        self.candidate = TaskFileEditRead(task_id=self.task.id, repository_id=self.repository.id,
            base_file_hash="b" * 64, proposal=FileEditProposal(file_path="task_list.py", summary="fix", content="value = 1\n"))
        self.generate = self.enterContext(patch.object(service.edit_proposal_service, "generate_task_file_edit", return_value=self.candidate))

    def start(self, task_id):
        self.task.status = "executing"
        return self.task

    def check(self, preparation=None, file_path="task_list.py"):
        return service.check_experiment_execution(preparation or self.preparation, file_path=file_path)

    def generate_edit(self):
        return service.generate_experiment_file_edit(self.preparation, file_path="task_list.py")

    def test_approved_starts_once_and_executing_does_not_restart(self):
        self.assertIs(self.generate_edit(), self.candidate)
        self.begin.assert_called_once_with(self.task.id)
        self.assertEqual(self.get_task.call_count, 2)
        self.assertIs(self.generate_edit(), self.candidate)
        self.assertEqual(self.begin.call_count, 1)
        self.assertEqual(self.generate.call_count, 2)
        self.generate.assert_called_with(self.task.id, file_path="task_list.py")

    def test_preparation_requirements(self):
        for update in ({"status": "error"}, {"task_id": None}, {"repository_id": None},
                       {"workspace_path": ""}, {"run_config": AgentRunConfig()}):
            with self.subTest(update=update), self.assertRaises(TaskExecutionError):
                self.check(self.preparation.model_copy(update=update))
        self.get_task.assert_not_called()

    def test_missing_task_and_identity_mismatch(self):
        self.get_task.return_value = None
        with self.assertRaisesRegex(TaskExecutionError, "task does not exist"):
            self.check()
        for field, value in (("id", uuid4()), ("repository_id", uuid4()), ("user_request", "other"),
                             ("task_type", "question"), ("run_config", AgentRunConfig(retrieval_policy="hybrid"))):
            self.get_task.return_value = self.task.model_copy(update={field: value})
            with self.subTest(field=field), self.assertRaisesRegex(TaskExecutionError, field):
                self.check()
        self.get_repository.assert_not_called()

    def test_state_and_retry_constraints(self):
        for update in ({"status": "awaiting_review"}, {"review_decision": "rejected"}, {"retry_count": 1}):
            self.get_task.return_value = self.task.model_copy(update=update)
            with self.subTest(update=update), self.assertRaises(TaskStateConflictError):
                self.generate_edit()
        self.begin.assert_not_called()
        self.generate.assert_not_called()

    def test_entire_plan_scope_and_exact_target_membership(self):
        for file_path in ("other.py", "Task_list.py", "./task_list.py", "tests/test_task_list.py"):
            with self.subTest(file_path=file_path), self.assertRaisesRegex(PlanScopeViolationError, file_path):
                self.check(file_path=file_path)
        self.task.result.plan.steps[0].files.append("tests/test_task_list.py")
        with self.assertRaisesRegex(PlanScopeViolationError, "tests/test_task_list.py"):
            self.generate_edit()
        self.begin.assert_not_called()
        self.generate.assert_not_called()

    def test_missing_or_wrong_plan(self):
        self.get_task.return_value = self.task.model_copy(update={"result": None})
        with self.assertRaises(TaskExecutionError):
            self.check()
        self.get_task.return_value = self.task
        self.task.result.repository_id = uuid4()
        with self.assertRaises(TaskExecutionError):
            self.check()

    def test_repository_association(self):
        self.get_repository.return_value = None
        with self.assertRaises(TaskExecutionError):
            self.check()
        for field, value in (("id", uuid4()), ("commit_hash", "b" * 40),
                             ("workspace_path", "D:/other"), ("test_profile", "other")):
            self.get_repository.return_value = SimpleNamespace(**{**vars(self.repository), field: value})
            with self.subTest(field=field), self.assertRaisesRegex(TaskExecutionError, field):
                self.check()

    def test_hash_baseline_keys_and_format(self):
        for hashes in ({}, {"extra.py": "a" * 64}, {"tests/test_task_list.py": "A" * 64},
                       {"tests/test_task_list.py": "a" * 63}, {"tests/test_task_list.py": "g" * 64}):
            with self.subTest(hashes=hashes), self.assertRaises(TaskExecutionError):
                service.check_protected_test_files(self.preparation.model_copy(update={"protected_test_file_hashes": hashes}),
                    workspace_path=self.root)

    def test_real_test_change_blocks_generation_without_updating_baseline(self):
        before = dict(self.preparation.protected_test_file_hashes)
        self.test_path.write_bytes(b"def test_example():\n    pass\n")
        with self.assertRaisesRegex(WorkspaceFileConflictError, "tests/test_task_list.py"):
            self.generate_edit()
        self.assertEqual(self.preparation.protected_test_file_hashes, before)
        self.begin.assert_not_called()
        self.generate.assert_not_called()

    def test_missing_file_and_path_or_read_errors_stop_execution(self):
        self.test_path.unlink()
        with self.assertRaises(RepositoryScanError):
            self.generate_edit()
        for function, error in (("resolve_workspace_target", InvalidWorkspacePathError("bad path")),
                                ("read_file_snapshot", RepositoryScanError("read failed"))):
            with self.subTest(function=function), patch.object(service, function, side_effect=error):
                with self.assertRaises(type(error)):
                    self.generate_edit()
        self.begin.assert_not_called()
        self.generate.assert_not_called()

    def test_second_check_catches_changed_tests_after_start(self):
        def start(task_id):
            self.task.status = "executing"
            self.test_path.write_bytes(b"changed\n")
            return self.task
        self.begin.side_effect = start
        with self.assertRaises(WorkspaceFileConflictError):
            self.generate_edit()
        self.assertEqual(self.task.status, "executing")
        self.generate.assert_not_called()

    def test_start_failure_and_nonexecuting_recheck(self):
        self.begin.side_effect = None
        self.begin.return_value = None
        with self.assertRaises(TaskExecutionError):
            self.generate_edit()
        self.begin.return_value = self.task
        with self.assertRaises(TaskStateConflictError):
            self.generate_edit()
        self.generate.assert_not_called()

    def test_model_failure_preserves_executing_and_is_not_retried(self):
        original = TimeoutError("model timeout")
        self.generate.side_effect = original
        with self.assertRaises(TimeoutError) as raised:
            self.generate_edit()
        self.assertIs(raised.exception, original)
        self.assertEqual(self.task.status, "executing")
        self.generate.assert_called_once()

    def test_candidate_identity_and_missing_result(self):
        self.task.status = "executing"
        changed_proposal = self.candidate.proposal.model_copy(update={"file_path": "other.py"})
        for candidate in (None, self.candidate.model_copy(update={"task_id": uuid4()}),
                          self.candidate.model_copy(update={"repository_id": uuid4()}),
                          self.candidate.model_copy(update={"proposal": changed_proposal})):
            self.generate.return_value = candidate
            with self.subTest(candidate=candidate), self.assertRaises(TaskExecutionError):
                self.generate_edit()
        self.begin.assert_not_called()
