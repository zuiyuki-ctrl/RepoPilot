"""Live wiring tested only with dummy credentials and simulated HTTP/Docker/SQL."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace as NS
from unittest.mock import patch

import httpx
import pytest
from pydantic import SecretStr
from backend.app.services.gateway_tls import LiveDashScopeTransport, FAKE_SECRET, live_tls_transport
from backend.app.services import gateway_runtime as runtime
from backend.app.services.gateway_observation_service import project_ledger
from backend.app.services.platform_resource_service import run_resources
from backend.app.schemas.model_gateway import ModelPolicy, ModelCallRequest, forwarded_body, body_bytes
from tests.test_gateway_runtime import deployment, run
from tests.test_model_gateway import ledger
from tests.test_gateway_upstream import response
from tests.test_gateway_observation import call, run as resource_run
from tests.test_model_gateway import payload


def test_live_protocol_uses_dummy_secret_only_in_header():
    secret = 'sk-test-only-never-a-real-key'
    seen = []
    def handler(request):
        seen.append(request)
        assert request.headers['Authorization'] == 'Bearer ' + secret
        assert secret.encode() not in request.content
        return response()
    transport = LiveDashScopeTransport(adapter=httpx.MockTransport(handler), secret=SecretStr(secret))
    raw = body_bytes(forwarded_body(ModelPolicy(model='qwen-plus'),
        ModelCallRequest(call_id='test',messages=[{'role':'user','content':'test'}])))
    result = transport.invoke(raw, deadline=datetime.now(timezone.utc)+timedelta(seconds=5))
    assert result['usage_source'] == 'provider' and len(seen) == 1
    assert secret not in repr(transport) and secret not in json.dumps(result)


def test_factory_uses_image_ca_not_environment(tmp_path, monkeypatch):
    path = tmp_path/'dummy-key'; path.write_text('sk-test-only-not-real'); path.chmod(0o444)
    monkeypatch.setenv('SSL_CERT_FILE','/nonexistent/injected-ca')
    monkeypatch.setenv('HTTPS_PROXY','http://injected.invalid')
    transport = live_tls_transport(credential_file=path)
    assert transport.mode == 'dashscope_live'
    path.chmod(0o600)
    with pytest.raises(ValueError): live_tls_transport(credential_file=path)
    with pytest.raises(ValueError):
        LiveDashScopeTransport(adapter=httpx.MockTransport(lambda _: response()),secret=SecretStr(FAKE_SECRET))


def test_live_exchange_ledger_idempotency_and_private_artifacts(ledger, tmp_path, monkeypatch):
    from backend.app.services.gateway_exchange import GatewayExchange
    from backend.app.services import gateway_credentials as credentials
    l=ledger
    monkeypatch.setattr('backend.app.services.platform_artifacts.run_directory',lambda _:tmp_path)
    issued=credentials.issue_credential(l.run.id,l.token,mode='dashscope_live')
    original=l.session.scalar.side_effect
    l.session.scalar.side_effect=lambda stmt: l.run.id if 'credential_sha256_1' in stmt.compile().params else original(stmt)
    identity=credentials.authenticate(issued.secret.get_secret_value())
    seen=[]
    def upstream(request):
        seen.append(request)
        return response()
    secret='sk-only-a-test-secret-not-real'
    exchange=GatewayExchange(transport=LiveDashScopeTransport(adapter=httpx.MockTransport(upstream),secret=SecretStr(secret)))
    first=exchange.call(identity,payload())
    second=exchange.call(identity,payload())
    assert first==second and len(seen)==1 and l.grant.calls_reserved==1
    assert first['transport']=='dashscope_live' and first['usage_source']=='provider'
    for path in tmp_path.rglob('*.json'):
        assert secret not in path.read_text(encoding='utf-8')


def enable_live(d):
    path=d.root/'dummy-provider-key';path.write_text('sk-test-only-not-real');path.chmod(0o444)
    d.settings.mode='dashscope_live'
    d.settings.live_provider=runtime.LiveProviderFiles(enabled=True,region='cn-beijing',
        provider_key=path,egress_image='sha256:'+'c'*64)


def test_live_topology_and_secret_mounts(deployment):
    d=deployment;enable_live(d)
    result=run(d)
    creates=[c for c in d.docker.commands if c[:2]==('container','create')]
    assert len(creates)==3  # No fake supplier in live mode.
    proxy=next(c for c in creates if c[c.index('--name')+1].endswith('-proxy'))
    gateway=next(c for c in creates if c[c.index('--name')+1].endswith('-gateway'))
    agent=next(c for c in creates if c[c.index('--name')+1].endswith('-agent'))
    assert '--mount' not in proxy and proxy[proxy.index('--network')+1].endswith('-egress-network')
    assert 'sha256:'+'c'*64 in proxy
    assert not any('provider-key' in arg for arg in agent)
    assert any('target=/run/repopilot/provider-key,readonly' in arg for arg in gateway)
    nets=[c for c in d.docker.commands if c[:2]==('network','create')]
    assert len(nets)==3 and sum('--internal' in c for c in nets)==2
    assert result['model_access'] is True and d.l.grant.revoked_at
    assert not d.docker.objects


@pytest.mark.parametrize('suffix',['-proxy','-gateway','-agent'])
def test_live_partial_start_cleanup(deployment,suffix):
    d=deployment;enable_live(d)
    d.docker.fail=lambda c:c[:2]==('container','start') and c[-1].endswith(suffix)
    with pytest.raises(runtime.ContainerUnconfirmed):run(d)
    assert not d.docker.objects and d.l.grant.credential_sha256 is None


def test_explicit_live_config_and_no_host_key_read(tmp_path,monkeypatch):
    database=tmp_path/'db.json';database.write_text('{}')
    key=tmp_path/'dummy-key';key.write_text('sk-test-only-not-real');key.chmod(0o444)
    raw=dict(mode='dashscope_live',image='sha256:'+'a'*64,control_network='control',database_file=str(database),
        live_provider=dict(enabled=True,region='cn-beijing',provider_key=str(key),egress_image='sha256:'+'b'*64))
    config=tmp_path/'runtime.json';config.write_text(json.dumps(raw))
    monkeypatch.setenv('REPOPILOT_GATEWAY_RUNTIME_CONFIG',str(config))
    with patch('backend.app.services.gateway_tls.read_mounted_secret',side_effect=AssertionError('Host must not read key')):
        assert runtime.load_settings().mode=='dashscope_live'
    for patch_value in ({'enabled':False},{'region':'other'},{'egress_image':'mutable:latest'}):
        changed={**raw,'live_provider':{**raw['live_provider'],**patch_value}}
        with pytest.raises(ValueError):runtime.RuntimeSettings.model_validate(changed)
    with pytest.raises(ValueError):runtime.RuntimeSettings.model_validate({**raw,'live_provider':None})
    with pytest.raises(ValueError):runtime.RuntimeSettings.model_validate({**raw,'mode':'mock'})


@pytest.mark.parametrize('status,usage_known,expected', [('succeeded',True,15),('unknown',True,None),('succeeded',False,None)])
def test_provider_totals_complete_only_when_settled_and_known(status,usage_known,expected):
    item=call(transport='dashscope_live',status=status)
    if not usage_known:item.usage=None
    grant=NS(calls_reserved=1,revoked_at=datetime.now(timezone.utc),policy={'model':'qwen-plus'})
    projected=project_ledger(item.run_id,grant,[item])
    assert projected['real_total_tokens']==expected
    assert projected['synthetic_known_total_tokens']==0
    value=run_resources(resource_run(),[],gateway=projected)
    assert value['tokens']['total_tokens']==expected
    assert value['tokens']['known_total_tokens']==(15 if usage_known else 0)
