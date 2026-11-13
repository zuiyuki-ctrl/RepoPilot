"""Persistent authoring jobs. No PlatformRun, AgentTask, or alternate Case library."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select, text
from ..db.session import SessionLocal
from ..db.models import CaseDraft, RunWork
from ..schemas.case_draft import DraftSelection, DraftText
from . import platform_catalog_service as catalog
from . import case_draft_source as source
from .experiment_contract_service import digest
from .run_lifecycle import RunConflictError


def projection(row):
    return {key: getattr(row, key) for key in ('id', 'status', 'revision', 'selection', 'preview',
        'text', 'baseline', 'error', 'observation', 'confirmed_benchmark_id', 'created_at', 'completed_at')}


def get_draft(draft_id):
    with SessionLocal() as session:
        row = session.get(CaseDraft, draft_id)
        if row is None:
            raise LookupError('草稿不存在')
        return projection(row)


def list_drafts(limit=30, offset=0):
    with SessionLocal() as session:
        # Do not multiply up to 1 MB JUnit evidence by every row in the history drawer.
        return [dict(id=r.id, status=r.status, text=r.text) for r in session.scalars(select(CaseDraft).order_by(
            CaseDraft.created_at.desc(), CaseDraft.id.desc()).limit(limit).offset(offset))]


def create_draft(request):
    request_hash = digest(request.model_dump(mode='json', exclude={'request_key'}))
    # Lost HTTP responses can be retried without re-authorizing changed current source/model.
    with SessionLocal() as session:
        row = session.scalar(select(CaseDraft).where(CaseDraft.request_key == request.request_key))
        if row:
            if row.request_sha256 != request_hash:
                raise RunConflictError('请求键已用于其他草稿内容')
            return projection(row)
    checked = source.preview(request.selection)
    if checked['preview_sha256'] != request.preview_sha256:
        raise RunConflictError('文件、模型配置或选择已改变；请重新预览并授权')
    metadata = {k: v for k, v in checked.items() if k != 'contents'}
    metadata['authorization'] = dict(allow_model=request.allow_model, allow_baseline_tests=request.allow_baseline_tests)
    with SessionLocal.begin() as session:
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': catalog.LOCK})
        row = session.scalar(select(CaseDraft).where(CaseDraft.request_key == request.request_key))
        if row:
            if row.request_sha256 != request_hash:
                raise RunConflictError('请求键已用于其他草稿内容')
        else:
            row = CaseDraft(request_key=request.request_key, request_sha256=request_hash,
                            selection=request.selection.model_dump(mode='json'), preview=metadata)
            session.add(row)
            session.flush()
        return projection(row)


def locked_draft(session, draft_id, revision):
    row = session.get(CaseDraft, draft_id, with_for_update=True)
    if row is None:
        raise LookupError('草稿不存在')
    if row.revision != revision:
        raise RunConflictError('草稿已更新；请刷新后再操作')
    return row


def edit_draft(draft_id, request):
    with SessionLocal.begin() as session:
        row = locked_draft(session, draft_id, request.revision)
        if row.status != 'ready' or row.active_token:
            raise RunConflictError('只有基线通过且生成完成的草稿可以编辑')
        DraftSelection.model_validate(row.selection).binding(request.text)
        row.text, row.revision = request.text.model_dump(mode='json'), row.revision + 1
        return projection(row)


def discard_draft(draft_id, request):
    with SessionLocal.begin() as session:
        row = locked_draft(session, draft_id, request.revision)
        if row.active_token or row.status == 'confirmed':
            raise RunConflictError('执行中的任务需等待完成或显式恢复；已确认版本不能作为草稿丢弃')
        row.status, row.revision = 'discarded', row.revision + 1
        return projection(row)


def confirm_draft(draft_id, request):
    # No model/test I/O in this transaction. The existing queued catalog validation checks
    # the current repository; experiments will recheck and execute their own frozen baseline.
    with SessionLocal.begin() as session:
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': catalog.LOCK})
        row = session.get(CaseDraft, draft_id, with_for_update=True)
        if row is None:
            raise LookupError('草稿不存在')
        confirmation = request.model_dump(mode='json')
        if row.status == 'confirmed' and row.confirmation == confirmation:
            return projection(row)
        if row.revision != request.revision or row.status != 'ready' or row.active_token:
            raise RunConflictError('草稿不是当前可确认版本；请刷新')
        if not row.baseline or row.baseline.get('passed') is not True:
            raise RunConflictError('失败基线尚未通过，不能注册')
        registration = request.registration(DraftSelection.model_validate(row.selection),
                                             DraftText.model_validate(row.text))
        saved = catalog.register_in_session(session, 'benchmarks', registration)
        catalog.queue_validation_in_session(session, 'benchmarks', saved['id'], uuid4())
        row.confirmed_benchmark_id = saved['id']
        row.confirmation, row.status, row.revision = confirmation, 'confirmed', row.revision + 1
        return projection(row)


def claim_draft(*, allow_model=False):
    if not allow_model:
        return None
    from .platform_experiment_service import assert_no_preparation
    with SessionLocal.begin() as session:
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': catalog.LOCK})
        catalog.assert_no_catalog_writer(session)
        assert_no_preparation(session)
        if session.scalar(select(RunWork.run_id).where(RunWork.active_token.is_not(None)).limit(1)):
            raise RunConflictError('Unsettled Run writer exists')
        row = session.scalar(select(CaseDraft).where(CaseDraft.status == 'queued').order_by(
            CaseDraft.created_at, CaseDraft.id).with_for_update(skip_locked=True).limit(1))
        if row is None:
            return None
        row.status, row.active_token = 'validating', uuid4()
        row.revision += 1
        return dict(id=row.id, token=row.active_token, selection=row.selection, preview=row.preview)


def progress(claim, **updates):
    with SessionLocal.begin() as session:
        row = session.get(CaseDraft, claim['id'], with_for_update=True)
        if row is None or row.active_token != claim['token'] or row.status not in ('validating', 'generating'):
            raise RunConflictError('Draft ownership lost')
        for key, value in updates.items():
            setattr(row, key, value)
        row.revision += 1


def settle(claim, *, result, baseline, observation, error, cleanup_confirmed):
    progress(claim, text=result, baseline=baseline, observation=observation, error=error,
        status=('ready' if result is not None and error is None else 'failed') if cleanup_confirmed else 'interrupted',
        active_token=None if cleanup_confirmed else claim['token'], completed_at=datetime.now(timezone.utc))


def recover_draft(draft_id, token):
    """Operator holds singleton worker lock and has explicitly stopped all writers."""
    from .platform_container import remove_owned
    with SessionLocal() as session:
        row = session.get(CaseDraft, draft_id)
        if row is None or row.active_token != token:
            raise RunConflictError('Draft recovery token differs')
    remove_owned(draft_id, 'baseline')
    with SessionLocal.begin() as session:
        row = session.get(CaseDraft, draft_id, with_for_update=True)
        if row is None or row.active_token != token:
            raise RunConflictError('Draft recovery token differs')
        row.status, row.active_token, row.revision = 'failed', None, row.revision + 1
        row.error = dict(reason='explicit_recovery_no_replay', message='已恢复所有权；不会自动重放模型请求')
        row.completed_at = datetime.now(timezone.utc)
