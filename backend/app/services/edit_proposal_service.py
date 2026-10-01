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
from ..db.repositories import task_event_repo
from ..schemas.reflection import ReflectionFinishedEventPayload


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


def generate_task_reflection_edit(
    task_id: UUID,
    *,
    file_path: str,
) -> TaskFileEditRead | None:
    """
    使用最近一次有效 Reflection action 为指定文件生成候选。
    只生成候选，不直接写入工作副本。
    """

    if not isinstance(file_path, str) or not file_path.endswith(".py"):
        raise InvalidTaskInputError(
            "Target file must be a Python file"
        )

    with SessionLocal() as session:
        # 查询任务；不存在返回 None。
        task = get_task(session, task_id=task_id)

        if task is None:
            return None

        # 必须是 approved、executing 的 plan 任务。
        if (
            task.task_type != "plan"
            or task.status != "executing"
            or task.review_decision != "approved"
        ):
            raise TaskStateConflictError("Task is not ready for reflection repair")

        # 校验已保存的 TaskPlanResult 及 repository_id。
        try:
            plan_result = TaskPlanResult.model_validate(task.result)
        except ValidationError as exc:
            raise TaskExecutionError("Stored plan is invalid") from exc

        if plan_result.repository_id != task.repository_id:
            raise TaskExecutionError("Stored plan repository does not match task")

        # 读取最近一次 REFLECTION_FINISHED。
        reflection_event = task_event_repo.get_latest_task_event_by_type(
            session,
            task_id=task_id,
            event_type="REFLECTION_FINISHED"
        )

        if reflection_event is None:
            raise TaskStateConflictError("Task has no completed reflection decision")

        # 验证 reflection_event.payload。
        try:
            reflection_payload = ReflectionFinishedEventPayload.model_validate(reflection_event.payload)
        except ValidationError as exc:
            raise TaskExecutionError("Stored reflection decision is invalid") from exc

        # payload 内 sequence 必须与事件 sequence 一致。
        if reflection_payload.sequence != reflection_event.sequence:
            raise TaskExecutionError("Stored reflection payload sequence does not match its event")

        # Reflection attempt 必须对应任务当前 retry_count。
        if reflection_payload.attempt != task.retry_count:
            raise TaskStateConflictError("Reflection decision is stale")

        # should_retry 必须为 True。
        if not reflection_payload.decision.should_retry:
            raise TaskStateConflictError("Reflection did not request a repair")

        latest_test_event = task_event_repo.get_latest_task_event_by_type(
            session,
            task_id=task.id,
            event_type="TEST_EXECUTION_FINISHED",
        )

        if latest_test_event is None:
            raise TaskExecutionError("Referenced test result is unavailable")

        if latest_test_event.sequence != reflection_payload.test_event_sequence:
            raise TaskStateConflictError("Reflection decision is stale")

        if latest_test_event.sequence >= reflection_event.sequence:
            raise TaskExecutionError("Stored reflection event order is invalid")

        for event_type in (
            "TEST_EXECUTION_STARTED",
            "TEST_EXECUTION_FAILED",
        ):
            newer_event = task_event_repo.get_latest_task_event_by_type(
                session,
                task_id=task_id,
                event_type=event_type
            )

            if newer_event is not None and newer_event.sequence > reflection_event.sequence:
                raise TaskStateConflictError("A newer test attempt invalidated the reflection decision")

        # 从 decision.actions 中查找 file_path 完全相同的 action。
        action = next(
            (
                candidate
                for candidate in reflection_payload.decision.actions
                if candidate.file_path == file_path
            ),
            None,
        )

        if action is None:
            raise PlanScopeViolationError("File is not included in the reflection decision")

        approved_files = {
            approved_file
            for step in plan_result.plan.steps
            for approved_file in step.files
        }

        if file_path not in approved_files:
            raise PlanScopeViolationError("Reflection target is outside the approved plan")

        # 查询 Repository 并检查 workspace_path。
        repository = get_repository(session, task.repository_id)

        if repository is None or not repository.workspace_path:
            raise TaskExecutionError("Task workspace is unavailable")

        repository_id = repository.id
        workspace_path = Path(repository.workspace_path)
        user_request = task.user_request
        plan = plan_result.plan
        repair_instruction = action.instruction

    # 从这里开始数据库会话已经关闭。
    

    target = resolve_workspace_target(
        workspace_path,
        file_path,
    )

    try:
        snapshot = read_file_snapshot(
            workspace_path,
            target,
            max_bytes=MAX_EDIT_INPUT_BYTES,
        )
    except FileSkippedError as exc:
        raise InvalidTaskInputError("Source file exceeds limits or contains null bytes") from exc

    try:
        original_content = snapshot.content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidTaskInputError("Source file must use UTF-8 encoding") from exc

    # 调用扩展后的 generate_file_edit，
    # 将 repair_instruction 一并传入。
    proposal = generate_file_edit(
        user_request,
        plan=plan,
        file_path=file_path,
        original_content=original_content,
        repair_instruction=repair_instruction,
    )

    return TaskFileEditRead(
        task_id=task_id,
        repository_id=repository_id,
        base_file_hash=snapshot.metadata.file_hash,
        proposal=proposal,
    )