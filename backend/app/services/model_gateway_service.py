"""Transactional model ledger: no sockets or provider keys.

Internal callers are trusted. Module B must authenticate a short-lived credential
before supplying run_id/worker_token here. Neither value is a bearer credential.
Transactions own the Run row lock; never hold it across upstream I/O.
"""
import hashlib
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from ..db.session import SessionLocal
from ..db.models import RunWork, RunModelGrant, ModelCall
from ..db.repositories import platform_run_repo as repo
from ..schemas.model_gateway import ModelPolicy, ModelCallRequest, ModelUsage, forwarded_body, body_bytes
from ..schemas.platform_run import AgentRunRequest, Hash
from pydantic import TypeAdapter, ValidationError
from .experiment_contract_service import digest
from .run_lifecycle import RunConflictError

INFLIGHT = ('reserved', 'dispatched')
ERROR_CODES = {'upstream_rejected', 'upstream_timeout', 'upstream_disconnected',
               'invalid_upstream_response', 'invalid_upstream_usage', 'attempt_ended'}


def authorize_process(session, run, config, *, allow_model):
    """Called in enqueue's Run-locked transaction. Never upgrades an old offline Run."""
    if config.model_policy is None:
        return
    if allow_model is not True:
        raise RunConflictError('Process model calls require explicit --allow-model authorization')
    if digest(config.model_dump(mode='json')) != run.request['config_sha256']:
        raise RunConflictError('Model configuration differs from frozen Run')
    policy = config.model_policy.model_dump(mode='json')
    grant = session.get(RunModelGrant, run.id)
    if grant:
        if grant.config_sha256 != run.request['config_sha256'] or grant.policy != policy:
            raise RunConflictError('Model authorization is immutable')
        return
    session.add(RunModelGrant(run_id=run.id, config_sha256=run.request['config_sha256'],
        policy=policy, calls_reserved=0, known_total_tokens=0))


def bind_attempt(session, run, work, *, allow_model):
    """Worker-only second authorization, after it acquired the execution fence."""
    grant = session.get(RunModelGrant, run.id)
    if not grant or allow_model is not True or work.stage != 'process_run':
        raise RunConflictError('Model worker authorization required')
    if (grant.revoked_at or grant.worker_token is not None or work.cancel_requested
            or run.lifecycle != 'running' or work.active_token is None
            or grant.config_sha256 != run.request['config_sha256']):
        raise RunConflictError('Model attempt cannot be rebound or resumed')
    request = AgentRunRequest.model_validate(run.request)
    remaining = request.budget.timeout_seconds - work.active_seconds
    if remaining <= 0:
        raise RunConflictError('Model execution deadline exhausted')
    grant.worker_token = work.active_token
    grant.expires_at = datetime.now(timezone.utc) + timedelta(seconds=remaining)


def revoke_attempt(session, run, *, now=None):
    """Caller holds Run lock. Quota is never refunded, including crash uncertainty."""
    grant = session.get(RunModelGrant, run.id)
    if grant is None:
        return
    now = now or datetime.now(timezone.utc)
    grant.revoked_at = grant.revoked_at or now
    grant.credential_sha256 = None
    for call in session.scalars(select(ModelCall).where(ModelCall.run_id == run.id,
                                                        ModelCall.status.in_(INFLIGHT))):
        call.status, call.error_code, call.completed_at = 'unknown', 'attempt_ended', now
        grant.stop_reason = 'unknown_result'


def _locked(session, run_id):
    run = repo.get_run(session, run_id, for_update=True)
    grant = session.get(RunModelGrant, run_id)
    work = session.get(RunWork, run_id)
    if run is None or grant is None or work is None:
        raise RunConflictError('Model authorization missing')
    return run, grant, work


def _active(run, grant, work, worker_token, now):
    if (grant.worker_token is None or grant.worker_token != worker_token
            or work.active_token != worker_token or grant.revoked_at
            or grant.expires_at is None or now >= grant.expires_at
            or work.cancel_requested or work.stage != 'process_run'
            or run.lifecycle != 'running'
            or grant.config_sha256 != run.request['config_sha256']):
        raise RunConflictError('Model authorization inactive')


def _read(call, *, created=False):
    # Never expose worker token or content through this metadata result.
    return dict(id=call.id, call_id=call.call_id, status=call.status, created=created,
                request_sha256=call.request_sha256, deadline=call.deadline,
                usage=call.usage, result_sha256=call.result_sha256, error_code=call.error_code,
                transport=call.transport)


def reserve_call(run_id, worker_token, data):
    call_request = ModelCallRequest.model_validate(data)
    with SessionLocal.begin() as session:
        run, grant, work = _locked(session, run_id)
        now = datetime.now(timezone.utc)
        _active(run, grant, work, worker_token, now)
        policy = ModelPolicy.model_validate(grant.policy)
        body = forwarded_body(policy, call_request)
        request_hash = hashlib.sha256(body_bytes(body)).hexdigest()
        old = session.scalar(select(ModelCall).where(ModelCall.run_id == run_id,
                                                     ModelCall.call_id == call_request.call_id))
        if old:
            if old.request_sha256 != request_hash:
                raise RunConflictError('Model call_id already used with different content')
            # Even unknown/failed calls are returned, NEVER automatically resent.
            return _read(old)
        if (grant.stop_reason or grant.calls_reserved >= policy.max_calls
                or (policy.max_total_tokens is not None and grant.known_total_tokens >= policy.max_total_tokens)):
            raise RunConflictError('Model budget exhausted or usage unknown')
        if session.scalar(select(ModelCall.id).where(ModelCall.run_id == run_id,
                                                     ModelCall.status.in_(INFLIGHT))):
            raise RunConflictError('Only one model request may be in flight per Run')
        call = ModelCall(run_id=run_id, call_id=call_request.call_id, worker_token=worker_token,
            request_sha256=request_hash, status='reserved', transport=grant.gateway_mode,
            deadline=min(grant.expires_at, now + timedelta(seconds=policy.request_timeout_seconds)))
        grant.calls_reserved += 1
        session.add(call)
        session.flush()
        return _read(call, created=True)


def mark_dispatched(run_id, worker_token, call_id):
    """Commit before sending once. A crash in the commit/send gap is conservative unknown."""
    with SessionLocal.begin() as session:
        run, grant, work = _locked(session, run_id)
        now = datetime.now(timezone.utc)
        _active(run, grant, work, worker_token, now)
        call = session.scalar(select(ModelCall).where(ModelCall.run_id == run_id, ModelCall.call_id == call_id))
        if (call is None or call.worker_token != worker_token or call.status != 'reserved'
                or now >= call.deadline):
            raise RunConflictError('Model call is not dispatchable; never replay it')
        call.status, call.dispatched_at = 'dispatched', now
        return _read(call)


def finish_call(run_id, worker_token, call_id, *, status, usage=None, result_sha256=None, error_code=None):
    """Trusted upstream completion. Late evidence may update ledger, NEVER Run lifecycle.

    A missing/invalid usage or unknown result stops all further calls. The request
    quota was already spent at reserve time; settlement never releases it.
    """
    if status not in ('succeeded', 'failed', 'unknown') or error_code not in ERROR_CODES | {None}:
        raise ValueError('Unsupported model result metadata')
    if result_sha256 is not None:
        TypeAdapter(Hash).validate_python(result_sha256)
    if status == 'succeeded' and result_sha256 is None:
        raise ValueError('Successful call requires immutable result artifact hash')
    try:
        parsed_usage = ModelUsage.model_validate(usage).model_dump() if usage is not None else None
    except ValidationError:
        parsed_usage, error_code = None, 'invalid_upstream_usage'
    with SessionLocal.begin() as session:
        run, grant, work = _locked(session, run_id)
        call = session.scalar(select(ModelCall).where(ModelCall.run_id == run_id, ModelCall.call_id == call_id))
        if call is None or call.worker_token != worker_token:
            raise RunConflictError('Model result ownership differs')
        if call.status in ('succeeded', 'failed'):
            if (call.status, call.usage, call.result_sha256, call.error_code) != (status, parsed_usage, result_sha256, error_code):
                raise RunConflictError('Model result already settled differently')
            return _read(call)
        if call.dispatched_at is None and status != 'unknown':
            raise RunConflictError('Cannot record upstream completion before dispatch')
        # Repeated unknown completions must not double-count known usage either.
        previous = call.usage['total_tokens'] if call.usage else 0
        if call.usage and call.usage != parsed_usage:
            raise RunConflictError('Recorded model usage is immutable')
        grant.known_total_tokens += (parsed_usage['total_tokens'] if parsed_usage else 0) - previous
        call.status, call.usage = status, parsed_usage
        call.result_sha256, call.error_code = result_sha256, error_code
        call.completed_at = datetime.now(timezone.utc)
        if status == 'unknown' or parsed_usage is None:
            grant.stop_reason = 'unknown_result' if status == 'unknown' else 'usage_missing'
        return _read(call)
