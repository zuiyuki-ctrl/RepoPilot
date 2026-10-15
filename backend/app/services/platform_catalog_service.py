"""Immutable registrations and durable, explicitly requested validation jobs."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from ..db.session import SessionLocal
from ..db.models import Repository, RunWork
from ..db.models.platform_catalog import AgentVersion, BenchmarkVersion, CatalogValidation
from .experiment_contract_service import digest
from .run_lifecycle import RunConflictError

MODELS = {'agents': AgentVersion, 'benchmarks': BenchmarkVersion}
LOCK = 714202603


def projection(row):
    return {key: getattr(row, key) for key in ('id', 'name', 'version', 'content_sha256',
            'status', 'descriptor', 'validation', 'created_at')}


def register(kind, request):
    model = MODELS[kind]
    descriptor = request.model_dump(mode='json')
    if kind == 'agents' and request.adapter == 'native':
        from ..agent.adapters.native import NativeAdapter
        descriptor['implementation_sha256'] = NativeAdapter().metadata()['implementation_sha256']
    content_hash = digest(descriptor)
    with SessionLocal.begin() as session:
        if kind == 'benchmarks':
            for item in request.cases:
                if session.get(Repository, item.repository_id) is None:
                    raise LookupError('Registered repository not found')
        session.execute(insert(model).values(id=uuid4(), name=request.name, version=request.version,
            descriptor=descriptor, content_sha256=content_hash, status='registered').on_conflict_do_nothing(
                index_elements=['name', 'version']))
        row = session.scalar(select(model).where(model.name == request.name, model.version == request.version))
        if row.content_sha256 != content_hash:
            raise RunConflictError('Version already exists with different content; create a new version')
        return projection(row)


def list_versions(kind, limit=100, offset=0):
    model = MODELS[kind]
    with SessionLocal() as session:
        return [projection(row) for row in session.scalars(select(model).order_by(
            model.created_at.desc(), model.id.desc()).limit(limit).offset(offset))]


def get_version(kind, item_id):
    with SessionLocal() as session:
        row = session.get(MODELS[kind], item_id)
        return projection(row) if row else None


def validation_projection(job):
    return {key: getattr(job, key) for key in ('id', 'status', 'report', 'created_at', 'completed_at')}


def queue_validation(kind, item_id, request_key):
    with SessionLocal.begin() as session:
        # Serialize cross-owner idempotency keys and duplicate requests; no I/O in this transaction.
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': LOCK})
        owner = session.get(MODELS[kind], item_id, with_for_update=True)
        if owner is None:
            raise LookupError('Version not found')
        field = 'agent_version_id' if kind == 'agents' else 'benchmark_version_id'
        existing = session.scalar(select(CatalogValidation).where(CatalogValidation.request_key == request_key))
        if existing:
            if getattr(existing, field) != item_id:
                raise RunConflictError('Request key belongs to another version')
            return validation_projection(existing)
        if session.scalar(select(CatalogValidation.id).where(getattr(CatalogValidation, field) == item_id,
                CatalogValidation.status.in_(['queued', 'running', 'interrupted'])).limit(1)):
            raise RunConflictError('Validation queued, running or awaiting explicit recovery')
        job = CatalogValidation(request_key=request_key, **{field: item_id})
        session.add(job)
        owner.status = 'validating'
        session.flush()
        return validation_projection(job)


def get_validation(job_id):
    with SessionLocal() as session:
        job = session.get(CatalogValidation, job_id)
        return validation_projection(job) if job else None


def assert_no_catalog_writer(session):
    if session.scalar(select(CatalogValidation.id).where(CatalogValidation.active_token.is_not(None)).limit(1)):
        raise RunConflictError('Unsettled catalog validation; stop writers and explicitly recover it')


def claim_validation():
    with SessionLocal.begin() as session:
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': LOCK})
        assert_no_catalog_writer(session)
        from .platform_experiment_service import assert_no_preparation
        assert_no_preparation(session)
        if session.scalar(select(RunWork.run_id).where(RunWork.active_token.is_not(None)).limit(1)):
            raise RunConflictError('Unsettled Run writer exists')
        job = session.scalar(select(CatalogValidation).where(CatalogValidation.status == 'queued')
            .order_by(CatalogValidation.created_at, CatalogValidation.id).with_for_update(skip_locked=True).limit(1))
        if job is None:
            return None
        kind = 'agents' if job.agent_version_id else 'benchmarks'
        owner = session.get(MODELS[kind], job.agent_version_id or job.benchmark_version_id)
        job.active_token, job.status, job.started_at = uuid4(), 'running', datetime.now(timezone.utc)
        return dict(id=job.id, token=job.active_token, kind=kind, descriptor=owner.descriptor,
                    content_sha256=owner.content_sha256)


def settle_validation(claim, report, *, cleanup_confirmed):
    with SessionLocal.begin() as session:
        job = session.get(CatalogValidation, claim['id'], with_for_update=True)
        if job is None or job.active_token != claim['token'] or job.status != 'running':
            raise RunConflictError('Validation ownership lost')
        owner = session.get(MODELS[claim['kind']], job.agent_version_id or job.benchmark_version_id,
                            with_for_update=True)
        job.report = {**report, 'cleanup_confirmed': cleanup_confirmed, 'content_sha256': claim['content_sha256']}
        job.completed_at = datetime.now(timezone.utc)
        job.status = ('passed' if report['passed'] else 'failed') if cleanup_confirmed else 'interrupted'
        if cleanup_confirmed:
            job.active_token = None
        owner.status = 'ready' if job.status == 'passed' else 'invalid'
        owner.validation = {**job.report, 'job_id': str(job.id), 'status': job.status}


def recover_validation(job_id, token):
    """Called only while holding the worker singleton lock after operator confirms writers stopped."""
    from .platform_container import remove_owned
    with SessionLocal() as session:
        job = session.get(CatalogValidation, job_id)
        if job is None or job.active_token != token:
            raise RunConflictError('Validation token differs')
    remove_owned(job_id, 'agent')
    with SessionLocal.begin() as session:
        job = session.get(CatalogValidation, job_id, with_for_update=True)
        if job is None or job.active_token != token:
            raise RunConflictError('Validation token differs')
        job.status, job.active_token = 'failed', None
        job.completed_at = datetime.now(timezone.utc)
        job.report = {'passed': False, 'reason': 'explicit_recovery_no_replay', 'cleanup_confirmed': True}
        model = AgentVersion if job.agent_version_id else BenchmarkVersion
        owner = session.get(model, job.agent_version_id or job.benchmark_version_id, with_for_update=True)
        owner.status, owner.validation = 'invalid', {**job.report, 'job_id': str(job.id), 'status': 'failed'}
