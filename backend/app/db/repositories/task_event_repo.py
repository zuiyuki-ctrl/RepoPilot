from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..models import TaskEvent


# 为任务分配递增序号并追加事件，形成可查询的执行历史；调用方须在同一事务锁定任务行。
# 复制 payload 并补充协议版本和序号，只 flush，不自行提交。
def append_task_event(
    session: Session,
    *,
    task_id: UUID,
    event_type: str,
    node_name: str,
    message: str,
    payload: dict,
) -> TaskEvent:
    # 1. 前置条件：调用方已在当前事务锁定对应 AgentTask 行。
    # 2. 查询该任务现有最大的 sequence；没有事件时按 0 处理。
    statement = select(func.max(TaskEvent.sequence)).where(
        TaskEvent.task_id == task_id,
    )

    # 3. 新 sequence = 最大值 + 1。
    max_sequence = session.execute(statement).scalar_one()
    sequence = (max_sequence if max_sequence is not None else 0) + 1

    # 4. 复制 payload，再由程序填入 sequence 和 schema_version=1。
    event_payload = dict(payload)
    event_payload["sequence"] = sequence
    event_payload["schema_version"] = 1

    # 5. 创建 TaskEvent，add、flush，返回对象；不 commit。
    task_event = TaskEvent(
        task_id=task_id,
        event_type=event_type,
        node_name=node_name,
        message=message,
        payload=event_payload,
        sequence=sequence,
    )

    session.add(task_event)
    session.flush()
    return task_event


# 按任务和严格大于 after_sequence 的条件升序读取事件，支持前端增量获取执行进度。
def list_task_events(
    session: Session,
    *,
    task_id: UUID,
    after_sequence: int,
    limit: int,
) -> list[TaskEvent]:
    # 1. 按 task_id 筛选。
    statement = select(TaskEvent).where(TaskEvent.task_id == task_id)

    # 2. 筛选 sequence > after_sequence。
    statement = statement.where(TaskEvent.sequence > after_sequence)

    # 3. 按 sequence 升序。
    statement = statement.order_by(TaskEvent.sequence)

    # 4. 应用 limit，返回列表。
    statement = statement.limit(limit)
    return list(session.scalars(statement).all())


# 读取最近测试事件的方法
def get_latest_task_event_by_type(
    session: Session,
    *,
    task_id: UUID,
    event_type: str,
) -> TaskEvent | None:
    """
    按 sequence 查找任务最近一次指定类型的事件。
    """

    # 查询 TaskEvent，并同时按 task_id 和 event_type 筛选。
    statement = select(TaskEvent).where(TaskEvent.task_id == task_id, TaskEvent.event_type == event_type)

    # 按 sequence 倒序，只取一条。
    statement = statement.order_by(TaskEvent.sequence.desc()).limit(1)

    # 返回 ORM 对象或 None
    return session.execute(statement).scalar_one_or_none()