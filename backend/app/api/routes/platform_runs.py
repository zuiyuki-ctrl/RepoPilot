import logging
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from ...schemas.platform_run import RunRead, RunPage, RunEventPage
from ...services import platform_run_service as service
from ...services import run_control_service as control
from ...services.run_lifecycle import RunConflictError
from ...schemas.run_control import ApprovalRequest, CancelRequest, CheckpointRead, ControlRead

router = APIRouter(prefix='/api/v2/runs', tags=['v2 runs'])
logger = logging.getLogger(__name__)


def read_database(operation):
    try:
        return operation()
    except SQLAlchemyError as exc:
        logger.exception('v2 Run database query failed')
        raise HTTPException(503, 'Run storage unavailable; check database and migrations') from exc
    except RunConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('', response_model=RunPage)
def list_runs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return RunPage(items=read_database(lambda: service.list_runs(limit=limit, offset=offset)))


@router.get('/{run_id}', response_model=RunRead)
def get_run(run_id: UUID):
    result = read_database(lambda: service.get_run(run_id))
    if result is None:
        raise HTTPException(404, 'Run not found')
    return result


@router.get('/{run_id}/events', response_model=RunEventPage)
def list_events(run_id: UUID, after_sequence: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    result = read_database(lambda: service.list_events(run_id, after_sequence=after_sequence, limit=limit))
    if result is None:
        raise HTTPException(404, 'Run not found')
    return RunEventPage(items=result, next_after_sequence=result[-1].sequence if result else after_sequence)


@router.get('/{run_id}/control', response_model=ControlRead | None)
def get_control(run_id: UUID):
    # 没有 worker 绑定的历史 Run 显示无控制面，不伪造可执行按钮。
    return read_database(lambda: control.get_control(run_id))


@router.get('/{run_id}/report')
def get_report(run_id: UUID):
    from ...services.platform_report_service import get_report as read_report
    result = read_database(lambda: read_report(run_id))
    if result is None:
        raise HTTPException(404, 'Run not found')
    return result


@router.post('/{run_id}/checkpoints/{checkpoint_id}/decision', response_model=CheckpointRead)
def decide(run_id: UUID, checkpoint_id: UUID, data: ApprovalRequest):
    result = read_database(lambda: control.decide_checkpoint(run_id, checkpoint_id, data))
    if result is None:
        raise HTTPException(404, 'Run checkpoint not found')
    return result


@router.post('/{run_id}/cancel')
def cancel(run_id: UUID, data: CancelRequest):
    result = read_database(lambda: control.request_cancel(run_id, data))
    if result is None:
        raise HTTPException(404, 'Run control not found')
    return result
