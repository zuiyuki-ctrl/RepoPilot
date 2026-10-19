"""Disposable PostgreSQL + Docker: mock, TLS-fake, or live topology with a closed grant.

Never loads .env, migrates an existing DB, pulls/builds an image or calls a model.
Live no-call uses a generated dummy key and closes quota before Agent startup.
Uses a fresh UUID-labelled PostgreSQL container with tmpfs data, loopback-only
ephemeral port, and a least-privilege gateway role. Keeps a non-secret report.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import sys
import hashlib
import time
from uuid import uuid4
import dotenv

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'repopilot.gateway_smoke'


def inspect_live_topology(runtime, run_id, token, control, checks):
    names=runtime.names(run_id,token)
    nodes={key:runtime.inspect_owned('container',names[key],run_id,token) for key in ('agent','gateway','proxy')}
    expected={'agent':{names['network']},'gateway':{control,names['network'],names['proxy-network']},
              'proxy':{names['proxy-network'],names['egress-network']}}
    checks['live_network_membership']=all(set(nodes[key]['NetworkSettings']['Networks'])==value for key,value in expected.items())
    checks['no_published_ports_or_privilege']=all(not n['HostConfig'].get('PortBindings') and not n['HostConfig'].get('Privileged') for n in nodes.values())
    checks['live_secret_mount_only_gateway']=all(not any(m['Destination']=='/run/repopilot/provider-key' for m in nodes[k]['Mounts']) for k in ('agent','proxy')) \
        and any(m['Destination']=='/run/repopilot/provider-key' and m['RW'] is False for m in nodes['gateway']['Mounts'])
    checks['proxy_has_no_mounts']=not nodes['proxy']['Mounts']
    # Disallowed CONNECT is rejected before resolving/dialling any provider.
    command="import socket; s=socket.create_connection(('provider-egress',8081),2); s.sendall(b'CONNECT example.invalid:443 HTTP/1.1\\r\\nHost: example.invalid:443\\r\\n\\r\\n'); data=s.recv(256); s.close(); assert data.startswith(b'HTTP/1.1 403')"
    checks['production_proxy_rejects_non_provider']=runtime.docker('exec',names['gateway'],'python','-I','-c',command).returncode==0
    if not all(checks.values()):
        raise RuntimeError('Live topology inspection failed')


def run_probe(gateway_image, agent_image, postgres_image, *, faults=False, tls_fixture=False, live_no_call=False, egress_image=None):
    if sum((faults, tls_fixture, live_no_call)) > 1:
        raise ValueError('Runtime checkpoints must be run separately')
    if live_no_call != (egress_image is not None):
        raise ValueError('Live no-call checkpoint requires explicit egress image')
    # Must happen before importing any database/config module in this process.
    if 'backend.app.db.session' in sys.modules or 'backend.app.core.config' in sys.modules:
        raise RuntimeError('Run the disposable probe in a fresh interpreter; existing DB binding forbidden')
    dotenv.load_dotenv = lambda *args, **kwargs: False
    from backend.app.services import gateway_runtime as runtime
    from backend.app.services import platform_artifacts as artifacts
    from backend.app.services.experiment_contract_service import digest
    from backend.app.schemas.platform_run import AgentRunRequest
    from backend.app.schemas.process_agent import ProcessConfiguration
    from backend.app.schemas.model_gateway import ModelPolicy
    for image in (gateway_image, agent_image, postgres_image, *([egress_image] if egress_image else [])):
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
            raise ValueError('Use existing immutable local image IDs')
        if runtime.checked('image','inspect','--format','{{.Id}}',image) != image:
            raise ValueError('Required image not available')
    owner, run_id, token = uuid4(), uuid4(), uuid4()
    prefix = 'rpgw-smoke-' + owner.hex
    root = ROOT / '.platform-artifacts' / 'gateway-runtime-smoke' / str(owner)
    root.parent.mkdir(parents=True, exist_ok=True)
    runtime.private_directory(root)
    resources=[]
    engine=None
    attempt_created=False
    attempt_clean=False
    fault_suite=None
    report=dict(schema_version=1, probe_id=str(owner), run_id=str(run_id), gateway_image=gateway_image,
                agent_image=agent_image, postgres_image=postgres_image,
                transport='dashscope_live' if live_no_call else 'dashscope_fake' if tls_fixture else 'mock', model_access=False,
                acceptance_scope='live_topology_closed_grant_no_provider_dispatch' if live_no_call else 'fake_exchange',
                started_at=datetime.now(timezone.utc).isoformat(), checks={}, cleanup_confirmed=False)
    if faults:
        report['fault_sources']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
            'scripts/probe_gateway_runtime.py','scripts/gateway_fault_checks.py','scripts/gateway_smoke_agent.py',
            'backend/app/services/platform_worker.py','backend/app/services/run_worker_service.py',
            'backend/app/services/gateway_runtime.py','backend/app/services/model_gateway_service.py')}
    checks=report['checks']

    def inspect(kind, name):
        listed=runtime.checked(kind,'ls',*(['--all'] if kind=='container' else []),'--filter',f'name={name}',
                               '--format','{{.Names}}' if kind=='container' else '{{.Name}}')
        if name not in listed.splitlines(): return None
        info=json.loads(runtime.checked(kind,'inspect',name))[0]
        labels=info.get('Config',{}).get('Labels') if kind=='container' else info.get('Labels')
        if (labels or {}).get(LABEL)!=str(owner): raise RuntimeError('Smoke ownership mismatch')
        return info

    def create_network(suffix, isolated):
        name=prefix+'-'+suffix;resources.append(('network',name))
        args=['network','create','--driver','bridge','--label',f'{LABEL}={owner}']
        if isolated:
            args.append('--internal')
            for key,value in runtime.ISOLATED.items(): args.extend(['--opt',f'{key}={value}'])
        runtime.checked(*args,name)
        if isolated and not runtime.isolated_network(inspect('network',name)):
            raise RuntimeError('Smoke control network differs')
        return name

    try:
        # Non-secret local worker port, never use an existing DB address or credentials.
        outside=create_network('db-host',False)
        control=create_network('control',True)
        password=secrets.token_urlsafe(32)
        password_file=root/'postgres-password'
        with password_file.open('x',encoding='ascii') as stream: stream.write(password)
        password_file.chmod(0o444)
        db_name=prefix+'-postgres';resources.append(('container',db_name))
        runtime.checked('container','create','--pull=never','--name',db_name,'--label',f'{LABEL}={owner}',
            '--network',outside,'--publish','127.0.0.1::5432','--log-driver','none','--memory','512m',
            '--pids-limit','128','--tmpfs','/var/lib/postgresql/data:rw,nosuid,size=256m',
            '--env','POSTGRES_PASSWORD_FILE=/run/password','--env','POSTGRES_DB=gateway_smoke',
            *runtime.mount(password_file,'/run/password',True),postgres_image)
        runtime.checked('network','connect','--alias','gateway-db',control,db_name)
        runtime.checked('container','start',db_name)
        for _ in range(30):
            if runtime.docker('exec',db_name,'pg_isready','-U','postgres','-d','gateway_smoke').returncode==0: break
            time.sleep(0.3)
        else: raise RuntimeError('Temporary PostgreSQL not ready')
        info=inspect('container',db_name)
        port=info['NetworkSettings']['Ports']['5432/tcp'][0]['HostPort']
        os.environ.update(DB_HOST='127.0.0.1',DB_PORT=port,DB_NAME='gateway_smoke',DB_USER='postgres',
                          DB_PASSWORD=password,DASHSCOPE_API_KEY='',CHAT_BASE_URL='',CHAT_MODEL='',
                          EMBEDDING_ENDPOINT='',PLATFORM_ARTIFACT_ROOT=str(root/'runs'))
        from backend.app.db.session import engine, SessionLocal
        from backend.app.db.base import Base
        from backend.app.db.models import Repository,PlatformRun,RunWork,RunModelGrant,ModelCall
        from backend.app.services import model_gateway_service as ledger
        from sqlalchemy import text,select
        engine.hide_parameters=True
        with engine.begin() as connection: connection.execute(text('CREATE EXTENSION vector'))
        # Fresh disposable DB only. Not an Alembic upgrade/downgrade acceptance.
        Base.metadata.create_all(engine)
        gateway_password=secrets.token_urlsafe(32)
        with engine.begin() as connection:
            # Generated URL-safe alphabet only, never supplied by an operator/Agent.
            connection.exec_driver_sql("CREATE ROLE gateway_smoke LOGIN PASSWORD '"+gateway_password+"'")
            connection.exec_driver_sql('GRANT CONNECT ON DATABASE gateway_smoke TO gateway_smoke')
            connection.exec_driver_sql('GRANT USAGE ON SCHEMA public TO gateway_smoke')
            connection.exec_driver_sql('GRANT SELECT ON platform_runs, run_work, run_model_grants, model_calls TO gateway_smoke')
            connection.exec_driver_sql('GRANT UPDATE (id) ON platform_runs TO gateway_smoke')
            connection.exec_driver_sql('GRANT UPDATE ON run_model_grants, model_calls TO gateway_smoke')
            connection.exec_driver_sql('GRANT INSERT ON model_calls TO gateway_smoke')
        database=root/'database.json'
        artifacts.write_json(database,dict(DB_HOST='gateway-db',DB_PORT='5432',DB_NAME='gateway_smoke',
                                           DB_USER='gateway_smoke',DB_PASSWORD=gateway_password))
        database.chmod(0o444)
        settings=root/'runtime.json'
        mode='dashscope_live' if live_no_call else 'dashscope_fake' if tls_fixture else 'mock'
        fixture_files=None
        live_files=None
        if live_no_call:
            (root/'fixture-provider-key').write_text('sk-local-probe-never-a-real-key',encoding='ascii')
            (root/'fixture-provider-key').chmod(0o444)
            live_files=dict(enabled=True,region='cn-beijing',provider_key=str(root/'fixture-provider-key'),egress_image=egress_image)
        if tls_fixture:
            import shutil, subprocess
            openssl=shutil.which('openssl') or 'C:/Program Files/Git/usr/bin/openssl.exe'
            subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                '-subj','/CN=dashscope.aliyuncs.com','-addext','subjectAltName=DNS:dashscope.aliyuncs.com',
                '-keyout',str(root/'fixture-server.key'),'-out',str(root/'fixture-ca.pem')],
                check=True,capture_output=True,timeout=20)
            (root/'fixture-provider-key').write_text('repopilot-fake-upstream-only',encoding='ascii')
            for name in ('fixture-server.key','fixture-ca.pem','fixture-provider-key'):(root/name).chmod(0o444)
            fixture_files=dict(ca=str(root/'fixture-ca.pem'),certificate=str(root/'fixture-ca.pem'),
                server_key=str(root/'fixture-server.key'),provider_key=str(root/'fixture-provider-key'))
        artifacts.write_json(settings,dict(mode=mode,image=gateway_image,control_network=control,
                                            database_file=str(database),tls_fixture=fixture_files,live_provider=live_files))
        os.environ['REPOPILOT_GATEWAY_RUNTIME_CONFIG']=str(settings)
        config=ProcessConfiguration(image=agent_image,argv=['python','-I','/input/client.py', *(['--live-no-call'] if live_no_call else [])],
                                    model_policy=ModelPolicy(model='qwen-plus'))
        request=AgentRunRequest(run_id=run_id,case_id='gateway-smoke',case_version='v1',task_description='mock only',
            repository_commit='a'*40,agent=dict(name='smoke',version='v1',adapter='process',
                                               implementation_sha256=agent_image.removeprefix('sha256:')),
            config_sha256=digest(config.model_dump(mode='json')),case_sha256='b'*64,task_type='feature',
            rule_sha256='c'*64,environment_sha256='d'*64,initial_snapshot_hash='e'*64,
            editable_files=['smoke.py'],budget={'timeout_seconds':120})
        directory=artifacts.run_directory(run_id);directory.mkdir()
        for name in ('input','output','workspace'):
            (directory/name).mkdir();(directory/name).chmod(0o777)
        with (directory/'input/client.py').open('xb') as stream:
            stream.write(artifacts.read_bytes(Path(__file__).with_name('gateway_smoke_agent.py')))
        with SessionLocal.begin() as session:
            repo=Repository(name='disposable-smoke',source_path='not-a-real-repository');session.add(repo);session.flush()
            run=PlatformRun(id=run_id,repository_id=repo.id,creation_key=str(owner),request_sha256=digest(request.model_dump(mode='json')),
                request=request.model_dump(mode='json'),lifecycle='running',started_at=datetime.now(timezone.utc))
            session.add(run);session.flush()
            work=RunWork(run_id=run_id,stage='process_run',state={'model_required':True},active_token=token,
                active_since=datetime.now(timezone.utc),ready=False,active_seconds=0,cancel_requested=False)
            session.add(work);session.flush()
            ledger.authorize_process(session,run,config,allow_model=True);session.flush()
            ledger.bind_attempt(session,run,work,allow_model=True)
            if live_no_call:
                session.get(RunModelGrant,run_id).stop_reason='acceptance_no_dispatch'
                session.flush()
        attempt_created=True
        original_checked=runtime.checked
        def observed_checked(*args):
            if live_no_call and args==('container','start',runtime.names(run_id,token)['agent']):
                inspect_live_topology(runtime,run_id,token,control,checks)
            return original_checked(*args)
        runtime.checked=observed_checked
        try:
            result=runtime.run_process(request,config,directory,token)
        finally:
            runtime.checked=original_checked
        attempt_clean=True
        report['execution']=result
        checks['agent_exit_zero']=result['exit_code']==0 and not result['timed_out']
        checks.update(artifacts.decode_json(artifacts.read_bytes(directory/'output/smoke-checks.json')))
        with SessionLocal() as session:
            calls=list(session.scalars(select(ModelCall).where(ModelCall.run_id==run_id)))
            grant=session.get(RunModelGrant,run_id)
            expected_calls=0 if live_no_call else 2 if tls_fixture else 1
            checks['persisted_successes']=len(calls)==expected_calls and all(c.status=='succeeded' and c.transport==mode for c in calls)
            checks['fake_usage_labelled' if tls_fixture else 'no_fabricated_usage']=(grant.known_total_tokens==30
                and all(c.usage==dict(prompt_tokens=10,completion_tokens=5,total_tokens=15) for c in calls)) if tls_fixture else (
                grant.known_total_tokens==0 and (not calls if live_no_call else len(calls)==1 and calls[0].usage is None))
            checks['credential_revoked']=grant.revoked_at is not None and grant.credential_sha256 is None
            checks['conservative_quota']=grant.calls_reserved==expected_calls and (tls_fixture or grant.stop_reason==('acceptance_no_dispatch' if live_no_call else 'usage_missing'))
            if calls:
                report['call']=dict(call_id=calls[0].call_id,status=calls[0].status,request_sha256=calls[0].request_sha256,
                                    result_sha256=calls[0].result_sha256,transport=calls[0].transport,usage=calls[0].usage)
        checks['credential_file_removed']=not runtime.attempt_directory(run_id,token).exists()
        # Read actual temporary DB + artifacts through the new C projection, not
        # reconstructed fixture values. This DB is still deleted at probe end.
        with SessionLocal.begin() as session:
            finished=session.get(PlatformRun,run_id)
            finished.lifecycle='finished';finished.completed_at=datetime.now(timezone.utc)
        from backend.app.services.gateway_observation_service import get_ledger
        from backend.app.services.gateway_request_evidence import get_request_evidence
        observed=get_ledger(run_id)
        checks['public_ledger_source']=observed['call_count']==expected_calls and observed['real_total_tokens'] is None
        report['public_ledger']=observed
        if tls_fixture:
            previews=[get_request_evidence(run_id,item['id']) for item in observed['items']]
            checks['historical_request_previews']=all(p['status']=='recorded' and p['hash_verified']
                and p['preview']['messages'][0]['content']=='fixed smoke message; no repository data' for p in previews)
            report['request_previews']=previews
        if faults:
            from .gateway_fault_checks import FaultSuite
            fault_suite=FaultSuite(root,request,config,resources,owner)
            fault_suite.run()
    except Exception as exc:
        report['error_code']=type(exc).__name__  # Never raw SQL/connection/request errors.
    finally:
        cleanup_errors=[]
        if fault_suite is not None:
            cleanup_errors.extend(fault_suite.cleanup())
            report['fault_checks']=fault_suite.checks
            report['fault_cases']=fault_suite.cases
            report['fault_last_case']=getattr(fault_suite,'current_case',None)
        if attempt_created:
            try:
                runtime.cleanup_owned_attempt(run_id,token)
                attempt_clean=True
            except Exception:
                attempt_clean=False
                cleanup_errors.append('attempt_cleanup_unconfirmed')
        if engine is not None: engine.dispose()
        # Preserve the DB if revocation/resource cleanup is uncertain: recovery
        # needs its durable ownership/credential records, not just a JSON report.
        if (not attempt_created or attempt_clean) and not cleanup_errors:
            for kind in ('container','network'):
                for resource_kind,name in reversed(resources):
                    if kind!=resource_kind: continue
                    try:
                        if inspect(kind,name) is not None:
                            runtime.checked(kind,'rm',*(['--force','--volumes'] if kind=='container' else []),name)
                        if inspect(kind,name) is not None: raise RuntimeError('Removal unconfirmed')
                    except Exception: cleanup_errors.append('smoke_resource_cleanup_unconfirmed')
            if not cleanup_errors:
                for name in ('postgres-password','database.json','runtime.json','fixture-server.key',
                             'fixture-ca.pem','fixture-provider-key'):
                    path=root/name
                    try:
                        if path.exists():
                            artifacts.read_bytes(runtime.safe_path(path),limit=8192)
                            path.chmod(0o600);path.unlink()
                    except Exception: cleanup_errors.append('smoke_secret_cleanup_unconfirmed')
        else:
            cleanup_errors.append('temporary_database_retained_for_recovery')
        report['cleanup_confirmed']=not cleanup_errors
        report['cleanup_errors']=cleanup_errors
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        report['status']=('cleanup_unconfirmed' if cleanup_errors else 'inconclusive' if report.get('error_code')
                          else 'passed' if checks and all(checks.values())
                          and (not faults or (report.get('fault_checks') and all(report['fault_checks'].values()))) else 'failed')
        artifacts.write_json(root/'report.json',report)
    print(json.dumps(dict(status=report['status'],checks=checks,cleanup_confirmed=report['cleanup_confirmed'],
                          fault_checks=report.get('fault_checks'),error_code=report.get('error_code'),
                          report=str(root/'report.json')),ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway-image',required=True)
    parser.add_argument('--agent-image',required=True)
    parser.add_argument('--postgres-image',required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--faults',action='store_true',help='Also exercise concurrency and faults in disposable resources')
    parser.add_argument('--tls-fixture',action='store_true',help='Isolated fake TLS supplier, never a real model')
    parser.add_argument('--live-no-call',action='store_true',help='Live topology, dummy key and pre-closed disposable grant; no provider requests')
    parser.add_argument('--egress-image')
    args=parser.parse_args()
    if not args.execute: parser.error('Temporary Docker resources require explicit --execute')
    return run_probe(args.gateway_image,args.agent_image,args.postgres_image,faults=args.faults,tls_fixture=args.tls_fixture,
                     live_no_call=args.live_no_call,egress_image=args.egress_image)


if __name__=='__main__':
    raise SystemExit(main())
