from uuid import UUID

from pydantic import ValidationError

from ..schemas.task_event import TaskEventRead
from ..schemas.agent import AgentQuestionResponse
from ..db.repositories.task_repo import get_task_for_update, mark_task_running
from .agent_service import run_readonly_agent, run_planning_agent
from ..core.exceptions import InvalidTaskInputError, TaskStateConflictError, TaskExecutionError
from ..db.repositories.repository_repo import get_repository
from ..db.session import SessionLocal
from ..schemas.task import TaskCreate, TaskRead, TaskPlanResult, TaskPlanReviewRequest
from ..db.repositories import task_repo, task_event_repo

import logging

logger = logging.getLogger(__name__)


def create_task(data: TaskCreate) -> TaskRead | None:
    # 1. 对 user_request 做 strip。
    user_request = data.user_request.strip()
    if user_request == "":
        raise InvalidTaskInputError("requestion must not be empty")

    # 2. 使用 SessionLocal.begin() 开启事务。
    with SessionLocal.begin() as session:
        # 3. 在同一个 session 中查询 repository。
        repository = get_repository(session, data.repository_id)

        # 4. 仓库不存在返回 None。
        if repository is None:
            return None

        # 5. 调用 task_repo.create_task。
        task = task_repo.create_task(
            session,
            repository_id=data.repository_id,
            user_request=user_request,
            task_type=data.task_type
        )
        # 6. 会话内转换为 TaskRead，保存为 result。
        result = TaskRead.model_validate(task)
    # 7. 退出事务、提交成功后返回 result。
    return result


def get_task(task_id: UUID) -> TaskRead | None:
    # 1. 使用 SessionLocal()。
    with SessionLocal() as session:
        # 2. 调用 task_repo.get_task。
        task = task_repo.get_task(session, task_id)

        # 3. 不存在返回 None，否则会话内转换为 TaskRead。
        if task is None:
            return None

        result = TaskRead.model_validate(task)

    return result


def run_task(task_id: UUID) -> TaskRead | None:
    with SessionLocal.begin() as session:
        # 1. 事务 A：调用 get_task_for_update。
        task = get_task_for_update(session, task_id)

        # 2. 不存在返回 None；status != "created" 抛 TaskStateConflictError。
        if task is None:
            return None

        if task.status != "created":
            raise TaskStateConflictError()

        # 3. 保存后续使用的 repository_id、user_request。
        repository_id = task.repository_id
        user_request = task.user_request.strip()
        task_type = task.task_type

        # 4. mark_task_running，退出事务并提交。
        mark_task_running(session, task)
        task_event_repo.append_task_event(
            session,
            task_id=task_id,
            event_type="TASK_STARTED",
            node_name="task_service",
            message="Task started",
            payload={
                "attempt": 1,
                "step_id": "task",
                "started_at": task.started_at.isoformat(),
            }
        )

    """将单个 Agent 内部事件立即提交到数据库。"""

    def persist_agent_event(
            *,
            event_type: str,
            node_name: str,
            message: str,
            payload: dict,
    ) -> None:

        with SessionLocal.begin() as session:
            # 锁定当前任务。
            current_task = get_task_for_update(session, task_id)

            # 如果任务已经不存在，抛出 TaskExecutionError。
            if current_task is None:
                raise TaskExecutionError()

            # Graph 执行期间任务必须是 running。
            # 如果不是 running，抛出 TaskStateConflictError。
            if current_task.status != "running":
                raise TaskStateConflictError()

            # 调用 append_task_event：
            task_event_repo.append_task_event(
                session,
                task_id=task_id,
                event_type=event_type,
                node_name=node_name,
                message=message,
                payload=payload
            )

    try:
        # 执行阶段：在任务事务外调用 Agent
        if task_type == "question":
            result = run_readonly_agent(
                repository_id,
                question=user_request,
                max_tool_calls=4,
                event_sink=persist_agent_event
            )

            if result is None:
                raise TaskExecutionError("repository is unavailable.")

            response = AgentQuestionResponse(
                **result,
                repository_id=repository_id
            )


        elif task_type == "plan":

            plan = run_planning_agent(
                repository_id,
                user_request=user_request,
                max_tool_calls=4,
                event_sink=persist_agent_event
            )
            #     # 2. 返回 None 时抛 TaskExecutionError。
            if plan is None:
                raise TaskExecutionError("repository is unavailable.")

            # 3. 构造 TaskPlanResult，保存为 response。
            response = TaskPlanResult(
                repository_id=repository_id,
                plan=plan
            )

        else:
            raise TaskExecutionError("Unsupported task type")

        saved_result = response.model_dump(mode="json")

        # 事务 B：保存成功结果。
        with SessionLocal.begin() as session:
            # 7. 重新用 get_task_for_update 查询并加锁。
            # 不要沿用事务 A 的 task 对象。
            task = get_task_for_update(session, task_id)

            # 8. 任务消失：抛 TaskExecutionError。
            # 状态不是 running：抛 TaskStateConflictError。
            if task is None:
                raise TaskExecutionError()

            if task.status != "running":
                raise TaskStateConflictError()

            if task_type == "question":
                # 调用 mark_task_completed。
                # 记录现有 TASK_COMPLETED。
                task_repo.mark_task_completed(session, task=task, result=saved_result)

                task_event_repo.append_task_event(
                    session,
                    task_id=task_id,
                    event_type="TASK_COMPLETED",
                    node_name="task_service",
                    message="Task completed",
                    payload={
                        "attempt": 1,
                        "step_id": "task",
                        "started_at": task.started_at.isoformat(),
                        "completed_at": task.completed_at.isoformat(),
                        "duration_ms": int((task.completed_at - task.started_at).total_seconds() * 1000),
                    }
                )
            else:
                # 调用 mark_task_awaiting_review。
                # 记录 TASK_AWAITING_REVIEW。
                task_repo.mark_task_awaiting_review(session, task=task, result=saved_result)

                task_event_repo.append_task_event(
                    session,
                    task_id=task_id,
                    event_type="TASK_AWAITING_REVIEW",
                    node_name="task_service",
                    message="Task is awaiting plan review",
                    payload={
                        "attempt": 1,
                        "step_id": "plan_review",
                    },
                )

            # 9. 在 Session 内转成 TaskRead，保存到 task_read。
            task_read = TaskRead.model_validate(task)

        # 到这里，事务 B 已提交成功。
        return task_read

    except Exception:
        logger.exception("Task execution failed; task_id=%s", task_id)

        try:
            # 事务 C：尽力记录失败状态。
            with SessionLocal.begin() as session:
                # 7. 重新查询并加锁。
                task = get_task_for_update(session, task_id)

                # 8. 仅当任务存在且仍为 running：
                # 调用 task_repo.mark_task_failed，
                # error 使用固定说明，例如：
                # "Task execution failed; see server logs."
                if task is not None and task.status == "running":
                    task_repo.mark_task_failed(session, task, error="Task execution failed; see server logs.")

                    task_event_repo.append_task_event(
                        session,
                        task_id=task_id,
                        event_type="TASK_FAILED",
                        node_name="task_service",
                        message="Task failed",
                        payload={
                            "attempt": 1,
                            "step_id": "task",
                            "started_at": task.started_at.isoformat(),
                            "completed_at": task.completed_at.isoformat(),
                            "duration_ms": int((task.completed_at - task.started_at).total_seconds() * 1000),
                            "description": "Task execution failed; see server logs",
                        }
                    )

        except Exception:
            logger.exception(
                "Failed to persist task failure; task_id=%s",
                task_id,
            )

        # 重新抛出外层捕获的原始异常。
        raise


# python -m alembic revision --autogenerate -m "create task_events table"
# python -m alembic upgrade head

def list_task_events(
        task_id: UUID,
        *,
        after_sequence: int = 0,
        limit: int = 50,
) -> list[TaskEventRead] | None:
    # 1. 校验 after_sequence >= 0，1 <= limit <= 100。
    if after_sequence < 0:
        raise InvalidTaskInputError("after_sequence must be nonnegative")

    if not 1 <= limit <= 100:
        raise InvalidTaskInputError("limit must be between 1 and 100")

    # 2. 使用 SessionLocal()。
    with SessionLocal() as session:
        # 3. 查询任务，不存在返回 None。
        task = task_repo.get_task(session, task_id)
        if task is None:
            return None

        # 4. 调用事件数据访问层。
        events = task_event_repo.list_task_events(
            session,
            task_id=task_id,
            after_sequence=after_sequence,
            limit=limit,
        )

        # 5. 在会话内转换成 TaskEventRead 列表。
        result: list[TaskEventRead] = []

        for event in events:
            result.append(TaskEventRead.model_validate(event))

        return result


# 用户对已经生成的计划作出批准或拒绝决定，程序保存决定，并记录审核事件。
def review_task_plan(
        task_id: UUID,
        data: TaskPlanReviewRequest,
) -> TaskRead | None:
    # 1. 清理 comment；空白评论转换为 None。
    comment = data.comment

    if comment is not None:
        comment = comment.strip()

        if not comment:
            comment = None

    # 2. SessionLocal.begin() 开启事务。
    with SessionLocal.begin() as session:
        # 3. 使用 get_task_for_update 锁定任务；不存在返回 None。
        task = get_task_for_update(session, task_id)
        if task is None:
            return None

        # 4. 检查类型、执行状态及是否已经审核。
        if task.task_type != "plan":
            raise TaskStateConflictError("Only plan tasks can be reviewed")

        # 状态不是 completed，抛 TaskStateConflictError。
        if task.status != "awaiting_review":
            raise TaskStateConflictError("Only tasks awaiting review can be reviewed")

        # review_decision 不是 None，抛 TaskStateConflictError。
        if task.review_decision is not None:
            raise TaskStateConflictError("Task has already been reviewed")

        # 5. 校验保存的计划结果。
        try:
            saved_plan = TaskPlanResult.model_validate(task.result)
        except ValidationError as exc:
            raise TaskExecutionError("Stored plan is invalid") from exc

        if saved_plan.repository_id != task.repository_id:
            raise TaskExecutionError("Stored plan repository does not match task")

        # 6. 调用 task_repo.save_plan_review
        task_repo.save_plan_review(
            session,
            task,
            decision=data.decision,
            comment=comment
        )

        # 7. 使用同一个 session 调用 append_task_event。
        task_event_repo.append_task_event(
            session,
            task_id=task.id,
            event_type=(
                "HUMAN_APPROVED"
                if data.decision == "approved"
                else "HUMAN_REJECTED"
            ),
            node_name="task_service",
            message=(
                "Plan approved"
                if data.decision == "approved"
                else "Plan rejected"
            ),
            payload={
                "step_id": "plan_review",
                "attempt": 1,
                "decision": data.decision,
                "comment": comment,
                "reviewed_at": task.reviewed_at.isoformat(),
            }
        )

        # 8. 在会话内转换成 TaskRead。
        result = TaskRead.model_validate(task)

    # 9. 退出事务成功后返回。
    return result
