from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from ..core.exceptions import (
    PlanScopeViolationError,
    TaskExecutionError,
    TaskStateConflictError,
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
    write_workspace_file,
)

def write_approved_plan_file(
    task_id: UUID,
    *,
    file_path: str,
    content: str,
) -> WorkspaceWriteResult | None:
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
        repository = repository_repo.get_repository(session, repository_id=task.repository_id)

        # 10. 仓库不存在或 workspace_path 为空时，
        #     抛 TaskExecutionError。
        if repository is None or not repository.workspace_path:
            raise TaskExecutionError()

        # 11. 调用原子写入函数。
        write_result = write_workspace_file(
            Path(repository.workspace_path),
            file_path=file_path,
            content=content,
        )

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