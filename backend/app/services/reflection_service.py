from dataclasses import dataclass
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from .test_run_service import check_test_run_snapshot
from ..schemas.reflection import ReflectionDecision
from ..core.exceptions import (
    RetryBudgetExceededError,
    TaskExecutionError,
    TaskStateConflictError,
)
from ..db.repositories import task_event_repo, task_repo, test_run_repo
from ..db.session import SessionLocal
from ..schemas.task import TaskPlanResult
from ..schemas.testing import TestExecutionEventPayload

import logging

from ..agent.reflection_generation import generate_reflection_decision

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReflectionContext:
    task_id: UUID
    repository_id: UUID
    user_request: str
    plan: TaskPlanResult

    test_result: TestExecutionEventPayload

    retry_count: int
    max_retries: int
    test_event_sequence: int


# 为失败测试领取一次反思机会：锁定任务，确认选中的是最新一轮完整测试结果，并校验事件数据。
# 校验通过后在同一事务内增加重试次数、切换为 reflecting、记录 REFLECTION_STARTED。
# 预算耗尽时保留计划并提交失败终态，再在事务外抛出预算异常。
# 返回脱离会话的上下文，供后续模型分析使用；这里不调用模型，也不执行修复。
def begin_task_reflection(
        task_id: UUID,
) -> ReflectionContext | None:
    """
    原子领取一次 Reflection 重试额度，并返回脱离 ORM 会话后
    仍可安全使用的上下文。任务不存在时返回 None。
    """

    context: ReflectionContext | None = None
    budget_exhausted = False

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

        for event_type in (
                "TEST_EXECUTION_STARTED",
                "TEST_EXECUTION_FAILED",
                "FILE_MODIFIED",
        ):
            newer_event = task_event_repo.get_latest_task_event_by_type(
                session,
                task_id=task_id,
                event_type=event_type,
            )

            if newer_event is not None and newer_event.sequence > test_event.sequence:
                raise TaskStateConflictError("Reflection requires the latest complete test result")

        # 使用 TestExecutionEventPayload 验证 test_event.payload。
        try:
            test_payload = TestExecutionEventPayload.model_validate(test_event.payload)
        except ValidationError as exc:
            raise TaskExecutionError("Stored test result is invalid") from exc

        if test_payload.sequence != test_event.sequence:
            raise TaskExecutionError("Stored test payload sequence does not match its event")

        # 已通过测试的任务不能进入 Reflection。
        if test_payload.passed:
            raise TaskStateConflictError("Passed tests do not require reflection")

        previous_reflection = task_event_repo.get_latest_task_event_by_type(
            session,
            task_id=task_id,
            event_type="REFLECTION_STARTED"
        )
        if previous_reflection and previous_reflection.sequence > test_event.sequence:
            raise TaskStateConflictError("Run tests again before starting another reflection")

        _require_current_failed_test(
            session,
            task_id=task.id,
            repository_id=task.repository_id,
            test_payload=test_payload,
        )

        if task.retry_count >= task.max_retries:
            error = "Task retry budget is exhausted"
            task_repo.mark_plan_task_failed(session, task=task, error=error)
            task_event_repo.append_task_event(
                session,
                task_id=task.id,
                event_type="TASK_FAILED",
                node_name="reflection_service",
                message=error,
                payload={
                    "step_id": "reflect",
                    "attempt": task.retry_count + 1,
                    "reason_code": "retry_budget_exhausted",
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                    "test_event_sequence": test_event.sequence,
                    "error": error,
                },
            )
            budget_exhausted = True
        else:
            task_repo.mark_task_reflecting(session, task)
            reflection_attempt = task.retry_count
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
                    "test_event_sequence": test_event.sequence,
                },
            )
            context = ReflectionContext(
                task_id=task.id,
                repository_id=task.repository_id,
                user_request=task.user_request,
                plan=plan_result,
                test_result=test_payload,
                retry_count=reflection_attempt,
                max_retries=task.max_retries,
                test_event_sequence=test_payload.sequence,
            )

    if budget_exhausted:
        raise RetryBudgetExceededError("Task retry budget is exhausted")

    return context


# 成功收尾函数
def _finish_task_reflection(
        context: ReflectionContext,
        decision: ReflectionDecision,
) -> None:
    with SessionLocal.begin() as session:
        # 1. 锁定任务
        task = task_repo.get_task_for_update(session, context.task_id)

        if task is None:
            raise TaskExecutionError("Task disappeared during reflection")

        # 2. 检查当前任务仍属于本轮 Reflection。
        #    具体条件见下面。
        if not (
                task.task_type == "plan"
                and task.status == "reflecting"
                and task.review_decision == "approved"
                and task.retry_count == context.retry_count
        ):
            raise TaskStateConflictError("Task is no longer in this reflection attempt")

        # 3. 调用 task_repo.mark_task_executing(session, task)。
        if task.repository_id != context.repository_id:
            raise TaskExecutionError("Task repository changed during reflection")

        if decision.should_retry:
            # 模型提出了可靠修复方向，回到 executing，
            # 后续根据 actions 生成并应用修复。
            task_repo.mark_task_executing(session, task)
        else:
            # 模型认为证据不足，无法可靠修复，任务进入失败终态。
            task_repo.mark_plan_task_failed(
                session,
                task=task,
                error="Reflection could not identify a reliable repair",
            )

        # 4. 调用 task_event_repo.append_task_event，
        #    保存完整决策，参数见下面。
        task_event_repo.append_task_event(
            session,
            task_id=task.id,
            event_type="REFLECTION_FINISHED",
            node_name="reflection_service",
            message=(
                "Reflection repair decision generated"
                if decision.should_retry
                else "Reflection stopped without a reliable repair"
            ),
            payload={
                "step_id": "reflect",
                "attempt": context.retry_count,
                "test_event_sequence": context.test_event_sequence,
                "decision": decision.model_dump(mode="json"),
            }
        )


# 失败收尾函数
def _fail_task_reflection(
        context: ReflectionContext,
        error: Exception,
) -> None:
    with SessionLocal.begin() as session:
        # 1. 锁定任务。
        task = task_repo.get_task_for_update(session, context.task_id)

        # 2. 检查任务存在。
        if task is None:
            raise TaskExecutionError("Task disappeared during reflection")

        # 3. 使用与成功收尾相同的状态、轮次、仓库检查。
        if not (
                task.task_type == "plan"
                and task.status == "reflecting"
                and task.review_decision == "approved"
                and task.retry_count == context.retry_count
        ):
            raise TaskStateConflictError("Task is no longer in this reflection attempt")

        # 4. 调用 mark_task_executing。
        if task.repository_id != context.repository_id:
            raise TaskExecutionError("Task repository changed during reflection")

        task_repo.mark_task_executing(session, task)

        # 5. 追加 REFLECTION_FAILED 事件。
        task_event_repo.append_task_event(
            session,
            task_id=task.id,
            event_type="REFLECTION_FAILED",
            node_name="reflection_service",
            message="Reflection generation failed",
            payload={
                "step_id": "reflect",
                "attempt": context.retry_count,
                "test_event_sequence": context.test_event_sequence,
                "error_type": type(error).__name__,
                "error": "Reflection generation failed; see server logs.",
            }
        )


def run_task_reflection(
        task_id: UUID,
) -> ReflectionDecision | None:
    # 1. 调用 begin_task_reflection(task_id)，保存为 context。
    context = begin_task_reflection(task_id)

    # 2. context is None 时返回 None。
    if context is None:
        return None

    try:
        # 3. 调用 generate_reflection_decision
        decision = generate_reflection_decision(
            user_request=context.user_request,
            plan=context.plan.plan,
            test_result=context.test_result,
        )

    except Exception as exc:
        # 4. logger.exception 记录模型生成失败，
        #    日志包含 context.task_id 和 context.retry_count。
        logger.exception("Failed to generate reflection decision; task_id: %s\nretry_count: %s",
                         context.task_id,
                         context.retry_count
                         )

        try:
            # 5. 调用 _fail_task_reflection(context, exc)。
            _fail_task_reflection(context, exc)
        except Exception:
            # 6. logger.exception 记录恢复状态失败。
            #    不用这个新异常替换原异常。
            logger.exception(
                "Failed to restore task after reflection failure; "
                "task_id=%s; retry_count=%s",
                context.task_id,
                context.retry_count,
            )

        # 7. 裸 raise，重新抛出最初的生成异常。
        raise

    # 8. 在上面 try/except 外调用：
    #    _finish_task_reflection(context, decision)。
    _finish_task_reflection(context, decision)

    # 9. 返回 decision。
    return decision


# 在 Reflection 调用模型之前，检查它准备分析的失败测试是否仍然适用于当前源码
def _require_current_failed_test(
        session: Session,
        *,
        task_id: UUID,
        repository_id: UUID,
        test_payload: TestExecutionEventPayload,
) -> None:
    if test_payload.test_run_id is None:
        raise TaskStateConflictError("Test result has no run reference; run tests again")

    try:
        test_run_id = UUID(test_payload.test_run_id)
    except ValueError as exc:
        raise TaskExecutionError("Stored test run ID is invalid") from exc

    test_run = test_run_repo.get_test_run(
        session,
        task_id=task_id,
        test_run_id=test_run_id,
    )

    if test_run is None:
        raise TaskExecutionError("Referenced test run is missing")

    # 这条记录对应的是 TEST_EXECUTION_FINISHED，因此：
    # - test_run.status 必须为 "finished"；
    # - exit_code、timed_out 必须与事件相同；
    # - 根据记录计算的通过状态，必须与 test_payload.passed 相同。
    if not (
        test_run.status == "finished"
        and test_run.exit_code == test_payload.exit_code
        and test_run.timed_out == test_payload.timed_out
    ):
        raise TaskExecutionError("Stored test run and event results disagree")

    passed = not test_run.timed_out and test_run.exit_code == 0
    if passed != test_payload.passed:
        raise TaskExecutionError("Stored test run and event results disagree")

    validity = check_test_run_snapshot(
        session,
        repository_id=repository_id,
        test_run=test_run,
    )

    if validity.is_current is None:
        raise TaskStateConflictError("Test snapshot is unavailable; run tests again")

    if not validity.is_current:
        raise TaskStateConflictError("Workspace changed after testing; run tests again")
