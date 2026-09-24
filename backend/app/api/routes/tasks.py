from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from ...schemas.task_event import TaskEventRead
from ...core.exceptions import InvalidTaskInputError, TaskStateConflictError, InvalidAnswerCitationError, \
    TaskExecutionError, InvalidPlanError, InsufficientPlanEvidenceError
from ...services import task_service
from ...schemas.task import TaskRead, TaskCreate, TaskPlanReviewRequest

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead, status_code=201)
def create_task(data: TaskCreate):
    # 1. 调用 task_service.create_task。
    try:
        result = task_service.create_task(data)

    # 2. InvalidTaskInputError → 422，固定提示。
    except InvalidTaskInputError as exc:
        raise HTTPException(status_code=422, detail="Task request cannot be blank") from exc

    # 3. SQLAlchemyError → 503，记录日志，固定提示。
    except SQLAlchemyError as exc:
        logger.exception(
            "Database unavailable; repository_id=%s",
            data.repository_id
        )
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    # 4. 结果为 None → 404，Repository not found。
    if result is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    # 5. 返回结果。
    return result


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: UUID):
    # 1. 调用 task_service.get_task。
    try:
        result = task_service.get_task(task_id)

    # 2. SQLAlchemyError → 503。
    except SQLAlchemyError as exc:
        logger.exception(
            "Task query failed; task_id=%s",
            task_id,
        )
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    # 3. 结果为 None → 404，Task not found。
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # 4. 返回结果。
    return result

@router.post("/{task_id}/run", response_model=TaskRead)
def run_task(task_id: UUID):
    try:
        # 1. 调用 task_service.run_task。
        result = task_service.run_task(task_id)

    # 2. 捕获具体异常。
    except TaskStateConflictError as exc:
        # 409 Conflict: 任务状态冲突（预期内的业务状态异常，记录 warning）
        logger.warning(
            "Task state conflict; task_id=%s: %s",
            task_id,
            exc,
        )
        raise HTTPException(status_code=409, detail="Task cannot be run in its current state") from exc

    except httpx.HTTPError as exc:
        # 503 Service Unavailable: 大模型/外部 HTTP 服务不可用
        logger.exception(
            "Model service unavailable; task_id=%s",
            task_id,
        )
        raise HTTPException(
            status_code=503, detail="Model service unavailable"
        ) from exc

    except SQLAlchemyError as exc:
        # 503 Service Unavailable: 数据库连接/执行异常
        logger.exception(
            "Database service unavailable; task_id=%s",
            task_id,
        )
        raise HTTPException(
            status_code=503, detail="Database service unavailable"
        ) from exc

    except InvalidAnswerCitationError as exc:
        # 502 Bad Gateway: 模型生成的引用格式非法，上游网关/模型返回结果无效
        logger.exception(
            "Generated answer contains invalid citations; task_id=%s",
            task_id,
        )
        raise HTTPException(
            status_code=502, detail="Generated answer contains invalid citations"
        ) from exc

    except InvalidPlanError as exc:
        raise HTTPException(status_code=502, detail="Model returned an invalid plan") from exc

    except InsufficientPlanEvidenceError as exc:
        raise HTTPException(status_code=409, detail="No code evidence available for planning") from exc

    except (TaskExecutionError, ValueError) as exc:
        # 500 Internal Server Error: 内部执行逻辑崩溃或意料之外的内部参数错误
        logger.exception(
            "Task execution or internal processing error; task_id=%s",
            task_id,
        )
        raise HTTPException(
            status_code=500, detail="Internal server error"
        ) from exc


    # 3. 结果为 None，返回 404：Task not found。
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # 4. 正常返回 TaskRead，HTTP 200。
    return result


@router.get(
    "/{task_id}/events",
    response_model=list[TaskEventRead],
)
def list_task_events(
    task_id: UUID,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    # 1. 调用 task_service.list_task_events。
    try:
        task_events = task_service.list_task_events(
            task_id,
            after_sequence=after_sequence,
            limit=limit
        )

    # 2. SQLAlchemyError → 503，记录 task_id，使用固定提示。
    except SQLAlchemyError as exc:
        logger.exception("Database unavailable; task_id=%s", task_id)
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    except InvalidTaskInputError as exc:
        raise HTTPException(status_code=422, detail="Invalid event pagination parameters") from exc

    # 3. result is None → 404。
    if task_events is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # 4. 返回结果，包括空列表。
    return task_events


@router.post("/{task_id}/review", response_model=TaskRead)
def review_task_plan(
    task_id: UUID,
    data: TaskPlanReviewRequest,
):
    # 1. 调用 task_service.review_task_plan。
    try:
        result = task_service.review_task_plan(task_id, data)

    # 2. TaskStateConflictError → 409。
    except TaskStateConflictError as exc:
        logger.exception(
            "Task state conflict; task_id=%s",
            task_id
        )
        raise HTTPException(status_code=409, detail="Task cannot be review in its current state") from exc

    # 3. SQLAlchemyError → 503。
    except SQLAlchemyError as exc:
        logger.exception(
            "Database unavailable; task_id=%s",
            task_id
        )
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    # 4. TaskExecutionError 或内部结果 ValidationError → 500。
    except (TaskExecutionError, ValidationError) as exc:
        logger.exception("Stored plan review failed; task_id=%s", task_id)
        raise HTTPException(status_code=500, detail="Task execution error") from exc

    # 5. 返回 None → 404。
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # 6. 成功返回 TaskRead。
    return result