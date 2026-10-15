from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from ...schemas.platform_experiment import ExperimentDraft, ExperimentStart
from ...services import platform_experiment_service as service
from .platform_catalog import invoke

router=APIRouter(prefix='/api/v2/experiments',tags=['v2 experiments'])


@router.post('/preview')
def preview(data:ExperimentDraft):
    return invoke(lambda:service.preview(data))


@router.post('',status_code=202)
def start(data:ExperimentStart):
    return invoke(lambda:service.start(data))


@router.get('')
def list_experiments(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    return invoke(lambda:service.list_experiments(limit,offset))


@router.get('/{experiment_id}')
def read(experiment_id:UUID):
    result=invoke(lambda:service.read(experiment_id))
    if result is None: raise HTTPException(404,'Experiment not found')
    return result


@router.post('/{experiment_id}/cancel')
def cancel(experiment_id:UUID):
    return invoke(lambda:service.cancel(experiment_id))
