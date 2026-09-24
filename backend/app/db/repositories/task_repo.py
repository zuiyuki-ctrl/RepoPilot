from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models import AgentTask


def create_task(
    session: Session,
    *,
    repository_id: UUID,
    user_request: str,
    task_type: str,
) -> AgentTask:

    task = AgentTask(
        repository_id=repository_id,
        user_request=user_request,
        task_type=task_type,
        status="created",
    )

    session.add(task)

    session.flush()

    return task


def get_task(
    session: Session,
    task_id: UUID,
) -> AgentTask | None:
    return session.get(AgentTask, task_id)

def get_task_for_update(
    session: Session,
    task_id: UUID,
) -> AgentTask | None:
    # 1. select(AgentTask)，按 id 筛选。
    statement = select(AgentTask).where(AgentTask.id == task_id)

    # 2. 添加 with_for_update()。
    statement = statement.with_for_update()

    # 3. 返回 scalar_one_or_none()。
    return session.execute(statement).scalar_one_or_none()


def mark_task_running(
    session: Session,
    task: AgentTask,
) -> None:
    # 1. status 设置为 running。
    task.status = "running"

    # 2. started_at 设置为当前 UTC 时间。
    task.started_at = datetime.now(timezone.utc)

    # 3. session.flush，不 commit。
    session.flush()


def mark_task_completed(
    session: Session,
    task: AgentTask,
    *,
    result: dict,
) -> None:
    # 1. status 设置为 completed。
    task.status = "completed"

    # 2. 保存 result，error 设为 None。
    task.result = result
    task.error = None

    # 3. 填写 completed_at，flush。
    task.completed_at = datetime.now(timezone.utc)
    session.flush()


def mark_task_failed(
    session: Session,
    task: AgentTask,
    *,
    error: str,
) -> None:
    # 1. status 设置为 failed。
    task.status = "failed"

    # 2. 保存受控错误说明，result 设为 None。
    task.result = None
    task.error = error

    # 3. 填写 completed_at，flush。
    task.completed_at = datetime.now(timezone.utc)
    session.flush()


# 是否允许审核，由服务层判断；数据访问层只负责落实已确定的变更
def save_plan_review(
    session: Session,
    task: AgentTask,
    *,
    decision: str,
    comment: str | None,
) -> None:
    # 1. 设置 review_decision 和 review_comment。
    task.review_decision = decision
    task.review_comment = comment

    # 2. reviewed_at 使用 datetime.now(timezone.utc)。
    task.reviewed_at = datetime.now(timezone.utc)

    # 3. session.flush()，不 commit。
    session.add(task)
    session.flush()