from pathlib import Path
from uuid import UUID
import re

from ..core.exceptions import (
    TaskExecutionError, TaskStateConflictError, PlanScopeViolationError,
    WorkspaceFileConflictError,
)
from ..schemas.edit import TaskFileEditRead
from ..schemas.experiment import ExperimentPreparation
from ..schemas.task import TaskRead, TaskPlanResult
from .workspace_edit_service import resolve_workspace_target
from .repository_scanner import read_file_snapshot

from ..schemas.experiment import ExperimentEditCandidate
from ..schemas.testing import TestRunRead
from ..schemas.task_report import TaskExecutionReport
from .workspace_edit_service import WorkspaceWriteResult
from . import (
    plan_execution_service,
    task_test_service,
    test_run_service,
    task_completion_service,
    task_report_service,
    task_service, repository_service, edit_proposal_service
)


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
        preparation: ExperimentPreparation,
        *,
        file_path: str | None = None,
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
        raise TaskStateConflictError(
            "Experiment requires an approved plan in approved or executing state with retry_count=0")
    if not isinstance(task.result, TaskPlanResult):
        raise TaskExecutionError("Experiment task has no valid stored plan")
    if task.result.repository_id != preparation.repository_id:
        raise TaskExecutionError("Stored plan repository does not match experiment")
    planned_files = {path for step in task.result.plan.steps for path in step.files}
    allowed_files = set(preparation.case.editable_files)
    outside_scope = sorted(planned_files - allowed_files)
    if outside_scope:
        raise PlanScopeViolationError(f"Plan files outside experiment scope: {outside_scope}")

    if file_path is not None:
        if file_path not in planned_files or file_path not in allowed_files:
            raise PlanScopeViolationError(f"Target file is outside experiment or approved plan scope: "
                                          f"{file_path}")

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


def apply_experiment_file_edit(
    preparation: ExperimentPreparation,
    *,
    artifact: ExperimentEditCandidate,
) -> WorkspaceWriteResult:
    candidate = artifact.candidate

    # 1. 校验以下三个关联：
    #    artifact.experiment_id == preparation.experiment_id
    #    candidate.task_id == preparation.task_id
    #    candidate.repository_id == preparation.repository_id
    #    不一致抛 TaskExecutionError。
    if not (
        artifact.experiment_id == preparation.experiment_id
        and candidate.task_id == preparation.task_id
        and candidate.repository_id == preparation.repository_id
    ):
        raise TaskExecutionError("Experiment candidate generation returned no task")

    # 2. 调用 check_experiment_execution：
    #    file_path 来自 candidate.proposal.file_path。
    task = check_experiment_execution(preparation, file_path=candidate.proposal.file_path)

    # 3. 必须要求 task.status == "executing"。
    #    这里不能代替 generate 阶段自动开始执行。
    if task.status != "executing":
        raise TaskStateConflictError("Experiment task must be executing before candidate generation")

    # 4. 调用已有应用服务
    result = plan_execution_service.apply_task_file_edit(
        task.id,
        base_file_hash=candidate.base_file_hash,
        proposal=candidate.proposal,
    )

    # 5. result 为 None 时抛 TaskExecutionError，否则返回。
    if result is None:
        raise TaskExecutionError("Experiment candidate generation returned no task")

    return result


def run_experiment_tests(
    preparation: ExperimentPreparation,
) -> TestRunRead:
    # 1. 调用 check_experiment_execution(preparation)。
    #    要求返回任务处于 executing。
    task = check_experiment_execution(preparation)
    if task.status != "executing":
        raise TaskStateConflictError("Experiment test must be executing before candidate generation")

    # 2. 调用
    execution = task_test_service.run_task_pytest(task.id)
    if execution is None:
        raise TaskExecutionError("Experiment test execution returned no task")

    # 3. 使用本次返回的 ID 查询数据库
    run = test_run_service.get_task_test_run(
        task.id,
        execution.test_run_id,
    )

    # 4. 检查 run 不为 None：
    #    run.id == execution.test_run_id
    #    run.task_id == task.id
    #    run.status == "finished"
    if run is None:
        raise TaskExecutionError("Test run execution failed")

    if not (
        run.id == execution.test_run_id
        and run.task_id == task.id
        and run.status == "finished"
    ):
        raise TaskExecutionError("Test run execution failed")

    # 5. 返回 run，测试通过或断言失败都要返回并保存。
    return run


def complete_experiment(
    preparation: ExperimentPreparation,
    *,
    test_run_id: UUID,
) -> TaskRead:
    # 1. 调用 check_experiment_execution(preparation)。
    task = check_experiment_execution(preparation)
    if task.status != "executing":
        raise TaskStateConflictError("Experiment task must be executing before candidate generation")

    # 2. 调用已有完成服务
    completed = task_completion_service.complete_plan_task(
        task.id,
        test_run_id=test_run_id,
    )

    # 3. 检查返回值不为 None，且：
    #    id、repository_id、run_config 与准备记录一致；
    #    status == "completed"。
    if completed is None:
        raise TaskExecutionError("Experiment completion failed")

    if not (
        completed.id == task.id
        and completed.repository_id == task.repository_id
        and completed.run_config == task.run_config
        and completed.status == "completed"
    ):
        raise TaskExecutionError("Experiment completion failed")


    # 4. 返回
    return completed


def read_experiment_report(
    preparation: ExperimentPreparation,
) -> TaskExecutionReport:
    # 1. 检查 preparation.status == "prepared"，
    #    且 task_id、repository_id 不为 None。
    if (
        preparation.status != "prepared"
        or preparation.task_id is None
        or preparation.repository_id is None
    ):
        raise TaskExecutionError("Experiment report is not prepared")

    # 2. 调用
    report = task_report_service.get_task_execution_report(
        preparation.task_id
    )


    # 3. 检查报告存在，并核对 report.task：
    #    id、repository_id、run_config、
    #    user_request、task_type 与准备记录一致。
    if report is None:
        raise TaskExecutionError("Experiment report not prepared")

    if not (
        report.task.id == preparation.task_id
        and report.task.repository_id == preparation.repository_id
        and report.task.run_config == preparation.run_config
        and report.task.user_request == preparation.case.user_request.strip()
        and report.task.task_type == "plan"
    ):
        raise TaskExecutionError("Report task does not match experiment preparation")

    if (
        report.test_run is not None
        and report.test_run.task_id != preparation.task_id
    ):
        raise TaskExecutionError(
            "Report test run does not belong to experiment task"
        )

    return report