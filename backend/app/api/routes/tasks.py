from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from ...core.exceptions import InvalidTaskInputError, TaskStateConflictError, InvalidAnswerCitationError, \
    TaskExecutionError
from ...services import task_service
from ...schemas.task import TaskRead, TaskCreate

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