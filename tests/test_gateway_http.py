"""HTTP -> real gateway services -> simulated SQL storage. No provider or real DB."""
from datetime import datetime, timedelta, timezone
from io import StringIO
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.app.gateway_app import create_gateway_app
from backend.app.services import gateway_credentials as credentials, model_gateway_service as ledger_service
from backend.app.services.gateway_exchange import GatewayExchange, MockTransport, GatewayArtifactStore
from backend.app.services.run_lifecycle import RunConflictError
from tests.test_model_gateway import ledger, payload


class HTTPFixture(NS):
    def __repr__(self):
        return '<HTTP gateway fixture; credential redacted>'


@pytest.fixture
def http_gateway(ledger, monkeypatch, tmp_path):
    l = ledger
    original = l.session.scalar.side_effect
    def scalar(statement):
        params = statement.compile().params
        if 'credential_sha256_1' in params:
            return l.run.id if params['credential_sha256_1'] == l.grant.credential_sha256 else None
        return original(statement)
    l.session.scalar.side_effect = scalar
    issued = credentials.issue_credential(l.run.id, l.token, mode='mock')
    root = tmp_path / 'run'; root.mkdir()
    monkeypatch.setattr('backend.app.services.platform_artifacts.run_directory', lambda run_id: root)
    exchange = GatewayExchange()
    transport = exchange.transport
    original_invoke = transport.invoke
    calls = []
    def invoke(body, **kwargs):
        calls.append(body)
        return original_invoke(body, **kwargs)
    monkeypatch.setattr(transport, 'invoke', invoke)
    with TestClient(create_gateway_app(exchange)) as client:
        yield HTTPFixture(l=l, client=client, exchange=exchange, issued=issued, root=root, calls=calls,
                 headers={'Authorization':'Bearer '+issued.secret.get_secret_value()})


def post(g, data=None, **kwargs):
    return g.client.post('/v1/model-calls', json=payload() if data is None else data,
                         headers=g.headers, **kwargs)


def test_request_to_ledger_to_mock_and_idempotent_artifact_replay(http_gateway):
    g=http_gateway
    first=post(g);second=post(g)
    assert first.status_code==second.status_code==200 and first.json()==second.json()
    value=first.json()
    assert value['transport']=='mock' and value['usage'] is None
    assert g.l.grant.calls_reserved==1 and len(g.calls)==1
    actual=json.loads(g.calls[0])
    assert actual['model']==g.l.config.model_policy.model and actual['stream'] is False
    assert set(actual)=={'model','messages','stream','enable_thinking','temperature','max_tokens'}
    assert post(g,payload(call_id='second')).status_code==409  # No fabricated mock provider usage.
    assert post(g,payload(text='changed')).status_code==409
    assert first.headers['cache-control']=='no-store'
    saved=''.join(p.read_text(encoding='utf-8') for p in g.root.rglob('*.json'))
    assert g.issued.secret.get_secret_value() not in saved
    assert 'Authorization' not in saved and str(g.l.token) not in saved


def test_only_credential_hash_persisted_and_no_public_issuance(http_gateway):
    g=http_gateway;secret=g.issued.secret.get_secret_value()
    assert len(g.l.grant.credential_sha256)==64 and g.l.grant.credential_sha256!=secret
    assert secret not in repr(g.issued) and secret not in str(g.issued)
    for path in ('/docs','/openapi.json','/api/v2/runs','/credentials','/cancel'):
        assert g.client.post(path).status_code==404
    assert g.client.get('/health').json()['model_access'] is False
    with pytest.raises(RunConflictError):credentials.issue_credential(g.l.run.id,g.l.token,mode='mock')
    with pytest.raises(ValueError):credentials.issue_credential(g.l.run.id,g.l.token,mode='dashscope')


@pytest.mark.parametrize('state',['expired','revoked','lost_owner','cancelled','not_running','wrong_stage'])
def test_expired_cancelled_and_cross_attempt_credentials_rejected(http_gateway,state):
    g=http_gateway;l=g.l
    if state=='expired': l.grant.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    elif state=='revoked': ledger_service.revoke_attempt(l.session,l.run)
    elif state=='lost_owner': l.work.active_token=uuid4()
    elif state=='cancelled': l.work.cancel_requested=True
    elif state=='not_running': l.run.lifecycle='finished'
    else: l.work.stage='evaluate'
    response=post(g)
    assert response.status_code==401 and response.json()=={'error':'invalid_credential'}
    assert not g.calls and l.grant.calls_reserved==0


@pytest.mark.parametrize('extra',[{'run_id':str(uuid4())},{'model':'qwen-other'},
    {'url':'http://host.docker.internal:8000'},{'headers':{'Authorization':'secret'}},{'tools':[]}])
def test_body_cannot_select_another_run_or_upstream(http_gateway,extra):
    g=http_gateway
    assert post(g,{**payload(),**extra}).status_code==422
    assert not g.calls and g.l.grant.calls_reserved==0


def test_invalid_credential_and_ambiguous_headers(http_gateway):
    g=http_gateway
    for secret in ('','Bearer invalid','Bearer rpgw_'+'x'*43,'Bearer '+str(g.l.run.id)):
        result=g.client.post('/v1/model-calls',json=payload(),headers={'Authorization':secret})
        assert result.status_code==401
    result=g.client.post('/v1/model-calls',json=payload(),headers=[
        ('Authorization',g.headers['Authorization']),('Authorization',g.headers['Authorization'])])
    assert result.status_code==400 and not g.calls


def test_body_limit_duplicate_json_keys_and_content_type(http_gateway):
    g=http_gateway
    headers={**g.headers,'Content-Type':'application/json'}
    assert g.client.post('/v1/model-calls',content=b'x'*65537,headers=headers).status_code==413
    # Streamed/chunked body has no Content-Length; it must still be bounded.
    assert g.client.post('/v1/model-calls',content=iter([b'x'*40000,b'y'*40000]),headers=headers).status_code==413
    assert g.client.post('/v1/model-calls',content=b'{"call_id":"a","call_id":"b"}',headers=headers).status_code==422
    assert g.client.post('/v1/model-calls',content=b'bad',headers=g.headers).status_code==415
    assert not g.calls and g.l.grant.calls_reserved==0


def test_inflight_duplicate_does_not_dispatch(http_gateway):
    g=http_gateway
    ledger_service.reserve_call(g.l.run.id,g.l.token,payload())
    result=post(g)
    assert result.status_code==202 and result.json()['status']=='reserved'
    assert not g.calls and g.l.grant.calls_reserved==1


def test_unknown_result_never_retries_and_redacts_exception(http_gateway,monkeypatch):
    g=http_gateway
    def fail(*args,**kwargs):
        g.calls.append(b'attempt')
        raise RuntimeError('sensitive upstream details '+g.issued.secret.get_secret_value())
    monkeypatch.setattr(g.exchange.transport,'invoke',fail)
    first=post(g);second=post(g)
    assert first.status_code==second.status_code==502
    assert g.l.calls[0].status=='unknown' and len(g.calls)==1
    assert 'sensitive' not in first.text and g.issued.secret.get_secret_value() not in first.text
    assert g.l.grant.calls_reserved==1


def test_late_response_is_retained_but_revoked_attempt_cannot_receive_it(http_gateway,monkeypatch):
    g=http_gateway
    def cancel(*args,**kwargs):
        ledger_service.revoke_attempt(g.l.session,g.l.run)
        g.l.work.cancel_requested=True;g.l.run.lifecycle='finished'
        return {'message':{'role':'assistant','content':'late mock'},'usage':None}
    monkeypatch.setattr(g.exchange.transport,'invoke',cancel)
    response=post(g)
    assert response.status_code==401
    assert g.l.calls[0].status=='succeeded' and g.l.run.lifecycle=='finished'
    assert g.l.grant.credential_sha256 is None
    assert list((g.root/'gateway'/'responses').glob('*.json'))


def test_missing_cached_artifact_does_not_trigger_reexecution(http_gateway):
    g=http_gateway
    assert post(g).status_code==200
    path=next((g.root/'gateway'/'responses').glob('*.json'))
    path.unlink()  # Test-owned temporary artifact only.
    assert post(g).status_code==503 and len(g.calls)==1


def test_cancel_between_authentication_and_reservation_never_dispatches(http_gateway):
    g=http_gateway
    identity=g.exchange.authenticate(g.issued.secret.get_secret_value())
    ledger_service.revoke_attempt(g.l.session,g.l.run)
    with pytest.raises(RunConflictError):g.exchange.call(identity,payload())
    assert not g.calls and not g.l.calls


def test_timeout_keeps_quota_and_never_automatically_resends(http_gateway,monkeypatch):
    g=http_gateway
    def fail(*args,**kwargs):
        g.calls.append(b'attempt')
        raise TimeoutError('private error')
    monkeypatch.setattr(g.exchange.transport,'invoke',fail)
    assert post(g).status_code==502
    assert post(g).json()['error_code']=='upstream_timeout'
    assert len(g.calls)==1 and g.l.grant.calls_reserved==1


def test_tampered_artifact_cannot_be_returned_or_regenerated(http_gateway):
    g=http_gateway
    assert post(g).status_code==200
    path=next((g.root/'gateway'/'responses').glob('*.json'))
    path.write_text('{"tampered":true}',encoding='utf-8')
    assert post(g).status_code==503 and len(g.calls)==1


def test_pre_dispatch_artifact_failure_prevents_mock_call(http_gateway,monkeypatch):
    g=http_gateway
    def fail(*args,**kwargs):raise OSError('private local path')
    monkeypatch.setattr(g.exchange.artifacts,'write',fail)
    result=post(g)
    assert result.status_code==502 and not g.calls
    assert g.l.calls[0].status=='unknown' and g.l.calls[0].dispatched_at is None
    assert g.l.grant.calls_reserved==1 and 'private' not in result.text


def test_wrong_worker_cannot_issue_or_reuse_grant(ledger):
    with pytest.raises(RunConflictError):credentials.issue_credential(ledger.run.id,uuid4(),mode='mock')
    ledger.grant.calls_reserved=1
    with pytest.raises(RunConflictError):credentials.issue_credential(ledger.run.id,ledger.token,mode='mock')


def test_credential_migration_compiles_and_guards_evidence():
    spec=importlib.util.spec_from_file_location('gateway_credentials_migration',
        Path('backend/migrations/versions/d719a02b0001_add_gateway_credentials.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    output=StringIO()
    ctx=MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output})
    with Operations.context(ctx):module.upgrade();module.downgrade()
    sql=output.getvalue()
    assert 'credential_sha256' in sql and 'UNIQUE' in sql and 'RAISE EXCEPTION' in sql
    assert module.down_revision=='d719a01b0001'
