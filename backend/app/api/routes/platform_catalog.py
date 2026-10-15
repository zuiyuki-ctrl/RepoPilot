"""Local trusted operator catalog; containers only execute in the persistent worker."""
import logging
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from ...db.session import SessionLocal
from ...db.models import Repository
from ...schemas.platform_catalog import AgentRegistration, BenchmarkRegistration, CatalogRead, ValidationRequest, ValidationRead
from ...services import platform_catalog_service as service
from ...services.run_lifecycle import RunConflictError

router = APIRouter(prefix='/api/v2', tags=['v2 catalog'])
logger = logging.getLogger(__name__)


def invoke(operation):
    try:
        return operation()
    except RunConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception('Catalog storage unavailable')
        raise HTTPException(503, 'Catalog storage unavailable; check database migrations') from exc


@router.post('/agents', response_model=CatalogRead)
def register_agent(data: AgentRegistration):
    return invoke(lambda: service.register('agents', data))


@router.post('/benchmarks', response_model=CatalogRead)
def register_benchmark(data: BenchmarkRegistration):
    return invoke(lambda: service.register('benchmarks', data))


@router.get('/catalog-repositories')
def repositories(limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    def read():
        with SessionLocal() as session:
            return [dict(id=row.id, name=row.name, commit_hash=row.commit_hash) for row in session.scalars(
                select(Repository).order_by(Repository.created_at.desc(), Repository.id.desc()).limit(limit).offset(offset))]
    return invoke(read)


@router.get('/catalog-validations/{job_id}', response_model=ValidationRead)
def get_validation(job_id: UUID):
    result = invoke(lambda: service.get_validation(job_id))
    if result is None:
        raise HTTPException(404, 'Validation not found')
    return result


@router.get('/{kind}', response_model=list[CatalogRead])
def list_versions(kind: Literal['agents', 'benchmarks'], limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    return invoke(lambda: service.list_versions(kind, limit, offset))


@router.get('/{kind}/{item_id}', response_model=CatalogRead)
def get_version(kind: Literal['agents', 'benchmarks'], item_id: UUID):
    result = invoke(lambda: service.get_version(kind, item_id))
    if result is None:
        raise HTTPException(404, 'Version not found')
    return result


@router.post('/{kind}/{item_id}/validate', response_model=ValidationRead, status_code=202)
def validate_version(kind: Literal['agents', 'benchmarks'], item_id: UUID, data: ValidationRequest):
    return invoke(lambda: service.queue_validation(kind, item_id, data.request_key))
