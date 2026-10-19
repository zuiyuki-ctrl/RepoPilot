"""Public ledger projection. Never open private artifacts or expose credentials.

Ledger call IDs are not RunEvent sequences. Fake usage is diagnostic only.
Only dashscope_live ledger entries qualify as provider usage, not billing receipts.
"""
import hashlib
from sqlalchemy import select, text
from ..db.session import SessionLocal
from ..db.models import PlatformRun
from ..db.models.model_gateway import RunModelGrant, ModelCall
from ..schemas.model_gateway import ModelUsage, ModelPolicy


def project_call(call):
    usage = None
    usage_status = 'missing'
    if call.usage is not None:
        try:
            usage = ModelUsage.model_validate(call.usage).model_dump()
            usage_status = 'recorded'
        except ValueError:
            usage_status = 'invalid'
    source = {'mock': 'mock', 'dashscope_fake': 'fake_upstream', 'dashscope_live': 'provider'}.get(call.transport, 'unverified')
    duration = None
    if call.dispatched_at and call.completed_at:
        elapsed = (call.completed_at - call.dispatched_at).total_seconds() * 1000
        if elapsed >= 0:
            duration = int(elapsed)
    # Caller chooses call_id and could put its bearer into it. Publish only its
    # digest plus the platform-generated UUID, never arbitrary caller text.
    return dict(id=str(call.id), call_id_sha256=hashlib.sha256(call.call_id.encode()).hexdigest(), status=call.status,
        evidence_source='platform_gateway_ledger', usage_source=source,
        usage_status=usage_status, usage=usage, real_usage_eligible=source == 'provider',
        request_sha256=call.request_sha256, response_sha256=call.result_sha256,
        error_code=call.error_code, created_at=call.created_at.isoformat(),
        dispatched_at=call.dispatched_at.isoformat() if call.dispatched_at else None,
        completed_at=call.completed_at.isoformat() if call.completed_at else None,
        duration_ms=duration, duration_scope='dispatch_to_settlement')


def project_ledger(run_id, grant, calls):
    items = [project_call(call) for call in calls]
    synthetic = [c for c in items if c['usage_source'] in ('mock', 'fake_upstream') and c['usage']]
    real = [c for c in items if c['real_usage_eligible'] and c['usage'] is not None]
    complete = bool(items) and grant is not None and getattr(grant, 'revoked_at', None) is not None \
        and grant.calls_reserved == len(items) == len(real) \
        and all(c['status'] in ('succeeded', 'failed') and c['dispatched_at'] is not None for c in items)
    policy = None
    if grant is not None:
        try:
            policy = ModelPolicy.model_validate(getattr(grant, 'policy', None)).model_dump(mode='json')
        except ValueError:
            pass  # Missing/invalid historical policy is not reconstructed from today's config.
    return dict(run_id=str(run_id), evidence_source='platform_gateway_ledger',
        grant_present=grant is not None, calls_reserved=grant.calls_reserved if grant else None,
        policy=policy, policy_status='recorded' if policy else 'missing_or_invalid',
        calls_remaining=max(0, policy['max_calls']-grant.calls_reserved) if policy else None,
        revoked=grant.revoked_at is not None if grant and hasattr(grant, 'revoked_at') else None,
        call_count=len(items), items=items,
        synthetic_usage_known_calls=len(synthetic),
        synthetic_known_total_tokens=sum(c['usage']['total_tokens'] for c in synthetic),
        real_usage_known_calls=len(real), real_known_total_tokens=sum(c['usage']['total_tokens'] for c in real),
        real_scope_complete=complete,
        real_total_tokens=sum(c['usage']['total_tokens'] for c in real) if complete else None, cost=None,
        limitations=['Synthetic usage is excluded from real tokens and cost',
            'Missing usage is unknown, not zero',
            'Hashes identify recorded bytes; artifact availability and contents are not checked here',
            'Ledger metadata does not prove complete context/tool coverage or L2'])


def load_ledgers(session, run_ids):
    """Reuse caller's transaction snapshot, two queries for all comparison members."""
    ids = list(run_ids)
    if not ids:
        return {}
    grants = {g.run_id: g for g in session.scalars(select(RunModelGrant).where(RunModelGrant.run_id.in_(ids)))}
    grouped = {run_id: [] for run_id in ids}
    for call in session.scalars(select(ModelCall).where(ModelCall.run_id.in_(ids))
                               .order_by(ModelCall.created_at, ModelCall.id)):
        grouped[call.run_id].append(call)
    return {run_id: project_ledger(run_id, grants.get(run_id), grouped[run_id]) for run_id in ids}


def get_ledger(run_id):
    # A grant is bounded to at most 20 reserved calls, so no separate pagination.
    with SessionLocal() as session:
        session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        if session.get(PlatformRun, run_id) is None:
            return None
        return load_ledgers(session, [run_id])[run_id]
