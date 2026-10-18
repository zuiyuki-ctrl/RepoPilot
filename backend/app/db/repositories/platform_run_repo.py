from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import PlatformRun, PlatformRunEvent


def get_run(session: Session, run_id, *, for_update=False):
    statement = select(PlatformRun).where(PlatformRun.id == run_id)
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def list_runs(session: Session, *, limit: int, offset: int):
    return list(session.scalars(select(PlatformRun).order_by(
        PlatformRun.created_at.desc(), PlatformRun.id.desc()).limit(limit).offset(offset)))


def next_queued_for_update(session: Session):
    # 只提供领取原语；全局 worker 所有权与恢复在 Day 2 实现。
    return session.scalar(select(PlatformRun).where(PlatformRun.lifecycle == 'queued')
        .order_by(PlatformRun.created_at, PlatformRun.id).with_for_update(skip_locked=True).limit(1))


def append_event(session: Session, run: PlatformRun, *, event_type: str, payload: dict, source='platform'):
    # 调用方必须已经锁住 Run，或在本事务刚创建 Run。
    run.event_sequence += 1
    event = PlatformRunEvent(run_id=run.id, sequence=run.event_sequence,
        event_type=event_type, source=source, payload=payload)
    session.add(event)
    session.flush()
    return event


def list_events(session: Session, run_id, *, after_sequence: int, limit: int, through_sequence=None):
    statement = select(PlatformRunEvent).where(
        PlatformRunEvent.run_id == run_id, PlatformRunEvent.sequence > after_sequence)
    if through_sequence is not None:
        statement = statement.where(PlatformRunEvent.sequence <= through_sequence)
    return list(session.scalars(statement.order_by(PlatformRunEvent.sequence).limit(limit)))
