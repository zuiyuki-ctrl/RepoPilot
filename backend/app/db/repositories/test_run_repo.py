from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import TestRun

def create_test_run(
    session: Session,
    *,
    task_id: UUID,
    image: str,
    timeout_seconds: int,
) -> TestRun:

    test_run = TestRun(
        task_id=task_id,
        image=image,
        timeout_seconds=timeout_seconds,
        status="running",
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        exit_code=None,
        error=None,
    )


    session.add(test_run)

    session.flush()

    return test_run


def get_test_run(
    session: Session,
    *,
    task_id: UUID,
    test_run_id: UUID,
) -> TestRun | None:

    statement = select(TestRun).where(TestRun.task_id == task_id, TestRun.id == test_run_id)

    return session.execute(statement).scalar_one_or_none()


def list_test_runs(
    session: Session,
    *,
    task_id: UUID,
    limit: int,
    offset: int,
) -> list[TestRun]:
    # 1. select(TestRun)，按 task_id 筛选。
    # 2. started_at 倒序、id 倒序，保持稳定排序。
    # 3. 应用 limit、offset。
    # 4. 返回 list(session.scalars(statement).all())。
    statement = select(TestRun).where(TestRun.task_id == task_id)

    statement = statement.order_by(TestRun.started_at.desc(), TestRun.id.desc()).limit(limit).offset(offset)

    return list(session.scalars(statement).all())


def finish_test_run(
    session: Session,
    test_run: TestRun,
    *,
    exit_code: int | None,
    timed_out: bool,
    stdout: str,
    stderr: str,
    stdout_truncated: bool,
    stderr_truncated: bool,
) -> None:

    test_run.status = "finished"
    test_run.exit_code = exit_code
    test_run.timed_out = timed_out
    test_run.stdout_truncated = stdout_truncated
    test_run.stderr_truncated = stderr_truncated
    test_run.stdout = stdout
    test_run.stderr = stderr

    test_run.completed_at = datetime.now(timezone.utc)
    test_run.error = None
    session.flush()


def fail_test_run(
    session: Session,
    test_run: TestRun,
    *,
    error: str,
) -> None:
    
    test_run.status = "error"
    test_run.error = error
    test_run.completed_at = datetime.now(timezone.utc)

    session.flush()