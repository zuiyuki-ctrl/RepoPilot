from pathlib import Path
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError

from ..schemas.edit import FileEditProposal
from ..agent.edit_generation import MAX_EDIT_INPUT_BYTES
from .repository_scanner import read_file_snapshot
from .workspace_git_service import read_workspace_diff
from ..schemas.workspace import TaskWorkspaceDiffRead
from ..core.exceptions import (
    PlanScopeViolationError,
    TaskExecutionError,
    TaskStateConflictError,
    RepositoryBusyError,
    WorkspaceWritePersistenceError,
    WorkspaceFileConflictError,
    InvalidTaskInputError
)
from ..db.repositories import (
    repository_repo,
    task_event_repo,
    task_repo,
)
from ..db.session import SessionLocal
from ..schemas.task import TaskPlanResult
from .workspace_edit_service import (
    WorkspaceWriteResult,
    write_workspace_file, resolve_workspace_target,
)

import re

HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")

import logging

logger = logging.getLogger(__name__)


# 校验计划批准状态及文件范围，锁定任务和仓库后写入工作副本，并记录 FILE_MODIFIED。
# 文件写入后持久化失败会单独报错，提示核实差异与事件；不会自动恢复原文件。
def write_approved_plan_file(
    task_id: UUID,
    *,
    file_path: str,
    content: str,
    expected_file_hash: str | None = None,
) -> WorkspaceWriteResult | None:
    file_written = False
    try:
        # 1. 开启数据库事务。
        with SessionLocal.begin() as session:
            # 2. 锁定任务。
            task = task_repo.get_task_for_update(session, task_id=task_id)

            # 3. 任务不存在时返回 None。
            if task is None:
                return None

            # 4. 检查这是已批准的计划任务
            if (
                    task.task_type != "plan"
                    or task.status != "approved"
                    or task.review_decision != "approved"
            ):
                raise TaskStateConflictError("Task is not approved for execution")

            # 5. 使用 TaskPlanResult 校验数据库中的 result。
            #    ValidationError 转换为 TaskExecutionError，
            #    并使用 raise ... from exc。
            try:
                saved_result = TaskPlanResult.model_validate(task.result)
            except ValidationError as exc:
                raise TaskExecutionError("Stored plan is invalid") from exc

            # 6. 保存结果中的 repository_id 必须等于 task.repository_id。
            if saved_result.repository_id != task.repository_id:
                raise TaskExecutionError("Stored plan repository does not match task")

            # 7. 从所有 plan.steps 收集允许修改的文件路径。
            #    使用集合，文件必须精确匹配，不做 strip 或大小写转换。
            approved_files = {
                file
                for step in saved_result.plan.steps
                for file in step.files
            }

            # 8. file_path 不在 approved_files 时，
            #    抛 PlanScopeViolationError。
            if file_path not in approved_files:
                raise PlanScopeViolationError("File is not included in the approved plan")

            # 9. 在同一个 session 中读取 Repository。
            try:
                repository = repository_repo.get_repository_for_update(session, repository_id=task.repository_id)
            except DBAPIError as exc:
                # getattr(exc.orig, "sqlstate", None)。
                attr = getattr(exc.orig, "sqlstate", None)

                # 等于 "55P03"：抛 RepositoryBusyError(...) from exc。
                if attr == "55P03":
                    raise RepositoryBusyError("Repository is busy") from exc

                # 其他数据库错误：原样 raise。
                raise

            # 10. 仓库不存在或 workspace_path 为空时，
            #     抛 TaskExecutionError。
            if repository is None or not repository.workspace_path:
                raise TaskExecutionError()

            # 10.1 expected_file_hash 不为 None 时，执行下面的检查。
            if expected_file_hash:
                # 10.2 使用 resolve_workspace_target 得到 target。
                target = resolve_workspace_target(
                    workspace_path=Path(repository.workspace_path),
                    file_path=file_path
                )

                # 10.3 使用 read_file_snapshot 读取当前文件
                snapshot = read_file_snapshot(target, Path(file_path), max_bytes=MAX_EDIT_INPUT_BYTES)

                # 10.4 比较 snapshot.metadata.file_hash 和 expected_file_hash。
                #    不一致时抛 WorkspaceFileConflictError。
                if snapshot.metadata.file_hash != expected_file_hash:
                    raise WorkspaceFileConflictError

                # 10.5 全部检查通过后，继续原有 write_workspace_file、事件记录和提交。

            # 11. 调用原子写入函数。
            write_result = write_workspace_file(
                Path(repository.workspace_path),
                file_path=file_path,
                content=content,
            )

            file_written = True

            # 12. 在同一事务中记录 FILE_MODIFIED。
            task_event_repo.append_task_event(
                session,
                task_id=task_id,
                event_type="FILE_MODIFIED",
                node_name="plan_execution_service",
                message="Workspace file modified",
                payload={
                    "step_id": "execute_plan",
                    "attempt": 1,
                    "file_path": write_result.file_path,
                    "created": write_result.created,
                    "bytes_written": write_result.bytes_written,
                },
            )

        # 13. 返回结果；不改变任务状态。
        return write_result

    except Exception as exc:
        if not file_written:
            raise

        logger.exception(
            "Workspace file written but persistence failed; task_id=%s; file_path=%s",
            task_id,
            file_path,
        )

        raise WorkspaceWritePersistenceError("Workspace file was written, but persistence was not confirmed; "
                                             "inspect diff and events before retrying") from exc


# 根据任务 ID 找到仓库工作副本，读取 Git 差异，再包装成接口返回的数据
def get_task_workspace_diff(
        task_id: UUID,
) -> TaskWorkspaceDiffRead | None:
    # 1. 使用 SessionLocal() 查询任务。
    with SessionLocal() as session:
        task = task_repo.get_task(session, task_id=task_id)

        # 2. 任务不存在，返回 None。
        if task is None:
            return None

        # 3. 非 plan 任务，抛 TaskStateConflictError。
        if task.task_type != "plan":
            raise TaskStateConflictError("Workspace diff is only available for plan tasks")

        # 4. 查询任务关联的 Repository。
        repository = repository_repo.get_repository(session, repository_id=task.repository_id)

        # 5. 仓库不存在或 workspace_path 为空，抛 TaskExecutionError。
        if repository is None or not repository.workspace_path:
            raise TaskExecutionError()

        # 6. 保存 repository_id 和 workspace_path，退出数据库会话。
        repository_id = task.repository_id
        workspace_path = Path(repository.workspace_path)

    # 7. 调用 read_workspace_diff。
    diff_result = read_workspace_diff(workspace_path)

    # 8. 构造 TaskWorkspaceDiffRead 并返回。
    return TaskWorkspaceDiffRead(
        task_id=task_id,
        repository_id=repository_id,
        diff=diff_result.diff,
        changed_files=diff_result.changed_files,
        untracked_files=diff_result.untracked_files,
        truncated=diff_result.truncated,
    )


def apply_task_file_edit(
    task_id: UUID,
    *,
    base_file_hash: str,
    proposal: FileEditProposal,
) -> WorkspaceWriteResult | None:
    # 1. 检查 base_file_hash 满足 64 位小写十六进制格式。
    #    不合法抛 InvalidTaskInputError。
    if not bool(HEX_64_PATTERN.match(base_file_hash)):
        raise InvalidTaskInputError("Invalid task hash")

    # 2. 检查 proposal.file_path 以 ".py" 结尾。
    #    不合法抛 InvalidTaskInputError。

    # 3. 再次校验候选源码，具体见下文。

    # 4. 调用 write_approved_plan_file：
    #    file_path=校验后的候选路径
    #    content=校验后的候选完整源码
    #    expected_file_hash=base_file_hash

    # 5. 返回写入结果。
    ...