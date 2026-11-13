"""Trusted local operator authoring API. All execution happens in platform_worker."""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from ...schemas.case_draft import DraftSelection, DraftCreate, DraftEdit, DraftConfirm, DraftRevision
from ...services import case_draft_service as service, case_draft_source as source
from .platform_catalog import invoke as catalog_invoke

router = APIRouter(prefix='/api/v2/case-drafts', tags=['Case drafts'])


def invoke(operation):
    try:
        return catalog_invoke(operation)
    except source.DraftInputError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:
        # Never echo model bodies, arbitrary paths, configuration or credentials.
        raise HTTPException(422, '草稿字段或文件范围不符合 Case 约束') from exc


@router.get('/repositories/{repository_id}')
def files(repository_id: UUID):
    return invoke(lambda: source.browse_repository(repository_id))


@router.post('/preview')
def preview(data: DraftSelection):
    return invoke(lambda: source.preview(data))


@router.get('')
def list_drafts(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    return invoke(lambda: service.list_drafts(limit, offset))


@router.post('', status_code=202)
def create(data: DraftCreate):
    return invoke(lambda: service.create_draft(data))


@router.get('/{draft_id}')
def get(draft_id: UUID):
    return invoke(lambda: service.get_draft(draft_id))


@router.post('/{draft_id}/edit')
def edit(draft_id: UUID, data: DraftEdit):
    return invoke(lambda: service.edit_draft(draft_id, data))


@router.post('/{draft_id}/discard')
def discard(draft_id: UUID, data: DraftRevision):
    return invoke(lambda: service.discard_draft(draft_id, data))


@router.post('/{draft_id}/confirm')
def confirm(draft_id: UUID, data: DraftConfirm):
    return invoke(lambda: service.confirm_draft(draft_id, data))
