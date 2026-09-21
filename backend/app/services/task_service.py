from uuid import UUID

from ..schemas.agent import AgentQuestionResponse
from ..db.repositories.task_repo import get_task_for_update, mark_task_running
from .agent_service import run_readonly_agent
from ..core.exceptions import InvalidTaskInputError, TaskStateConflictError, TaskExecutionError
from ..db.repositories.repository_repo import get_repository
from ..db.session import SessionLocal
from ..schemas.task import TaskCreate, TaskRead
from ..db.repositories import task_repo

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

        # 4. mark_task_running，退出事务并提交。
        mark_task_running(session, task)

    try:
        # 执行阶段：在任务事务外调用 Agent。
        result = run_readonly_agent(
            repository_id,
            question=user_request,
            max_tool_calls=4,
        )

        # 5. result 为 None，抛 TaskExecutionError。
        # 提示：任务存在，但它对应的仓库已不可用。
        if result is None:
            raise TaskExecutionError("repository is unavailable.")

        # 6. 转换为 AgentQuestionResponse，再得到 saved_result。
        response = AgentQuestionResponse(**result, repository_id=repository_id)
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

            task_repo.mark_task_completed(session, task, result=saved_result)

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
                if task and task.status == "running":
                    task_repo.mark_task_failed(session, task, error="Task execution failed; see server logs.")

        except Exception:
            logger.exception(
                "Failed to persist task failure; task_id=%s",
                task_id,
            )

        # 重新抛出外层捕获的原始异常。
        raise