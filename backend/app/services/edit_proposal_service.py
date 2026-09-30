from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from ..agent.edit_generation import MAX_EDIT_INPUT_BYTES, generate_file_edit
from .repository_scanner import read_file_snapshot
from ..db.repositories.repository_repo import get_repository
from .workspace_edit_service import resolve_workspace_target
from ..core.exceptions import (
    TaskStateConflictError,
    TaskExecutionError,
    PlanScopeViolationError,
    InvalidTaskInputError,
    FileSkippedError
)
from ..schemas.task import TaskPlanResult
from ..db.repositories.task_repo import get_task
from ..db.session import SessionLocal
from ..schemas.edit import TaskFileEditRead


# 为执行中的已批准计划生成文件候选：检查任务及文件范围，读取原文快照，再在数据库会话外调用模型。
# 返回候选与原文 hash；应用时用这个 hash 检查文件是否已变化，此处不写文件。
def generate_task_file_edit(
    task_id: UUID,
    *,
    file_path: str,
) -> TaskFileEditRead | None:

    # 第一阶段，在 with SessionLocal() as session: 内读取并检查任务
    with SessionLocal() as session:

        task = get_task(session, task_id=task_id)
        if task is None:
            return None

        if task.task_type != "plan" or task.status != "executing" or task.review_decision != "approved":
            raise TaskStateConflictError("Task is not executing")

        # 用 TaskPlanResult.model_validate(task.result) 解析存储结果。ValidationError 转成 TaskExecutionError。
        try:
            plan_result = TaskPlanResult.model_validate(task.result)
        except ValidationError as exc:
            raise TaskExecutionError("Stored plan is invalid") from exc

        # 检查结果里的 repository_id 与任务一致。
        if plan_result.repository_id != task.repository_id:
            raise TaskExecutionError("Stored plan repository does not match task")

        # 从 plan.steps 收集所有 files；目标不在集合中，抛 PlanScopeViolationError。
        files = {
            path
            for step in plan_result.plan.steps
            for path in step.files
        }

        if file_path not in files:
            raise PlanScopeViolationError

        # 查询仓库；不存在或缺少 workspace_path，抛 TaskExecutionError。
        repository = get_repository(session, repository_id=task.repository_id)
        if repository is None or not repository.workspace_path:
            raise TaskExecutionError

        # 保存后面需要的普通变量：repository_id、workspace_path、user_request、plan，然后退出会话。
        repository_id = repository.id
        workspace_path = Path(repository.workspace_path)
        user_request = task.user_request
        plan = plan_result.plan


    # 1. 检查 file_path 是字符串，且以 ".py" 结尾。
    #    不符合抛 InvalidTaskInputError。
    if not isinstance(file_path, str) or not file_path.endswith(".py"):
        raise InvalidTaskInputError("Target file must be a Python file")

    # 2. 使用 resolve_workspace_target(workspace_path, file_path)。
    #    复用路径边界、链接和 .git 拒绝规则。
    target = resolve_workspace_target(workspace_path, file_path)

    # 3. 调用 read_file_snapshot：
    try:
        snapshot = read_file_snapshot(workspace_path, target, max_bytes=MAX_EDIT_INPUT_BYTES)
    except FileSkippedError as exc:
        raise InvalidTaskInputError("Source file exceeds limits or contains null bytes") from exc

    # 4. 保存 snapshot.metadata.file_hash。
    file_hash = snapshot.metadata.file_hash

    # 5. 将 snapshot.content 解码成 original_content。
    try:
        original_content = snapshot.content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidTaskInputError("Source file must use UTF-8 encoding") from exc

    # 1. 调用 generate_file_edit：
    #    user_request、plan、file_path、original_content。
    proposal = generate_file_edit(
        user_request,
        plan=plan,
        file_path=file_path,
        original_content=original_content,
    )

    # 2. 构造 TaskFileEditRead：
    #    task_id、repository_id、
    #    base_file_hash=snapshot.metadata.file_hash、
    #    proposal=生成结果。
    return TaskFileEditRead(
        task_id=task_id,
        repository_id=repository_id,
        base_file_hash=file_hash,
        proposal=proposal,
    )