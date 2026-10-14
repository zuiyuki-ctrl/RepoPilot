"""v2 接管的任务只允许通过 Run 检查点修改，旧 HTTP 写入口保持只读。"""
from uuid import UUID
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from ..db.session import SessionLocal
from ..db.models import PlatformRun


def guard_native_task(request: Request):
    task_id = request.path_params.get('task_id')
    if request.method in ('GET', 'HEAD', 'OPTIONS') or task_id is None:
        return
    try:
        parsed = UUID(str(task_id))
    except ValueError:
        return  # 交给 FastAPI 路径参数校验返回 422。
    try:
        with SessionLocal() as session:
            bound = session.scalar(select(PlatformRun.id).where(PlatformRun.legacy_task_id == parsed))
    except SQLAlchemyError as exc:
        raise HTTPException(503, 'Run ownership storage unavailable') from exc
    if bound is not None:
        raise HTTPException(409, 'Task is managed by a v2 Run; use its approval and cancellation endpoints')
