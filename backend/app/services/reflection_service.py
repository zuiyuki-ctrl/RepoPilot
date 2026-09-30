from dataclasses import dataclass
from uuid import UUID

from pydantic import ValidationError

from ..core.exceptions import (
    RetryBudgetExceededError,
    TaskExecutionError,
    TaskStateConflictError,
)
from ..db.repositories import task_event_repo, task_repo
from ..db.session import SessionLocal
from ..schemas.task import TaskPlanResult
from ..schemas.testing import TestExecutionEventPayload


@dataclass(frozen=True)
class ReflectionContext:
    task_id: UUID
    repository_id: UUID
    user_request: str
    plan: TaskPlanResult

    test_stdout: str
    test_stderr: str
    test_exit_code: int | None
    test_timed_out: bool

    retry_count: int
    max_retries: int
    test_event_sequence: int


# 原子领取一次 Reflection 重试额度
def begin_task_reflection(
    task_id: UUID,
) -> ReflectionContext | None:
    """
    原子领取一次 Reflection 重试额度，并返回脱离 ORM 会话后
    仍可安全使用的上下文。任务不存在时返回 None。
    """

    with SessionLocal.begin() as session:
        # 使用 get_task_for_update 锁定任务。
        task = task_repo.get_task_for_update(session, task_id)

        if task is None:
            return None

        # 必须同时满足：
        # - task_type == "plan"
        # - status == "executing"
        # - review_decision == "approved"
        if (
            task.task_type != "plan"
            or task.status != "executing"
            or task.review_decision != "approved"
        ):
            raise TaskStateConflictError("Task is not ready for reflection")

        # 验证 task.result
        try:
            plan_result = TaskPlanResult.model_validate(task.result)
        except ValidationError as exc:
            raise TaskExecutionError("Stored plan is invalid") from exc

        # plan_result.repository_id 必须等于 task.repository_id。
        if plan_result.repository_id != task.repository_id:
            raise TaskExecutionError("Stored plan repository does not match task")

        # 查询最近一次 TEST_EXECUTION_FINISHED。
        test_event = task_event_repo.get_latest_task_event_by_type(
            session,
            task_id=task_id,
            event_type="TEST_EXECUTION_FINISHED",
        )

        if test_event is None:
            raise TaskStateConflictError("Task has no completed test result")

        # 使用 TestExecutionEventPayload 验证 test_event.payload。
        try:
            test_payload = TestExecutionEventPayload.model_validate(test_event.payload)
        except ValidationError as exc:
            raise TaskExecutionError("Stored test result is invalid") from exc

        # 已通过测试的任务不能进入 Reflection。
        if test_payload.passed:
            raise TaskStateConflictError("Passed tests do not require reflection")

        # 没有剩余预算时抛 RetryBudgetExceededError。
        if task.retry_count >= task.max_retries:
            raise RetryBudgetExceededError("Task retry budget is exhausted")

        # 调用 mark_task_reflecting。
        # 该方法会同时 retry_count += 1。
        task_repo.mark_task_reflecting(session, task)

        # 此处必须在 mark_task_reflecting 之后读取 retry_count，
        # 它表示即将执行的修复轮次。
        reflection_attempt = task.retry_count

        # 记录 REFLECTION_STARTED。
        task_event_repo.append_task_event(
            session,
            task_id=task.id,
            event_type="REFLECTION_STARTED",
            node_name="reflection_service",
            message="Reflection started",
            payload={
                "step_id": "reflect",
                "attempt": reflection_attempt,
                "retry_count": reflection_attempt,
                "max_retries": task.max_retries,
                "test_event_sequence": test_payload.sequence,
            },
        )

        # 在事务内提取普通值和 Pydantic 对象，
        # 不把 task/test_event ORM 对象带出会话。
        context = ReflectionContext(
            task_id=task.id,
            repository_id=task.repository_id,
            user_request=task.user_request,
            plan=plan_result,
            test_stdout=test_payload.stdout,
            test_stderr=test_payload.stderr,
            test_exit_code=test_payload.exit_code,
            test_timed_out=test_payload.timed_out,
            retry_count=reflection_attempt,
            max_retries=task.max_retries,
            test_event_sequence=test_payload.sequence,
        )

    return context