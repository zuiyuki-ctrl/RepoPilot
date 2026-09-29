from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from ...services import (
    edit_proposal_service,
    plan_execution_service,
    task_service,
    task_test_service
)
from ...schemas.edit import TaskFileEditRead, TaskFileEditRequest, TaskFileEditApplyRequest
from ...schemas.workspace import TaskWorkspaceDiffRead, TaskWorkspaceWriteRead, TaskWorkspaceWriteRequest
from ...schemas.task_event import TaskEventRead
from ...core.exceptions import InvalidTaskInputError, TaskStateConflictError, InvalidAnswerCitationError, \
    TaskExecutionError, InvalidPlanError, InsufficientPlanEvidenceError, WorkspaceDiffError, InvalidWorkspacePathError, \
    RepositoryBusyError, PlanScopeViolationError, WorkspaceWriteError, WorkspaceWritePersistenceError, \
    RepositoryScanError, InvalidEditProposalError, WorkspaceFileConflictError, SandboxPreparationError, \
    SandboxExecutionError
from ...schemas.task import TaskRead, TaskCreate, TaskPlanReviewRequest
from ...schemas.testing import TaskTestRead

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead, status_code=201)
# 接收任务创建请求并返回登记结果，将输入和数据库异常转换为 HTTP 响应；不启动执行。
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
# 提供任务详情查询入口，返回状态、结果及审核信息，任务不存在时返回 404。
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
# 同步执行已创建的任务并返回结果，将状态冲突和模型、数据库故障映射为 HTTP 响应。
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
# 提供按事件序号分页查询的 HTTP 入口，供客户端轮询任务执行进度。
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
# 接收用户对待审核计划的批准或拒绝决定，调用服务保存审核与事件；不执行计划。
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


# 查看工作副本差异
@router.get(
    "/{task_id}/diff",
    response_model=TaskWorkspaceDiffRead,
)
# 提供计划任务关联工作副本的差异预览，返回整个副本相对于 HEAD 的变化，不只限于该任务。
def get_task_workspace_diff(task_id: UUID):
    # 1. 调用 plan_execution_service.get_task_workspace_diff。
    try:
        diff = plan_execution_service.get_task_workspace_diff(task_id)

    # 2. 转换异常。
    except TaskStateConflictError as exc:
        logger.exception("Only plan tasks support workspace; task_id=%s", task_id)
        raise HTTPException(status_code=409, detail="Only plan tasks support workspace diff",) from exc

    except SQLAlchemyError as exc:
        logger.exception("Database unavailable; task_id=%s", task_id)
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    except WorkspaceDiffError as exc:
        logger.exception("Workspace diff unavailable; task_id=%s", task_id)
        raise HTTPException(status_code=503, detail="Workspace diff unavailable") from exc

    except InvalidWorkspacePathError as exc:
        logger.exception("Stored workspace path is invalid; task_id=%s", task_id)
        raise HTTPException(status_code=500, detail="Stored workspace path is invalid") from exc

    except TaskExecutionError as exc:
        logger.exception("Task workspace is unavailable; task_id=%s", task_id)
        raise HTTPException(status_code=500, detail="Task workspace is unavailable") from exc

    # 3. 结果为 None，返回 404。
    if diff is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # 4. 返回响应对象。
    return diff


# 手动写入入口，现在也要求 executing
@router.post(
    "/{task_id}/files",
    response_model=TaskWorkspaceWriteRead,
)
# 提供已批准计划的单文件写入入口，校验请求并转换执行异常，返回写入摘要。
# 持久化未确认时明确报告文件已写入，避免调用方误以为修改已回滚。
def write_task_workspace_file(
    task_id: UUID,
    data: TaskWorkspaceWriteRequest,
):
    # 1. 调用受审批约束的服务。
    try:
        result = plan_execution_service.write_approved_plan_file(
            task_id,
            file_path=data.file_path,
            content=data.content
        )
    except TaskStateConflictError as e:
        raise HTTPException(
            status_code=409,
            detail=(
                "任务必须是已批准且处于 executing 状态的计划任务；"
                "批准后请先调用 POST /api/v1/tasks/{task_id}/execute"
            ),
        ) from e

    except RepositoryBusyError as e:
        raise HTTPException(
            status_code=409,
            detail="Repository is busy",
        ) from e

    except PlanScopeViolationError as e:
        raise HTTPException(
            status_code=403,
            detail="File is not included in the approved plan",
        ) from e

    except InvalidWorkspacePathError as e:
        raise HTTPException(
            status_code=422,
            detail="Workspace target path is invalid",
        ) from e

    except WorkspaceWriteError as e:
        logger.exception(
            "Workspace file write failed; task_id=%s; file_path=%s",
            task_id,
            data.file_path,
        )

        raise HTTPException(
            status_code=500,
            detail="Workspace file write failed",
        ) from e

    except SQLAlchemyError as e:
        logger.exception(
            "Database unavailable during workspace write; task_id=%s; file_path=%s",
            task_id,
            data.file_path,
        )
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from e

    except TaskExecutionError as e:
        logger.exception(
            "Task execution data is invalid; task_id=%s; file_path=%s",
            task_id,
            data.file_path,
        )
        raise HTTPException(
            status_code=500,
            detail="Task execution data is invalid",
        ) from e

    except WorkspaceWritePersistenceError as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "workspace_write_persistence_failed",
                "message": (
                    "The file was written, but persistence was not confirmed. "
                    "Inspect workspace diff and task events before retrying."
                ),
                "file_written": True,
            },
        ) from e

        # 3. 返回 None 时，抛出 404 HTTPException
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )


    # 4. 构造 TaskWorkspaceWriteRead 并返回。
    return TaskWorkspaceWriteRead(
        task_id=task_id,
        file_path=result.file_path,
        created=result.created,
        bytes_written=result.bytes_written,
    )


# 读取当前源码，生成候选，返回原文件 hash
@router.post(
    "/{task_id}/edit-proposal",
    response_model=TaskFileEditRead,
)
def generate_task_file_edit(
    task_id: UUID,
    data: TaskFileEditRequest,
):
    try:
        result = edit_proposal_service.generate_task_file_edit(task_id, file_path=data.file_path)
    except TaskStateConflictError as e:
        raise HTTPException(
            status_code=409,
            detail=(
                "任务必须是已批准且处于 executing 状态的计划任务；"
                "批准后请先调用 POST /api/v1/tasks/{task_id}/execute"
            ),
        ) from e

    except PlanScopeViolationError as e:
        raise HTTPException(
            status_code=403,
            detail="文件不在批准范围",
        ) from e

    except InvalidTaskInputError as e:
        raise HTTPException(
            status_code=422,
            detail="文件类型、大小或编码不符合本功能要求",
        ) from e

    except InvalidWorkspacePathError as e:
        raise HTTPException(
            status_code=422,
            detail="工作副本目标路径无法通过检查",
        ) from e

    except RepositoryScanError as e:
        logger.exception("Repository scan failed; task_id=%s; file_path=%s", task_id, data.file_path)
        raise HTTPException(
            status_code=503,
            detail="当前无法读取工作副本源码",
        ) from e

    except InvalidEditProposalError as e:
        logger.exception("Edit proposal failed; task_id=%s; file_path=%s", task_id, data.file_path)
        raise HTTPException(
            status_code=502,
            detail="模型生成的候选不合法",
        ) from e

    except httpx.HTTPError as e:
        logger.exception("模型服务请求失败; task_id=%s; file_path=%s", task_id, data.file_path)
        raise HTTPException(
            status_code=503,
            detail="模型服务请求失败",
        ) from e

    except SQLAlchemyError as e:
        logger.exception(
            "Database unavailable during workspace write; task_id=%s; file_path=%s",
            task_id,
            data.file_path
        )
        raise HTTPException(
            status_code=503,
            detail="数据库不可用",
        ) from e

    except TaskExecutionError as e:
        logger.exception(
            "Edit proposal generation failed; task_id=%s; file_path=%s",
            task_id,
            data.file_path,
        )

        raise HTTPException(
            status_code=500,
            detail="存储的任务或计划数据异常",
        ) from e

    except ValueError as e:
        logger.exception(
            "Edit proposal generation failed; task_id=%s; file_path=%s",
            task_id,
            data.file_path,
        )
        raise HTTPException(
            status_code=500,
            detail="内部生成流程异常",
        ) from e

        # 3. result 为 None 时返回 404
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    return result


# 复验候选，持锁比较 hash，然后写文件、记录事件
@router.post(
    "/{task_id}/edit-proposal/apply",
    response_model=TaskWorkspaceWriteRead,
)
def apply_task_file_edit(
    task_id: UUID,
    data: TaskFileEditApplyRequest,
):
    try:
        result = plan_execution_service.apply_task_file_edit(
            task_id,
            base_file_hash=data.base_file_hash,
            proposal=data.proposal,
        )

    # 下面依次处理业务异常。
    except TaskStateConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "任务必须是已批准且处于 executing 状态的计划任务；"
                "批准后请先调用 POST /api/v1/tasks/{task_id}/execute"
            ),
        ) from exc

    except WorkspaceFileConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="Workspace file changed after proposal generation",
        ) from exc

    except PlanScopeViolationError as exc:
        raise HTTPException(
            status_code=403,
            detail="File is not included in the approved plan",
        ) from exc

    except (InvalidTaskInputError, InvalidEditProposalError) as exc:
        raise HTTPException(
            status_code=422,
            detail="Edit proposal is invalid",
        ) from exc

    except InvalidWorkspacePathError as exc:
        raise HTTPException(
            status_code=422,
            detail="Workspace target path is invalid",
        ) from exc

    except RepositoryBusyError as exc:
        raise HTTPException(
            status_code=409,
            detail="Repository is busy",
        ) from exc

    except RepositoryScanError as exc:
        logger.exception(
            "Workspace source read failed; task_id=%s; file_path=%s",
            task_id,
            data.proposal.file_path,
        )
        raise HTTPException(
            status_code=503,
            detail="Workspace source is unavailable",
        ) from exc

    except WorkspaceWritePersistenceError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "workspace_write_persistence_failed",
                "message": (
                    "The file was written, but persistence was not confirmed. "
                    "Inspect workspace diff and task events before retrying."
                ),
                "file_written": True,
            },
        ) from exc

    except WorkspaceWriteError as exc:
        logger.exception(
            "Workspace edit application failed; task_id=%s; file_path=%s",
            task_id,
            data.proposal.file_path,
        )
        raise HTTPException(
            status_code=500,
            detail="Workspace file write failed",
        ) from exc

    except SQLAlchemyError as exc:
        logger.exception(
            "Database unavailable while applying edit; task_id=%s",
            task_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc

    except TaskExecutionError as exc:
        logger.exception(
            "Stored task data is invalid; task_id=%s",
            task_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Stored task data is invalid",
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    return TaskWorkspaceWriteRead(
        task_id=task_id,
        file_path=result.file_path,
        created=result.created,
        bytes_written=result.bytes_written,
    )


# 将已批准计划切换为 executing，记录 TASK_EXECUTION_STARTED
@router.post(
    "/{task_id}/execute",
    response_model=TaskRead,
)
def begin_plan_execution(task_id: UUID):
    try:
        result = task_service.begin_plan_execution(task_id)

    except TaskStateConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="Task is not ready for execution",
        ) from exc

    except SQLAlchemyError as exc:
        logger.exception(
            "Database unavailable while starting execution; task_id=%s",
            task_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc

    except TaskExecutionError as exc:
        logger.exception(
            "Stored plan is invalid; task_id=%s",
            task_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Stored plan is invalid",
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    return result


# 对已批准的计划任务运行 Docker pytest。
@router.post(
    "/{task_id}/tests",
    response_model=TaskTestRead,
)
def run_task_tests(task_id: UUID):
    """
    对已批准且处于 executing 状态的计划任务运行 Docker pytest。
    """

    try:
        # 调用 task_test_service.run_task_pytest
        result = task_test_service.run_task_pytest(task_id)

    except TaskStateConflictError as exc:
        # 包括任务尚未执行、正在测试或状态已被其他流程改变。
        raise HTTPException(
            status_code=409,
            detail="Task is not ready for sandbox testing",
        ) from exc

    except SandboxPreparationError as exc:
        logger.exception(
            "Sandbox snapshot preparation failed; task_id=%s",
            task_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Sandbox snapshot preparation failed",
        ) from exc

    except SandboxExecutionError as exc:
        logger.exception(
            "Sandbox execution failed; task_id=%s",
            task_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Sandbox execution failed",
        ) from exc

    except SQLAlchemyError as exc:
        logger.exception(
            "Database unavailable during sandbox testing; task_id=%s",
            task_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc

    except TaskExecutionError as exc:
        logger.exception(
            "Task workspace unavailable during sandbox testing; "
            "task_id=%s",
            task_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Task workspace is unavailable",
        ) from exc

    # 服务返回 None 表示任务不存在。
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    # 只有未超时且 exit_code == 0 才算通过。
    passed = not result.timed_out and result.exit_code == 0

    # 将结果转换为 API 响应。
    return TaskTestRead(
        task_id=task_id,
        passed=passed,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        timed_out=result.timed_out,
        stdout_truncated=result.stdout_truncated,
        stderr_truncated=result.stderr_truncated,
    )
