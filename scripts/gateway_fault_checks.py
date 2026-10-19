"""Fault acceptance inside probe_gateway_runtime's disposable DB, never standalone.

No production fault switches. Controlled delays live in a test-only transport;
container faults use labelled Docker resources and actual worker/adapter services.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import multiprocessing
from pathlib import Path
from threading import Barrier, Event
import time
from uuid import uuid4


def worker_child(claim):
    # multiprocessing imports this module without importing application config.
    import dotenv
    dotenv.load_dotenv = lambda *a, **k: False
    from backend.app.services.platform_worker import execute_step
    execute_step(claim)


def dispatched_crash_child(claim):
    """Die after the real DB commit, without returning/settling a transport result."""
    import os
    import dotenv
    dotenv.load_dotenv=lambda *a,**k:False
    from backend.app.services import model_gateway_service as ledger
    from backend.app.services.gateway_credentials import issue_credential
    issue_credential(claim['run_id'],claim['token'],mode='mock')
    ledger.reserve_call(claim['run_id'],claim['token'],FaultSuite.payload())
    ledger.mark_dispatched(claim['run_id'],claim['token'],'one')
    os._exit(23)


def wait_until(predicate, *, seconds=30):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate(): return
        time.sleep(0.1)
    raise TimeoutError('Fault checkpoint not reached')


class FaultSuite:
    def __init__(self, root, request, config, resources, owner):
        from backend.app.services import gateway_runtime, model_gateway_service, run_worker_service
        from backend.app.db.session import SessionLocal, engine
        self.runtime, self.ledger, self.worker = gateway_runtime, model_gateway_service, run_worker_service
        self.sessions, self.engine = SessionLocal, engine
        self.root, self.template, self.config = root, request, config
        self.resources, self.owner = resources, owner
        self.attempts, self.children, self.blockers = [], [], []
        self.checks, self.cases = {}, []

    def check(self, name, result):
        self.checks[name]=bool(result)
        if not result: raise AssertionError(name)

    def seed(self, name, *, container=False, seconds=120):
        from backend.app.db.models import Repository, PlatformRun, RunWork
        from backend.app.services import platform_artifacts as artifacts
        from backend.app.services.experiment_contract_service import digest
        from backend.app.schemas.platform_run import RunBudget
        from backend.app.schemas.process_agent import ProcessConfiguration
        run_id, token=uuid4(), uuid4()
        config=ProcessConfiguration.model_validate({**self.config.model_dump(mode='json'),
            'argv':['python','-I','/input/client.py','--hold','--concurrent']})
        request=self.template.model_copy(update={'run_id':run_id,'config_sha256':digest(config.model_dump(mode='json')),
                                                'budget':RunBudget(timeout_seconds=seconds)})
        state={'model_required':True}
        directory=artifacts.run_directory(run_id)
        if container:
            from backend.app.services import platform_test_collector as collector
            from backend.app.schemas.experiment import ExperimentCase
            from backend.app.schemas.experiment_definition import AcceptanceRule
            from backend.app.agent.adapters.process import ProcessAdapter
            source=self.root/('source-'+run_id.hex)
            files={'smoke.py':b'def value(): return 1\n',
                   'tests/test_smoke.py':b'from smoke import value\ndef test_value(): assert value() == 1\n'}
            artifacts.copy_files(files,source)
            case=ExperimentCase(case_id='gateway-fault',case_version='v1',task_type='feature',user_request=request.task_description,
                repository_commit=request.repository_commit,editable_files=['smoke.py'],
                protected_test_files=['tests/test_smoke.py'],test_profile='python-basic')
            rule=AcceptanceRule(version='v1',required_tests=[{'classname':'tests.test_smoke','name':'test_value'}])
            request=request.model_copy(update={'case_id':case.case_id,'case_version':case.case_version,
                'case_sha256':digest(case.model_dump(mode='json')),'rule_sha256':digest(rule.model_dump(mode='json')),
                'environment_sha256':collector.environment_fingerprint(config.image),
                'initial_snapshot_hash':artifacts.python_hash(files)})
            state['bundle_sha256']=collector.create_bundle(request,workspace=source,case=case,rule=rule,
                image=config.image,process_config=config.model_dump(mode='json'))
            ProcessAdapter().prepare(request,state)
            with (directory/'input/client.py').open('xb') as stream:
                stream.write(artifacts.read_bytes(Path(__file__).with_name('gateway_smoke_agent.py')))
        else:
            directory.mkdir()
        with self.sessions.begin() as session:
            repo=Repository(name='fault-'+name,source_path='disposable-fixture');session.add(repo);session.flush()
            run=PlatformRun(id=run_id,repository_id=repo.id,creation_key=str(run_id),
                request_sha256=digest(request.model_dump(mode='json')),request=request.model_dump(mode='json'),
                lifecycle='running',started_at=datetime.now(timezone.utc))
            session.add(run);session.flush()
            work=RunWork(run_id=run_id,stage='process_run',state=state,active_token=token,
                active_since=datetime.now(timezone.utc),active_seconds=0,ready=False,cancel_requested=False)
            session.add(work);session.flush()
            self.ledger.authorize_process(session,run,config,allow_model=True);session.flush()
            self.ledger.bind_attempt(session,run,work,allow_model=True)
        attempt=dict(run_id=run_id,token=token,request=request.model_dump(mode='json'),state=state,
                     stage='process_run',execution_status='pending',remaining_seconds=seconds+90)
        self.attempts.append(attempt)
        self.cases.append(dict(name=name,run_id=str(run_id),layer='docker_worker' if container else 'postgres_service'))
        return attempt

    def snapshot(self, a):
        from sqlalchemy import select
        from backend.app.db.models import PlatformRun, RunWork, RunModelGrant, ModelCall
        with self.sessions() as s:
            run=s.get(PlatformRun,a['run_id']);work=s.get(RunWork,a['run_id']);grant=s.get(RunModelGrant,a['run_id'])
            calls=list(s.scalars(select(ModelCall).where(ModelCall.run_id==a['run_id']).order_by(ModelCall.created_at)))
            return dict(lifecycle=run.lifecycle,execution=run.execution_status,version=run.version,
                cancel=work.cancel_requested,token=work.active_token,ready=work.ready,cleanup=work.cleanup_status,
                error=work.error_code,revoked=grant.revoked_at is not None,credential=grant.credential_sha256 is not None,
                count=grant.calls_reserved,calls=[dict(id=str(c.id),call_id=c.call_id,status=c.status,
                result_sha256=c.result_sha256,transport=c.transport) for c in calls])

    @staticmethod
    def payload(call_id='one'):
        return {'call_id':call_id,'messages':[{'role':'user','content':'fixed fault acceptance message'}]}

    def credential(self,a):
        from backend.app.services.gateway_credentials import issue_credential
        return issue_credential(a['run_id'],a['token'],mode='mock').secret.get_secret_value()

    def concurrent(self, *, same):
        from backend.app.services.run_lifecycle import RunConflictError
        name='same_id' if same else 'single_inflight'
        a=self.seed(name);self.credential(a)
        barrier=Barrier(8,timeout=10)
        def reserve(index):
            barrier.wait()
            try:
                value=self.ledger.reserve_call(a['run_id'],a['token'],self.payload('one' if same else f'call-{index}'))
                return 'created' if value['created'] else 'existing'
            except RunConflictError: return 'conflict'
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(reserve,range(8)))
        state=self.snapshot(a)
        self.check(name+'_eight_connections',results.count('created')==1
                   and results.count('existing' if same else 'conflict')==7)
        self.check(name+'_one_row_one_quota',state['count']==len(state['calls'])==1)
        if not same:
            from sqlalchemy.exc import IntegrityError
            from backend.app.db.models import ModelCall
            try:
                with self.sessions.begin() as session:
                    session.add(ModelCall(run_id=a['run_id'],call_id='bypass-service',worker_token=a['token'],
                        request_sha256='f'*64,status='reserved',deadline=datetime.now(timezone.utc)+timedelta(seconds=30)))
                    session.flush()
                rejected=False
            except IntegrityError:rejected=True
            self.check('postgres_unique_inflight_constraint',rejected and len(self.snapshot(a)['calls'])==1)
        self.runtime.revoke_owned_attempt(a['run_id'],a['token'])
        state=self.snapshot(a)
        self.check(name+'_unknown_no_refund',state['count']==1 and state['calls'][0]['status']=='unknown')

    def cancel_inflight(self):
        from backend.app.services.gateway_exchange import GatewayExchange, MockTransport
        from backend.app.services.gateway_credentials import GatewayUnauthorized
        from backend.app.services.run_control_service import request_cancel
        from backend.app.schemas.run_control import CancelRequest
        a=self.seed('cancel_inflight');secret=self.credential(a)
        entered, release=Event(), Event()
        class HeldMock(MockTransport):
            def invoke(inner,body,*,deadline):
                entered.set()
                if not release.wait(15): raise TimeoutError('Fixture release deadline')
                return super().invoke(body,deadline=deadline)
        exchange=GatewayExchange(transport=HeldMock(),run_id=a['run_id'],worker_token=a['token'])
        identity=exchange.authenticate(secret)
        def call():
            try: exchange.call(identity,self.payload());return 'delivered'
            except GatewayUnauthorized:return 'revoked'
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending=pool.submit(call)
            try:
                self.check('cancel_reached_dispatched',entered.wait(10) and self.snapshot(a)['calls'][0]['status']=='dispatched')
                # A real independent transaction must finish while transport is blocked.
                pool.submit(request_cancel,a['run_id'],CancelRequest(expected_version=1)).result(timeout=5)
                state=self.snapshot(a)
                self.check('cancel_commits_without_transport_lock',state['cancel'] and state['revoked']
                           and state['calls'][0]['status']=='unknown')
                try: exchange.authenticate(secret);denied=False
                except GatewayUnauthorized:denied=True
                self.check('cancel_rejects_new_auth',denied)
            finally: release.set()
            self.check('late_result_not_delivered',pending.result(timeout=10)=='revoked')
        state=self.snapshot(a)
        self.check('late_evidence_without_resurrection',state['cancel'] and state['revoked'] and state['count']==1
                   and state['execution']=='pending' and state['calls'][0]['status']=='succeeded'
                   and bool(state['calls'][0]['result_sha256']))

    def scope_and_expiry(self):
        from backend.app.services.gateway_exchange import GatewayExchange
        from backend.app.services.gateway_credentials import GatewayUnauthorized
        from backend.app.services.run_lifecycle import RunConflictError
        from backend.app.db.models import RunModelGrant
        a=self.seed('scope_expiry');b=self.seed('other_run')
        secret=self.credential(a);other=self.credential(b)
        exchange=GatewayExchange(run_id=a['run_id'],worker_token=a['token'])
        for name,action in (
            ('cross_run_denied',lambda:exchange.authenticate(other)),
            ('cross_attempt_denied',lambda:GatewayExchange(run_id=a['run_id'],worker_token=uuid4()).authenticate(secret))):
            try: action();denied=False
            except GatewayUnauthorized:denied=True
            self.check(name,denied)
        identity=exchange.authenticate(secret)
        # Deterministic persisted deadline, no fake clock in the production service.
        with self.sessions.begin() as session:
            session.get(RunModelGrant,a['run_id']).expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        try: exchange.call(identity,self.payload());denied=False
        except RunConflictError:denied=True
        self.check('expired_identity_cannot_reserve',denied and self.snapshot(a)['count']==0)
        try: exchange.authenticate(secret);denied=False
        except GatewayUnauthorized:denied=True
        self.check('expired_bearer_denied',denied)

    def recover(self,a):
        before=self.snapshot(a)
        self.worker.recover_interrupted(a['run_id'],a['token'])
        a['recovered']=True
        after=self.snapshot(a)
        self.check('recovery_no_replay_'+a['run_id'].hex[:8],after['token'] is None and not after['ready']
                   and after['lifecycle']=='interrupted' and after['calls']==before['calls']
                   and after['count']==before['count'])

    def dispatched_crash(self):
        from backend.app.services import platform_worker
        from backend.app.services.run_lifecycle import RunConflictError
        a=self.seed('dispatched_crash')
        def factory(*,target,args):
            child=multiprocessing.get_context('spawn').Process(target=dispatched_crash_child,args=args)
            self.children.append(child)
            return child
        platform_worker.supervise(a,process_factory=factory)
        state=self.snapshot(a)
        self.check('dispatched_crash_unknown',state['lifecycle']=='interrupted' and state['token']==a['token']
                   and state['count']==1 and len(state['calls'])==1 and state['calls'][0]['status']=='unknown')
        try:self.ledger.reserve_call(a['run_id'],a['token'],self.payload());denied=False
        except RunConflictError:denied=True
        self.check('dispatched_crash_cannot_replay',denied and self.snapshot(a)['count']==1)
        self.recover(a)

    def resources_absent(self,a):
        resources=self.runtime.names(a['run_id'],a['token'])
        return all(self.runtime.inspect_owned(kind,name,a['run_id'],a['token']) is None
            for kind,name in [('container',resources['agent']),('container',resources['gateway']),('network',resources['network'])]
            ) and not self.runtime.attempt_directory(a['run_id'],a['token']).exists()

    def replay_from_agent(self,a):
        script="""import json,os,urllib.request,urllib.error
from pathlib import Path
try:
    secret=Path(os.environ['REPOPILOT_MODEL_CREDENTIAL_FILE']).read_text()
    body={'call_id':'smoke-first','messages':[{'role':'user','content':'fixed smoke message; no repository data'}]}
    request=urllib.request.Request(os.environ['REPOPILOT_MODEL_GATEWAY_URL'],data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+secret})
    try:
        with urllib.request.urlopen(request,timeout=8) as response: print(response.status)
    except urllib.error.HTTPError as error: print(error.code)
except Exception: print(0)
"""
        name=self.runtime.names(a['run_id'],a['token'])['agent']
        if self.runtime.inspect_owned('container',name,a['run_id'],a['token']) is None:
            raise RuntimeError('Fault Agent missing')
        return int(self.runtime.checked('exec',name,'python','-I','-c',script))

    def blocker(self,a):
        name='rpgw-smoke-'+self.owner.hex+'-blocker'
        network=self.runtime.names(a['run_id'],a['token'])['network']
        self.resources.append(('container',name));self.blockers.append(name)
        self.runtime.checked('container','create','--pull=never','--name',name,
            '--label',f'repopilot.gateway_smoke={self.owner}','--network',network,'--read-only',
            '--user','10001:10001','--cap-drop','ALL','--security-opt','no-new-privileges',
            '--log-driver','none','--entrypoint','python',self.config.image,'-I','-c','import time; time.sleep(120)')
        self.runtime.checked('container','start',name)
        return name

    def remove_blocker(self,name):
        listed=self.runtime.checked('container','ls','--all','--filter',f'name=^/{name}$','--format','{{.Names}}')
        if name not in listed.splitlines():return
        info=json.loads(self.runtime.checked('container','inspect',name))[0]
        if info.get('Config',{}).get('Labels',{}).get('repopilot.gateway_smoke')!=str(self.owner):
            raise RuntimeError('Fault blocker ownership mismatch')
        self.runtime.checked('container','rm','--force','--volumes',name)

    def container_fault(self,kind):
        from backend.app.services import platform_worker
        from backend.app.services.run_control_service import request_cancel
        from backend.app.schemas.run_control import CancelRequest
        from sqlalchemy import text
        a=self.seed(kind,container=True,seconds=25 if kind=='deadline' else 120)
        made=Event();box=[]
        def factory(*,target,args):
            child=multiprocessing.get_context('spawn').Process(target=worker_child,args=args)
            self.children.append(child);box.append(child);made.set()
            return child
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(platform_worker.supervise,a,process_factory=factory)
            try:
                self.check(kind+'_child_created',made.wait(5))
                marker=self.runtime.artifacts.run_directory(a['run_id'])/'output/ready-for-fault'
                wait_until(lambda:marker.exists() or pending.done(),seconds=30)
                self.check(kind+'_real_agent_ready',marker.exists() and not pending.done())
                evidence=self.runtime.artifacts.decode_json(self.runtime.artifacts.read_bytes(marker.with_name('smoke-checks.json')))
                self.check(kind+'_concurrent_http',evidence.get('concurrent_http_same_id') is True and all(evidence.values()))
                child=box[0]
                if kind=='db_reconnect':
                    try:
                        with self.engine.begin() as c:
                            c.execute(text('ALTER ROLE gateway_smoke NOLOGIN'))
                            c.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename='gateway_smoke'"))
                        self.check('db_unavailable_returns_503',self.replay_from_agent(a)==503)
                    finally:
                        with self.engine.begin() as c:c.execute(text('ALTER ROLE gateway_smoke LOGIN'))
                    self.check('db_reconnect_replays_existing',self.replay_from_agent(a)==200 and self.snapshot(a)['count']==1)
                    child.terminate()  # Abrupt worker death after the live reconnect check.
                elif kind=='blocked_cleanup':
                    name=self.blocker(a)
                    child.terminate()
                elif kind=='cancel_container':
                    request_cancel(a['run_id'],CancelRequest(expected_version=1))
                elif kind=='kill_child':
                    child.terminate()
                # deadline: the real, persisted execution deadline expires naturally.
                pending.result(timeout=50)
                state=self.snapshot(a)
                self.check(kind+'_revoked',state['revoked'] and not state['credential'])
                self.check(kind+'_one_call_no_replay',state['count']==1 and len(state['calls'])==1)
                if kind=='cancel_container':
                    self.check('cancel_not_misreported_failed',state['cancel'] and (state['lifecycle']=='interrupted'
                               or state['execution']=='cancelled'))
                if kind=='deadline':
                    self.check('deadline_reports_timeout',state['execution']=='timed_out')
                if kind in ('kill_child','blocked_cleanup','db_reconnect'):
                    self.check(kind+'_fence_retained',state['lifecycle']=='interrupted' and state['token']==a['token'])
                if kind=='blocked_cleanup':
                    secret=self.runtime.attempt_directory(a['run_id'],a['token'])/'credential'
                    self.check('blocked_cleanup_keeps_secret',secret.exists())
                    try:self.worker.recover_interrupted(a['run_id'],a['token']);failed=False
                    except self.runtime.ContainerUnconfirmed:failed=True
                    self.check('blocked_recovery_cannot_clear_fence',failed and self.snapshot(a)['token']==a['token'])
                    self.remove_blocker(name)
                if state['token'] is not None:self.recover(a)
                else:a['recovered']=True
                self.check(kind+'_resources_removed',self.resources_absent(a))
            finally:
                # Only the exact subprocess created by this case can be stopped.
                if box:
                    try:
                        if box[0].is_alive():box[0].terminate()
                    except ValueError:pass  # supervisor already closed its own handle
                if not pending.done():pending.result(timeout=50)

    def run(self):
        for name,action in [('same_id',lambda:self.concurrent(same=True)),
                            ('single_inflight',lambda:self.concurrent(same=False)),
                            ('cancel_inflight',self.cancel_inflight),('scope_expiry',self.scope_and_expiry),
                            ('dispatched_crash',self.dispatched_crash),
                            *[(kind,lambda kind=kind:self.container_fault(kind)) for kind in
                              ('kill_child','blocked_cleanup','db_reconnect','cancel_container','deadline')]]:
            print('fault checkpoint: '+name,flush=True)
            self.current_case=name
            action()

    def cleanup(self):
        errors=[]
        for child in self.children:
            try:
                if child.is_alive():child.terminate();child.join(timeout=5)
                if child.is_alive():raise RuntimeError('Fault child still alive')
            except ValueError:pass
            except Exception:errors.append('fault_child_stop_unconfirmed')
        for name in self.blockers:
            try:self.remove_blocker(name)
            except Exception:errors.append('fault_blocker_cleanup_unconfirmed')
        if not errors:
            for a in self.attempts:
                if a.get('recovered'):continue
                try:
                    state=self.snapshot(a)
                    if state['token'] is None:
                        if not state['revoked'] or not self.resources_absent(a):
                            raise RuntimeError('Cleared fence without confirmed cleanup')
                    else:
                        self.worker.recover_interrupted(a['run_id'],a['token'])
                    a['recovered']=True
                except Exception:errors.append('fault_attempt_cleanup_unconfirmed')
        return errors
