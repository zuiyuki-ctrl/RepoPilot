from pathlib import Path
import re

from ..core.exceptions import (
    TaskExecutionError, TaskStateConflictError, PlanScopeViolationError,
    WorkspaceFileConflictError,
)
from ..schemas.edit import TaskFileEditRead
from ..schemas.experiment import ExperimentPreparation
from ..schemas.task import TaskRead, TaskPlanResult
from . import task_service, repository_service, edit_proposal_service
from .workspace_edit_service import resolve_workspace_target
from .repository_scanner import read_file_snapshot


def check_protected_test_files(
    preparation: ExperimentPreparation, *, workspace_path: Path,
) -> None:
    """比较工作区测试文件的当前 hash 与准备记录中的基线 hash。"""
    hashes = preparation.protected_test_file_hashes
    if set(hashes) != set(preparation.case.protected_test_files):
        raise TaskExecutionError("Protected test hash keys do not match experiment protected tests")
    for file_path, baseline in hashes.items():
        if not isinstance(baseline, str) or re.fullmatch(r"[0-9a-f]{64}", baseline) is None:
            raise TaskExecutionError(f"Invalid protected test baseline hash: {file_path}")
    for file_path, baseline in hashes.items():
        target = resolve_workspace_target(workspace_path, file_path)
        snapshot = read_file_snapshot(workspace_path, target)
        if snapshot.metadata.file_hash != baseline:
            raise WorkspaceFileConflictError(f"Protected test file has changed: {file_path}")


def check_experiment_execution(
    preparation: ExperimentPreparation, *, file_path: str,
) -> TaskRead:
    """读取数据库现状，检查实验关联、批准范围和受保护测试文件。"""
    if preparation.status != "prepared":
        raise TaskExecutionError("Experiment preparation must be prepared")
    if preparation.task_id is None or preparation.repository_id is None or not preparation.workspace_path:
        raise TaskExecutionError("Experiment preparation is missing task, repository or workspace association")
    if preparation.run_config.retrieval_policy not in ("vector", "hybrid"):
        raise TaskExecutionError("Experiment retrieval policy must be vector or hybrid")
    task = task_service.get_task(preparation.task_id)
    if task is None:
        raise TaskExecutionError("Experiment associated task does not exist")
    for field, expected in (
        ("id", preparation.task_id), ("repository_id", preparation.repository_id),
        ("run_config", preparation.run_config),
        ("user_request", preparation.case.user_request.strip()), ("task_type", "plan"),
    ):
        if getattr(task, field) != expected:
            raise TaskExecutionError(f"Task {field} does not match experiment preparation")
    if (task.review_decision != "approved" or task.status not in {"approved", "executing"}
            or task.retry_count != 0):
        raise TaskStateConflictError("Experiment requires an approved plan in approved or executing state with retry_count=0")
    if not isinstance(task.result, TaskPlanResult):
        raise TaskExecutionError("Experiment task has no valid stored plan")
    if task.result.repository_id != preparation.repository_id:
        raise TaskExecutionError("Stored plan repository does not match experiment")
    planned_files = {path for step in task.result.plan.steps for path in step.files}
    allowed_files = set(preparation.case.editable_files)
    outside_scope = sorted(planned_files - allowed_files)
    if outside_scope:
        raise PlanScopeViolationError(f"Plan files outside experiment scope: {outside_scope}")
    if file_path not in planned_files or file_path not in allowed_files:
        raise PlanScopeViolationError(f"Target file is outside experiment or approved plan scope: {file_path}")

    # 这里只核对登记版本，不检查磁盘 Git HEAD。
    repository = repository_service.get_repository(preparation.repository_id)
    if repository is None:
        raise TaskExecutionError("Experiment associated repository does not exist")
    for field, expected in (
        ("id", preparation.repository_id), ("commit_hash", preparation.case.repository_commit),
        ("workspace_path", preparation.workspace_path), ("test_profile", preparation.case.test_profile),
    ):
        if getattr(repository, field) != expected:
            raise TaskExecutionError(f"Repository {field} does not match experiment preparation")
    check_protected_test_files(preparation, workspace_path=Path(repository.workspace_path))
    return task


def generate_experiment_file_edit(
    preparation: ExperimentPreparation, *, file_path: str,
) -> TaskFileEditRead:
    """开始已批准实验的执行，并生成一个文件候选；不应用候选。"""
    task = check_experiment_execution(preparation, file_path=file_path)
    if task.status == "approved":
        if task_service.begin_plan_execution(task.id) is None:
            raise TaskExecutionError("Experiment task disappeared while starting execution")
    task = check_experiment_execution(preparation, file_path=file_path)
    if task.status != "executing":
        raise TaskStateConflictError("Experiment task must be executing before candidate generation")
    # 各服务管理自身事务；模型失败保持已发生的 executing 状态，不自动重试。
    candidate = edit_proposal_service.generate_task_file_edit(task.id, file_path=file_path)
    if candidate is None:
        raise TaskExecutionError("Experiment candidate generation returned no task")
    if (candidate.task_id != task.id or candidate.repository_id != preparation.repository_id
            or candidate.proposal.file_path != file_path):
        raise TaskExecutionError("Generated candidate task, repository or file path does not match experiment")
    return candidate
