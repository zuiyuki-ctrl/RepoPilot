from uuid import UUID
from typing import Literal
import json
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from ...schemas.platform_experiment import ExperimentDraft, ExperimentStart
from ...schemas.platform_decision import ExperimentReviewRequest
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


@router.get('/{experiment_id}/comparison')
def comparison(experiment_id:UUID):
    from ...services.platform_comparison_service import get_comparison
    result=invoke(lambda:get_comparison(experiment_id))
    if result is None: raise HTTPException(404,'Experiment not found')
    return result


@router.post('/{experiment_id}/reviews', status_code=201)
def review(experiment_id:UUID, data:ExperimentReviewRequest):
    from ...services.platform_review_service import save_review
    return invoke(lambda:save_review(experiment_id, data))


@router.get('/{experiment_id}/reviews')
def reviews(experiment_id:UUID, limit:int=Query(20,ge=1,le=100), offset:int=Query(0,ge=0)):
    from ...services.platform_review_service import list_reviews
    result=invoke(lambda:list_reviews(experiment_id, limit=limit, offset=offset))
    if result is None: raise HTTPException(404,'Experiment not found')
    return result


@router.get('/{experiment_id}/export')
def export(experiment_id:UUID, format:Literal['json','markdown']='json'):
    from ...services.platform_export_service import export_report, render_markdown
    report=invoke(lambda:export_report(experiment_id))
    if report is None: raise HTTPException(404,'Experiment not found')
    content=json.dumps(report,ensure_ascii=False,indent=2) if format=='json' else render_markdown(report)
    extension='json' if format=='json' else 'md'
    filename=f'experiment-{experiment_id}-{report["report_sha256"][:12]}.{extension}'
    return Response(content,media_type='application/json' if format=='json' else 'text/markdown',
        headers={'Content-Disposition':f'attachment; filename="{filename}"','Cache-Control':'no-store'})
