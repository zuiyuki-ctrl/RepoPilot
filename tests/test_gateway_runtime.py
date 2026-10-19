"""Mock deployment lifecycle acceptance: simulated Docker, real local secret files.

These tests do not claim a real PostgreSQL or container deployment has passed.
"""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
from backend.app.services import gateway_runtime as runtime
from backend.app.services import run_worker_service as worker, platform_worker
from backend.app.services.gateway_credentials import GatewayUnauthorized, GatewayIdentity
from backend.app.services.gateway_exchange import GatewayExchange
from backend.app.schemas.platform_run import AgentRunRequest
from backend.app.services.run_lifecycle import RunConflictError
from tests.test_model_gateway import ledger


class FakeDocker:
    def __init__(self, run_id, token, settings):
        self.run_id, self.token, self.settings = run_id, token, settings
        self.commands, self.objects = [], {}
        self.fail = None
        self.revoked = lambda: True
        self.on_agent_start = lambda: None

    def __call__(self, *args):
        self.commands.append(args)
        if self.fail and self.fail(args):
            return NS(returncode=1, stdout='', stderr='not exported')
        value = ''
        if args[0] == 'version': value = json.dumps({'Os':'linux','Version':'28.3.2'})
        elif args[:2] == ('image','inspect'):
            value = args[-1] if '--format' in args else json.dumps([{'Config':{}}])
        elif args[:2] == ('network','inspect') and args[-1] == self.settings.control_network:
            value = json.dumps([{'Driver':'bridge','Internal':True,'EnableIPv6':False,'Options':runtime.ISOLATED}])
        elif args[1] == 'ls':
            value = '\n'.join(name for (kind, name) in self.objects if kind == args[0])
        elif args[1] == 'inspect': value = json.dumps([self.objects[(args[0], args[-1])]])
        elif args[1] == 'create':
            name = args[-1] if args[0] == 'network' else args[args.index('--name')+1]
            labels = {runtime.LABEL:str(self.token),'repopilot.run_id':str(self.run_id)}
            info = ({'Labels':labels, 'Driver':'bridge','Internal':'--internal' in args,'EnableIPv6':False,'Options':runtime.ISOLATED}
                    if args[0] == 'network' else {'Config':{'Labels':labels},'State':{'Status':'created'},
                        'HostConfig':{},'NetworkSettings':{'Networks':{args[args.index('--network')+1]:{}}}})
            self.objects[(args[0],name)] = info
        elif args[1] == 'connect':
            self.objects[('container',args[-1])]['NetworkSettings']['Networks'][args[-2]] = {}
        elif args[1] == 'start':
            info = self.objects[('container',args[-1])]
            info['State'] = {'Status':'running'}
            if args[-1].endswith('-agent'):
                self.on_agent_start()
                info['State'] = {'Status':'exited','ExitCode':0}
        elif args[1] == 'rm':
            assert self.revoked(), 'revocation must commit before resource removal'
            del self.objects[(args[0],args[-1])]
        return NS(returncode=0, stdout=value, stderr='')


@pytest.fixture
def deployment(ledger, monkeypatch, tmp_path):
    l = ledger
    root = tmp_path / 'run'; root.mkdir()
    for child in ('input','workspace','output'): (root / child).mkdir()
    database = tmp_path / 'database.json'
    database.write_text(json.dumps(dict(DB_HOST='test-db',DB_PORT='5432',DB_NAME='test',
                                        DB_USER='test',DB_PASSWORD='fixture-only')))
    settings = runtime.RuntimeSettings(mode='mock',image='sha256:'+'b'*64,
                                        control_network='test-control',database_file=database)
    monkeypatch.setattr(runtime, 'load_settings', lambda: settings)
    monkeypatch.setattr(runtime.artifacts, 'run_directory', lambda run_id: root)
    docker = FakeDocker(l.run.id, l.token, settings)
    docker.revoked = lambda: l.grant.revoked_at is not None
    monkeypatch.setattr(runtime, 'docker', docker)
    monkeypatch.setattr(runtime.time, 'sleep', lambda _: None)
    # DACL setup is exercised separately; simulated deployments never launch Windows utilities.
    monkeypatch.setattr(runtime, 'private_directory', lambda path: path.mkdir(mode=0o700))
    return NS(l=l, root=root, settings=settings, docker=docker,
              request=AgentRunRequest.model_validate(l.run.request))


def run(d):
    return runtime.run_process(d.request, d.l.config, d.root, d.l.token)


def enable_tls_fixture(d):
    paths={}
    for key in ('ca','certificate','server_key','provider_key'):
        path=d.root/('fixture-'+key)
        path.write_text('repopilot-fake-upstream-only' if key=='provider_key' else 'fixture')
        path.chmod(0o444);paths[key]=path
    d.settings.mode='dashscope_fake'
    d.settings.tls_fixture=runtime.TLSFixtureFiles(**paths)


def test_tls_runtime_mounts_and_owned_resources(deployment):
    d=deployment;enable_tls_fixture(d)
    result=run(d)
    assert result['gateway_mode']=='dashscope_fake' and result['model_access'] is False
    commands=d.docker.commands
    creates=[c for c in commands if c[:2]==('container','create')]
    gateway=next(c for c in creates if c[c.index('--name')+1].endswith('-gateway'))
    agent=next(c for c in creates if c[c.index('--name')+1].endswith('-agent'))
    supplier=next(c for c in creates if c[c.index('--name')+1].endswith('-supplier'))
    proxy=next(c for c in creates if c[c.index('--name')+1].endswith('-proxy'))
    assert any('target=/run/repopilot/provider-key,readonly' in a for a in gateway)
    assert not any('provider-key' in a or 'server.key' in a or 'database.json' in a for a in agent)
    assert any('target=/run/fixture/server.key,readonly' in a for a in supplier)
    assert '--mount' not in proxy
    assert len([c for c in commands if c[:2]==('network','create')])==3
    assert not d.docker.objects and d.l.grant.credential_sha256 is None


@pytest.mark.parametrize('suffix',['-supplier','-proxy','-gateway'])
def test_tls_partial_start_failure_revokes_and_cleans(deployment,suffix):
    d=deployment;enable_tls_fixture(d)
    d.docker.fail=lambda c:c[:2]==('container','start') and c[-1].endswith(suffix)
    with pytest.raises(runtime.ContainerUnconfirmed):run(d)
    assert not d.docker.objects and d.l.grant.revoked_at and d.l.grant.credential_sha256 is None


def test_tls_proxy_cleanup_failure_keeps_credential(deployment):
    d=deployment;enable_tls_fixture(d)
    d.docker.fail=lambda c:c[:2]==('container','rm') and c[-1].endswith('-proxy')
    with pytest.raises(runtime.ContainerUnconfirmed):run(d)
    directory=runtime.attempt_directory(d.l.run.id,d.l.token)
    assert (directory/'credential').exists() and d.l.grant.revoked_at
    d.docker.fail=None
    runtime.cleanup_owned_attempt(d.l.run.id,d.l.token)
    assert not directory.exists() and not d.docker.objects


def test_complete_mock_deployment_mounts_scope_revokes_and_removes(deployment):
    d=deployment
    def inspect_running():
        path=runtime.attempt_directory(d.l.run.id,d.l.token)/'credential'
        assert path.read_text().startswith('rpgw_')
        assert d.l.grant.credential_sha256 is not None
        create=[a for a in d.docker.commands if a[:2]==('container','create')]
        agent,gateway=create[1],create[0]
        assert 'REPOPILOT_MODEL_TRANSPORT=mock' in agent
        assert any('target=/run/repopilot/credential,readonly' in a for a in agent)
        assert not any('database.json' in a or '/evidence/' in a for a in agent)
        assert not any('/workspace' in a or '/input' in a or 'target=/run/repopilot/credential,' in a for a in gateway)
        assert path.read_text() not in str(create)
        assert not any(flag in agent for flag in ('--publish','--privileged','--network=host'))
    d.docker.on_agent_start=inspect_running
    result=run(d)
    assert result['exit_code']==0 and result['gateway_mode']=='mock' and result['model_access'] is False
    assert result['stdout']==result['stderr']=='' and result['writers_stopped']
    assert d.l.grant.revoked_at and d.l.grant.credential_sha256 is None
    assert not d.docker.objects and not runtime.attempt_directory(d.l.run.id,d.l.token).exists()
    assert d.settings.database_file.exists()  # Operator-owned file is untouched.
    runtime.cleanup_owned_attempt(d.l.run.id,d.l.token)  # Parent may repeat cleanup safely.


@pytest.mark.parametrize('failure',['network','gateway_create','connect','gateway_start','health','agent_create','agent_start'])
def test_partial_setup_failure_revokes_and_cleans_without_fallback(deployment,failure):
    d=deployment
    def fail(args):
        return ((failure=='network' and args[:2]==('network','create'))
            or (failure=='gateway_create' and args[:2]==('container','create') and any(a.endswith('-gateway') for a in args))
            or (failure=='connect' and args[:2]==('network','connect'))
            or (failure=='gateway_start' and args[:2]==('container','start') and args[-1].endswith('-gateway'))
            or (failure=='health' and args[0]=='exec')
            or (failure=='agent_create' and args[:2]==('container','create') and any(a.endswith('-agent') for a in args))
            or (failure=='agent_start' and args[:2]==('container','start') and args[-1].endswith('-agent')))
    d.docker.fail=fail
    with pytest.raises(RuntimeError): run(d)
    assert d.l.grant.revoked_at and not d.docker.objects
    assert not runtime.attempt_directory(d.l.run.id,d.l.token).exists()
    assert not any('host' in a or '--publish' in a for a in d.docker.commands)


def test_cancel_between_gateway_and_agent_start_is_rejected(deployment,monkeypatch):
    d=deployment
    original=runtime.ensure_active
    calls=[]
    def active(run_id,token):
        calls.append(True)
        if len(calls)==2: d.l.work.cancel_requested=True
        original(run_id,token)
    monkeypatch.setattr(runtime,'ensure_active',active)
    with pytest.raises(RunConflictError): run(d)
    assert not any(a[:2]==('container','start') and a[-1].endswith('-agent') for a in d.docker.commands)
    assert d.l.grant.revoked_at and not d.docker.objects


def test_failed_cleanup_retains_file_and_fence_until_explicit_recovery(deployment):
    d=deployment
    d.docker.fail=lambda args: args[:2]==('container','rm') and args[-1].endswith('-agent')
    with pytest.raises(runtime.ContainerUnconfirmed,match='retain worker fence'):run(d)
    assert d.l.work.active_token==d.l.token and d.l.grant.revoked_at
    assert (runtime.attempt_directory(d.l.run.id,d.l.token)/'credential').exists()
    d.docker.fail=None
    runtime.cleanup_owned_attempt(d.l.run.id,d.l.token)
    assert not d.docker.objects and not runtime.attempt_directory(d.l.run.id,d.l.token).exists()


def test_foreign_resource_is_not_removed(deployment):
    d=deployment
    name=runtime.names(d.l.run.id,d.l.token)['agent']
    d.docker.objects[('container',name)]={'Config':{'Labels':{runtime.LABEL:str(uuid4())}}}
    with pytest.raises(runtime.ContainerUnconfirmed):run(d)
    assert ('container',name) in d.docker.objects
    assert not any(a[1]=='rm' and a[-1]==name for a in d.docker.commands)


def test_unconfirmed_revocation_stops_resources_but_keeps_secret(deployment,monkeypatch):
    d=deployment
    def on_start():
        monkeypatch.setattr(runtime,'revoke_owned_attempt',MagicMock(side_effect=RuntimeError('DB unavailable')))
        d.docker.revoked=lambda: True  # Removing isolated writers remains safe on DB failure.
    d.docker.on_agent_start=on_start
    with pytest.raises(runtime.ContainerUnconfirmed):run(d)
    assert not d.docker.objects
    assert (runtime.attempt_directory(d.l.run.id,d.l.token)/'credential').exists()
    assert d.l.work.active_token==d.l.token


def test_deployed_gateway_rejects_other_run_and_attempt(ledger):
    l=ledger
    identity=GatewayIdentity(l.run.id,l.token,l.grant.config_sha256,l.grant.expires_at,l.config.model_policy,'mock')
    store=NS(authenticate=lambda _:identity)
    for run_id,token in ((uuid4(),l.token),(l.run.id,uuid4())):
        with pytest.raises(GatewayUnauthorized):
            GatewayExchange(store=store,run_id=run_id,worker_token=token).authenticate('fixture')
    assert GatewayExchange(store=store,run_id=l.run.id,worker_token=l.token).authenticate('fixture')==identity


def test_settings_opt_in_strict_mock_absolute_files(tmp_path,monkeypatch):
    monkeypatch.delenv('REPOPILOT_GATEWAY_RUNTIME_CONFIG',raising=False)
    with pytest.raises(ValueError,match='not_configured'):runtime.load_settings()
    database=tmp_path/'database.json';database.write_text('{}')
    path=tmp_path/'runtime.json'
    raw=dict(mode='mock',image='sha256:'+'a'*64,control_network='control',database_file=str(database))
    path.write_text(json.dumps(raw));monkeypatch.setenv('REPOPILOT_GATEWAY_RUNTIME_CONFIG',str(path))
    assert runtime.load_settings().mode=='mock'
    for extra in ({'mode':'live'},{'provider_key':'bad'},{'database_file':'relative.json'},{'image':'mutable:latest'}):
        path.write_text(json.dumps({**raw,**extra}))
        with pytest.raises(ValueError):runtime.load_settings()


def test_mock_rejects_nonisolated_control_network(deployment,monkeypatch):
    d=deployment;original=d.docker
    def docker(*args):
        if args[:2]==('network','inspect') and args[-1]==d.settings.control_network:
            return NS(returncode=0,stdout=json.dumps([{'Internal':False,'Driver':'bridge'}]))
        return original(*args)
    monkeypatch.setattr(runtime,'docker',docker)
    with pytest.raises(ValueError,match='internal and isolated'):run(d)
    assert not d.docker.objects and d.l.grant.revoked_at


def test_supervisor_revokes_before_stopping_child_and_cleans_before_settling(monkeypatch):
    events=[]
    child=MagicMock(pid=123);child.is_alive.side_effect=[True,True,False,False]
    child.terminate.side_effect=lambda:events.append('terminate')
    claim=dict(run_id=uuid4(),token=uuid4(),remaining_seconds=0,stage='process_run',
               request={'agent':{'adapter':'process'}},state={'model_required':True,'bundle_sha256':'x'})
    monkeypatch.setattr(runtime,'revoke_owned_attempt',lambda *a:events.append('revoke'))
    monkeypatch.setattr(runtime,'cleanup_owned_attempt',lambda *a:events.append('cleanup'))
    monkeypatch.setattr(worker,'settle_step',lambda *a,**kw:events.append('settle'))
    monkeypatch.setattr('backend.app.services.platform_container.remove_owned',lambda *a:None)
    platform_worker.supervise(claim,process_factory=MagicMock(return_value=child))
    assert events.index('revoke')<events.index('terminate')<events.index('cleanup')<events.index('settle')


def test_failed_recovery_cleanup_cannot_clear_fence(ledger,monkeypatch):
    l=ledger;l.work.state={'model_required':True}
    monkeypatch.setattr(runtime,'cleanup_owned_attempt',MagicMock(side_effect=runtime.ContainerUnconfirmed()))
    with pytest.raises(runtime.ContainerUnconfirmed):worker.recover_interrupted(l.run.id,l.token)
    assert l.work.active_token==l.token and l.grant.revoked_at


def test_online_adapter_uses_trusted_token_and_suppresses_unreviewed_trace(deployment,monkeypatch):
    from backend.app.agent.adapters import process
    d=deployment
    monkeypatch.setattr(process,'checked_bundle',lambda *a:(d.root,{'process_config':d.l.config.model_dump(mode='json')},None))
    offline=MagicMock(side_effect=AssertionError('Offline fallback forbidden'))
    monkeypatch.setattr(process,'run_container',offline)
    monkeypatch.setattr(process,'read_trace',MagicMock(side_effect=AssertionError('Raw online trace forbidden')))
    adapter=process.ProcessAdapter();adapter.bind_worker_attempt(d.l.token)
    step=adapter.run(d.request,'process_run',{'model_required':True})
    assert step.state['process_execution']['gateway_mode']=='mock'
    assert step.state['process_execution']['trace']['events']==[]
    assert step.state['process_execution']['protocol_error']=='invalid_or_missing_result'
    assert adapter.cleanup()=={'status':'confirmed'}
