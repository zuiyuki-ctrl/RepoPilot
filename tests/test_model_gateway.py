"""Module A offline contracts. No real database, Docker or model calls."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from io import StringIO
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
from uuid import uuid4
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable, CreateIndex
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.app.db.models import RunModelGrant, ModelCall, RunWork
from backend.app.schemas.model_gateway import ModelPolicy, ModelCallRequest, forwarded_body, body_bytes
from backend.app.schemas.process_agent import ProcessConfiguration
from backend.app.schemas.platform_catalog import AgentRegistration
from backend.app.services import model_gateway_service as gateway
from backend.app.services import run_control_service as control, run_worker_service as worker
from backend.app.services import platform_experiment_service as experiments
from backend.app.services.experiment_contract_service import digest
from backend.app.services.run_lifecycle import RunConflictError
from tests.test_platform_day3 import request as offline_request, CONFIG
from tests.test_platform_day5 import records, draft


def online_config(**policy):
    return ProcessConfiguration(**CONFIG.model_dump(), model_policy=ModelPolicy(model='qwen-plus', **policy))


def payload(call_id='first', text='fix this function'):
    return dict(call_id=call_id, messages=[dict(role='user', content=text)])


def test_old_configuration_and_nested_registration_hash_unchanged():
    old = dict(protocol_version=1, image=CONFIG.image, argv=CONFIG.argv, trace=False)
    for raw in (old, {**old, 'model_policy': None}):
        assert ProcessConfiguration.model_validate(raw).model_dump(mode='json') == old
        assert digest(ProcessConfiguration.model_validate(raw).model_dump(mode='json')) == digest(old)
    agent = AgentRegistration(name='fixture', version='v1', adapter='process', process=old)
    assert agent.model_dump(mode='json')['process'] == old
    assert 'model_policy' not in agent.model_dump_json()


@pytest.mark.parametrize('field,value', [('base_url','https://bad.invalid'), ('api_key','secret'),
    ('headers',{}), ('stream',True), ('tools',[]), ('enable_thinking',True),
    ('token_enforcement','enforced'), ('max_calls',True), ('temperature',2), ('model','https://bad.invalid')])
def test_policy_rejects_unfrozen_or_unsupported_fields(field, value):
    with pytest.raises(ValidationError):
        ModelPolicy.model_validate({'model':'qwen-plus', field:value})


def test_text_only_request_limits_and_frozen_parameters():
    policy = ModelPolicy(model='qwen-plus', max_messages=1, max_request_bytes=1024)
    call = ModelCallRequest.model_validate(payload())
    body = forwarded_body(policy, call)
    assert body['model'] == policy.model and body['max_tokens'] == 2048
    assert body['stream'] is False and body['enable_thinking'] is False
    assert len(body_bytes(body)) < 1024
    with pytest.raises(ValueError, match='byte_limit'):
        forwarded_body(policy, ModelCallRequest.model_validate(payload(text='汉'*400)))
    with pytest.raises(ValueError, match='message_limit'):
        forwarded_body(policy, ModelCallRequest(call_id='two', messages=call.messages*2))
    for extra in ({'model':'other'}, {'run_id':str(uuid4())}, {'tools':[]}):
        with pytest.raises(ValidationError): ModelCallRequest.model_validate({**payload(), **extra})
    with pytest.raises(ValidationError):
        ModelCallRequest(call_id='bad', messages=[dict(role='user',content=[{'image_url':'x'}])])


@pytest.fixture
def ledger(monkeypatch):
    config = online_config(max_calls=2, max_total_tokens=100)
    request = offline_request().model_copy(update={'config_sha256':digest(config.model_dump(mode='json'))})
    run = NS(id=request.run_id, request=request.model_dump(mode='json'), lifecycle='running',
             execution_status='pending', evaluation_outcome='pending', started_at=None, completed_at=None)
    token = uuid4()
    work = NS(active_token=token, stage='process_run', cancel_requested=False, active_seconds=0)
    grant = RunModelGrant(run_id=run.id, config_sha256=request.config_sha256,
        policy=config.model_policy.model_dump(mode='json'), calls_reserved=0, known_total_tokens=0,
        worker_token=token, expires_at=datetime.now(timezone.utc)+timedelta(seconds=120))
    session = MagicMock()
    calls = []
    session.get.side_effect = lambda model, key: grant if model is RunModelGrant else work
    def scalar(statement):
        params = statement.compile().params
        if 'call_id_1' in params:
            return next((c for c in calls if c.call_id == params['call_id_1']), None)
        return next((c.id for c in calls if c.status in gateway.INFLIGHT), None)
    def add(call):
        call.id=uuid4(); calls.append(call)
    session.scalar.side_effect = scalar
    session.scalars.side_effect = lambda stmt: [c for c in calls if c.status in gateway.INFLIGHT]
    session.add.side_effect = add
    lock = MagicMock(return_value=run)
    monkeypatch.setattr(gateway.SessionLocal, 'begin', lambda: nullcontext(session))
    monkeypatch.setattr(gateway.repo, 'get_run', lock)
    return NS(config=config, run=run, grant=grant, work=work, token=token,
              session=session, calls=calls, lock=lock)


def reserve(l, **kw):
    return gateway.reserve_call(l.run.id, l.token, payload(**kw))


def dispatch(l, call_id='first'):
    return gateway.mark_dispatched(l.run.id, l.token, call_id)


def finish(l, call_id='first', **kw):
    return gateway.finish_call(l.run.id, l.token, call_id, **kw)


USAGE = dict(prompt_tokens=10, completion_tokens=5, total_tokens=15)


def test_idempotency_one_inflight_and_row_lock(ledger):
    l=ledger
    assert reserve(l)['created']
    assert not reserve(l)['created']
    assert l.grant.calls_reserved == 1
    l.lock.assert_called_with(l.session,l.run.id,for_update=True)
    with pytest.raises(RunConflictError, match='different content'): reserve(l,text='different')
    with pytest.raises(RunConflictError, match='in flight'): reserve(l,call_id='second')
    dispatch(l)
    with pytest.raises(RunConflictError, match='never replay'): dispatch(l)
    finish(l,status='succeeded',usage=USAGE,result_sha256='a'*64)
    finish(l,status='succeeded',usage=USAGE,result_sha256='a'*64)
    assert l.grant.known_total_tokens == 15
    assert reserve(l)['status'] == 'succeeded'
    reserve(l,call_id='second'); dispatch(l,'second')
    finish(l,'second',status='failed',usage=USAGE,error_code='upstream_rejected')
    with pytest.raises(RunConflictError, match='budget'): reserve(l,call_id='third')
    assert l.grant.calls_reserved == 2


@pytest.mark.parametrize('status', ['unknown','failed','succeeded'])
def test_missing_usage_stops_subsequent_calls_and_never_refunds(ledger,status):
    l=ledger;reserve(l);dispatch(l)
    finish(l,status=status,result_sha256='b'*64 if status=='succeeded' else None)
    assert l.grant.calls_reserved == 1
    assert reserve(l)['status'] == status
    with pytest.raises(RunConflictError,match='budget'):reserve(l,call_id='second')


def test_advisory_total_exhausted_stops_next_call(ledger):
    l=ledger;reserve(l);dispatch(l)
    finish(l,status='succeeded',usage=dict(prompt_tokens=110,completion_tokens=5,total_tokens=115),result_sha256='a'*64)
    assert l.grant.known_total_tokens == 115  # Not a strict prepaid token cap.
    with pytest.raises(RunConflictError,match='budget'):reserve(l,call_id='second')


@pytest.mark.parametrize('mutation', ['expired','cancelled','wrong_token','lost_owner','wrong_stage','terminal','config_drift','revoked'])
def test_authorization_checked_on_every_admission(ledger,mutation):
    l=ledger
    if mutation=='expired': l.grant.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    elif mutation=='cancelled': l.work.cancel_requested=True
    elif mutation=='wrong_token': l.token=uuid4()
    elif mutation=='lost_owner': l.work.active_token=uuid4()
    elif mutation=='wrong_stage': l.work.stage='evaluate'
    elif mutation=='terminal': l.run.lifecycle='finished'
    elif mutation=='config_drift': l.grant.config_sha256='0'*64
    else: l.grant.revoked_at=datetime.now(timezone.utc)
    with pytest.raises(RunConflictError,match='inactive'):reserve(l)
    assert not l.calls and l.grant.calls_reserved == 0


def test_cancel_between_reserve_and_dispatch_denies_send(ledger):
    l=ledger;reserve(l);l.work.cancel_requested=True
    with pytest.raises(RunConflictError,match='inactive'):dispatch(l)
    gateway.revoke_attempt(l.session,l.run)
    assert l.calls[0].status=='unknown' and l.grant.calls_reserved==1


def test_cancel_retains_late_evidence_without_resurrecting_run(ledger):
    l=ledger;reserve(l);dispatch(l)
    l.work.cancel_requested=True;l.run.lifecycle='finished'
    gateway.revoke_attempt(l.session,l.run)
    assert l.calls[0].status=='unknown'
    finish(l,status='succeeded',usage=USAGE,result_sha256='a'*64)
    assert l.calls[0].status=='succeeded' and l.grant.known_total_tokens==15
    assert l.run.lifecycle=='finished' and l.grant.revoked_at is not None
    with pytest.raises(RunConflictError):reserve(l,call_id='second')


def test_invalid_usage_is_unknown_not_zero_and_blocks_next_call(ledger):
    l=ledger;reserve(l);dispatch(l)
    result=finish(l,status='succeeded',usage={**USAGE,'total_tokens':999},result_sha256='a'*64)
    assert result['usage'] is None and result['error_code']=='invalid_upstream_usage'
    assert l.grant.stop_reason=='usage_missing'
    with pytest.raises(RunConflictError):reserve(l,call_id='second')


def test_call_deadline_and_cross_attempt_result_are_rejected(ledger):
    l=ledger;reserve(l)
    l.calls[0].deadline=datetime.now(timezone.utc)-timedelta(seconds=1)
    with pytest.raises(RunConflictError):dispatch(l)
    with pytest.raises(RunConflictError):
        gateway.finish_call(l.run.id,uuid4(),'first',status='unknown')
    gateway.revoke_attempt(l.session,l.run)
    with pytest.raises(RunConflictError,match='before dispatch'):
        finish(l,status='succeeded',usage=USAGE,result_sha256='a'*64)


def test_worker_bind_requires_second_opt_in_and_cannot_reset_quota(ledger):
    l=ledger;l.grant.worker_token=None;l.grant.expires_at=None
    with pytest.raises(RunConflictError):gateway.bind_attempt(l.session,l.run,l.work,allow_model=False)
    gateway.bind_attempt(l.session,l.run,l.work,allow_model=True)
    assert l.grant.worker_token==l.token
    reserve(l)
    with pytest.raises(RunConflictError):gateway.bind_attempt(l.session,l.run,l.work,allow_model=True)
    assert l.grant.calls_reserved==1


def test_enqueue_requires_entry_authorization_and_saves_frozen_policy():
    config=online_config();request=offline_request().model_copy(update={'config_sha256':digest(config.model_dump(mode='json'))})
    run=NS(id=request.run_id,repository_id=uuid4(),legacy_task_id=None,request=request.model_dump(mode='json'),lifecycle='queued')
    session=MagicMock();session.get.return_value=None
    with patch.object(control.SessionLocal,'begin',return_value=nullcontext(session)), \
         patch.object(control.repo,'get_run',return_value=run), patch.object(control.repo,'append_event'), \
         patch('backend.app.services.platform_test_collector.checked_bundle',return_value=(None,{'process_config':config.model_dump(mode='json')},None)):
        with pytest.raises(RunConflictError):control.enqueue_process(run.id,bundle_sha256='b'*64)
        session.add.assert_not_called()
        control.enqueue_process(run.id,bundle_sha256='b'*64,allow_model=True)
    grant,work=[c.args[0] for c in session.add.call_args_list]
    assert isinstance(grant,RunModelGrant) and grant.policy==config.model_policy.model_dump(mode='json')
    assert isinstance(work,RunWork) and work.state['model_required'] is True


def test_model_process_preview_needs_no_native_embeddings():
    items=records()
    for row in items[1:]:
        row.descriptor['process']['model_policy']=ModelPolicy(model='qwen-plus').model_dump()
        row.content_sha256=digest(row.descriptor)
    session=MagicMock();session.get.side_effect=items
    with patch('backend.app.services.experiment_preparation.index_content') as index:
        result=experiments.freeze(session,draft())
    assert result['needs_model'] is True and result['native_index_hashes']=={}
    index.assert_not_called()


@pytest.mark.parametrize('allow_model,missing_grant', [(False,False),(True,True),(True,False)])
def test_worker_rechecks_frozen_policy_even_if_scheduling_hint_is_missing(ledger,allow_model,missing_grant):
    l=ledger
    l.run.lifecycle='preparing';l.run.version=2;l.run.execution_status='pending'
    l.run.event_sequence=0;l.run.started_at=None;l.run.completed_at=None
    l.work.state={'bundle_sha256':'b'*64};l.work.active_token=None
    l.grant.worker_token=None;l.grant.expires_at=None
    l.session.scalar.side_effect=[None,None,None,l.run]
    l.session.get.side_effect=lambda model,key: (None if missing_grant else l.grant) if model is RunModelGrant else l.work
    with patch.object(worker.repo,'append_event'), \
         patch('backend.app.services.platform_test_collector.checked_bundle',
               return_value=(None,{'process_config':l.config.model_dump(mode='json')},None)):
        if not allow_model or missing_grant:
            with pytest.raises(RunConflictError,match='both entry and worker'):worker.claim_next(allow_model=allow_model)
            assert l.work.active_token is None
        else:
            claim=worker.claim_next(allow_model=True)
            assert l.grant.worker_token==claim['token'] and l.work.state['model_required']
    if not allow_model:
        sql=str(l.session.scalar.call_args.args[0].compile(dialect=postgresql.dialect(),compile_kwargs={'literal_binds':True}))
        assert 'model_required' in sql and 'IS DISTINCT FROM true' in sql


@pytest.mark.parametrize('entry', ['run','experiment','recovery','settle'])
def test_control_paths_revoke_attempt_in_same_transaction(ledger,entry):
    from backend.app.schemas.run_control import CancelRequest
    l=ledger;reserve(l);dispatch(l)
    l.run.version=1;l.run.legacy_task_id=None;l.run.capabilities={}
    l.work.state={'model_required':True};l.work.result=None
    l.session.get.side_effect=lambda model,key,**kw: l.grant if model is RunModelGrant else (l.work if model is RunWork else l.run)
    with patch.object(control.repo,'append_event'),patch.object(worker,'import_native_events'), \
         patch('backend.app.services.gateway_runtime.cleanup_owned_attempt'):
        if entry=='run': control.request_cancel(l.run.id,CancelRequest(expected_version=1))
        elif entry=='experiment': experiments.stop_run(l.session,l.run.id)
        elif entry=='recovery': worker.recover_interrupted(l.run.id,l.token)
        else: worker.settle_step(l.run.id,l.token,elapsed=1,forced_reason='worker_exit')
    assert l.grant.revoked_at is not None and l.calls[0].status=='unknown'
    assert l.grant.calls_reserved==1


def test_online_transport_requires_operator_settings_and_worker_context(monkeypatch):
    from backend.app.agent.adapters import process
    monkeypatch.delenv('REPOPILOT_GATEWAY_RUNTIME_CONFIG', raising=False)
    manifest={'process_config':online_config().model_dump(mode='json')}
    with patch.object(process,'checked_bundle',return_value=(None,manifest,None)),patch.object(process,'run_container') as run:
        with pytest.raises(ValueError,match='runtime_not_configured'):
            process.ProcessAdapter().prepare(offline_request(),{})
        with pytest.raises(ValueError,match='worker_ownership_required'):
            process.ProcessAdapter().run(offline_request(),'process_run',{})
        run.assert_not_called()


def test_migration_and_unique_inflight_postgres_ddl_offline():
    path=Path('backend/migrations/versions/d719a01b0001_add_model_gateway_ledger.py')
    spec=importlib.util.spec_from_file_location('gateway_migration',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    output=StringIO()
    ctx=MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output})
    with Operations.context(ctx):module.upgrade();module.downgrade()
    sql=output.getvalue()
    assert 'CREATE TABLE model_calls' in sql and 'RAISE EXCEPTION' in sql
    assert "WHERE status IN ('reserved','dispatched')" in sql
    for model in (RunModelGrant,ModelCall):
        assert 'CREATE TABLE' in str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
    indices='\n'.join(str(CreateIndex(i).compile(dialect=postgresql.dialect())) for i in ModelCall.__table__.indexes)
    assert 'CREATE UNIQUE INDEX uq_model_call_inflight' in indices
