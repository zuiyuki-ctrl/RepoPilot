"""Freeze comparisons before execution; retain every planned attempt, including preparation failures."""
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import select, text
from ..db.session import SessionLocal
from ..db.models import PlatformRun, RunWork
from ..db.models.platform_catalog import AgentVersion, BenchmarkVersion
from ..db.models.platform_experiment import PlatformExperiment, ExperimentMember
from ..schemas.platform_experiment import ExperimentDraft
from .experiment_contract_service import digest
from .run_lifecycle import RunConflictError

LOCK = 714202603


def differences(left, right, prefix=''):
    if isinstance(left, dict) and isinstance(right, dict):
        return [p for key in sorted(left.keys() | right.keys())
                for p in differences(left.get(key), right.get(key), f'{prefix}.{key}' if prefix else key)]
    return [] if left == right else [prefix]


def freeze(session, draft):
    suite = session.get(BenchmarkVersion, draft.suite_id)
    agents = [session.get(AgentVersion, key) for key in (draft.baseline_agent_id, draft.candidate_agent_id)]
    if suite is None or any(row is None for row in agents):
        raise LookupError('Registered version not found')
    for row in [suite, *agents]:
        if row.status != 'ready' or not row.validation or not row.validation.get('cleanup_confirmed'):
            raise RunConflictError('All versions must have completed validation')
        if digest(row.descriptor) != row.content_sha256:
            raise RunConflictError('Registered content differs from hash')
    # Labels are identity, not an experimental strategy. Compare executable configuration and capabilities.
    configs = [{k:v for k,v in row.descriptor.items() if k not in ('name','version')} for row in agents]
    # Preparation always binds the registered runtime, so absent vs explicit equal fingerprints
    # are not an actual executable strategy difference.
    for config in configs:
        if config['adapter']=='native':
            config['native']={**config['native'],'runtime_fingerprint':config['implementation_sha256']}
    changed = differences(*configs)
    if draft.mode == 'controlled':
        if configs[0]['adapter'] != configs[1]['adapter']:
            raise RunConflictError('Different adapters require benchmark mode')
        if set(changed) != set(draft.changed_fields) or not changed:
            raise RunConflictError('Controlled mode requires exact nonempty changed_fields matching preview')
        if any(p in ('implementation_sha256','process.image','declared_capabilities') for p in changed):
            raise RunConflictError('Different implementations/capabilities require benchmark mode')
    needs_model = any(c['adapter']=='native' for c in configs)
    for config in configs:
        native = config.get('native') or {}
        if any(native.get(k) is not None for k in ('index_fingerprint','experiment_contract_sha256','test_image_id')):
            raise RunConflictError('Register Native strategy without old per-run bindings')
    if len(suite.descriptor['cases'])*2*draft.repetitions > 40:
        raise RunConflictError('Batch limit is 40 Runs')
    from .platform_test_collector import runner_fingerprint
    from .experiment_preparation import index_content
    index_hashes={str(item['repository_id']):digest(index_content(session,UUID(item['repository_id'])))
                  for item in suite.descriptor['cases']} if needs_model else {}
    return dict(schema_version=1, draft=draft.model_dump(mode='json'),
        runner_sha256=runner_fingerprint(), native_index_hashes=index_hashes,
        suite=dict(id=str(suite.id), content_sha256=suite.content_sha256, descriptor=suite.descriptor,
                   validation=suite.validation),
        agents={arm:dict(id=str(row.id),content_sha256=row.content_sha256,descriptor=row.descriptor)
                for arm,row in zip(('baseline','candidate'),agents)},
        changed_fields=changed, run_count=len(suite.descriptor['cases'])*2*draft.repetitions,
        needs_model=needs_model, intervention={'native':'manual_plan_and_each_candidate','process':'none'},
        limitations=['Protocol fixtures are not model effectiveness evidence',
                     'No automatic embedding; Native requires a matching existing index',
                     'Approval waits can change actual execution order; timestamps retained'])


def preview(draft):
    with SessionLocal() as session:
        manifest = freeze(session,draft)
        return dict(manifest=manifest, preview_sha256=digest(manifest))


def start(data):
    request_hash = digest(data.model_dump(mode='json'))
    with SessionLocal.begin() as session:
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':LOCK})
        old = session.scalar(select(PlatformExperiment).where(PlatformExperiment.request_key==data.request_key))
        if old:
            if old.request_sha256 != request_hash:
                raise RunConflictError('Start key already used for another request')
            return {'id':old.id,'manifest_sha256':old.manifest_sha256}
        draft = ExperimentDraft.model_validate({k:v for k,v in data.model_dump().items() if k in ExperimentDraft.model_fields})
        manifest = freeze(session,draft)
        if digest(manifest) != data.preview_sha256:
            raise RunConflictError('Preview changed; inspect a fresh preview before starting')
        if manifest['needs_model'] and not data.allow_model:
            raise RunConflictError('Native requires explicit model authorization and worker --allow-model')
        manifest['allow_model'] = data.allow_model
        experiment=PlatformExperiment(request_key=data.request_key, request_sha256=request_hash,
            manifest=manifest,manifest_sha256=digest(manifest),cancel_requested=False)
        session.add(experiment); session.flush()
        arms = ('baseline','candidate') if draft.order=='baseline_first' else ('candidate','baseline')
        sequence=0
        for repetition in range(1,draft.repetitions+1):
            for index in range(len(manifest['suite']['descriptor']['cases'])):
                for arm in arms:
                    sequence+=1
                    session.add(ExperimentMember(experiment_id=experiment.id,sequence=sequence,case_index=index,
                        repetition=repetition,arm=arm,status='queued'))
        return {'id':experiment.id,'manifest_sha256':experiment.manifest_sha256}


def read(experiment_id):
    with SessionLocal() as session:
        experiment=session.get(PlatformExperiment,experiment_id)
        if experiment is None: return None
        members=[]
        for member in session.scalars(select(ExperimentMember).where(ExperimentMember.experiment_id==experiment_id).order_by(ExperimentMember.sequence)):
            run=session.get(PlatformRun,member.run_id) if member.run_id else None
            members.append(dict(id=member.id,sequence=member.sequence,case_index=member.case_index,
                repetition=member.repetition,arm=member.arm,status=member.status,error_code=member.error_code,
                claimed_at=member.claimed_at,run_id=member.run_id,lifecycle=run.lifecycle if run else None,
                execution_status=run.execution_status if run else None,evaluation_outcome=run.evaluation_outcome if run else None,
                started_at=run.started_at if run else None,
                interruption_token=member.active_token if member.status in ('preparing','interrupted') else None))
        terminal=all(m['status'] in ('preparation_failed','cancelled','interrupted') or m['lifecycle'] in ('finished','interrupted') for m in members)
        return dict(id=experiment.id,manifest=experiment.manifest,manifest_sha256=experiment.manifest_sha256,
            created_at=experiment.created_at,cancel_requested=experiment.cancel_requested,
            status='settled' if terminal else 'active',members=members)


def list_experiments(limit=50,offset=0):
    with SessionLocal() as session:
        return [dict(id=e.id,name=e.manifest['draft']['name'],created_at=e.created_at,
                     cancel_requested=e.cancel_requested,manifest_sha256=e.manifest_sha256)
                for e in session.scalars(select(PlatformExperiment).order_by(PlatformExperiment.created_at.desc(),PlatformExperiment.id.desc()).limit(limit).offset(offset))]


def cancel(experiment_id):
    with SessionLocal.begin() as session:
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':LOCK})
        experiment=session.get(PlatformExperiment,experiment_id,with_for_update=True)
        if experiment is None: raise LookupError('Experiment not found')
        experiment.cancel_requested=True
        for member in session.scalars(select(ExperimentMember).where(ExperimentMember.experiment_id==experiment_id)):
            if member.status=='queued': member.status='cancelled'
            if member.run_id:
                stop_run(session,member.run_id)
        return {'cancel_requested':True}


def stop_run(session,run_id):
    from ..db.repositories.platform_run_repo import append_event
    run=session.get(PlatformRun,run_id,with_for_update=True)
    work=session.get(RunWork,run_id)
    if run and work and run.lifecycle not in ('finished','interrupted','evaluating') and not work.cancel_requested:
        work.cancel_requested,work.ready=True,True
        run.version+=1
        append_event(session,run,event_type='CANCEL_REQUESTED',payload={'source':'experiment'})


def assert_no_preparation(session):
    if session.scalar(select(ExperimentMember.id).where(ExperimentMember.active_token.is_not(None)).limit(1)):
        raise RunConflictError('Unsettled experiment preparation; explicit recovery required')


def claim_preparation(*,allow_model):
    from .platform_catalog_service import assert_no_catalog_writer
    with SessionLocal.begin() as session:
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':LOCK})
        assert_no_preparation(session); assert_no_catalog_writer(session)
        if session.scalar(select(RunWork.run_id).where(RunWork.active_token.is_not(None)).limit(1)):
            raise RunConflictError('Unsettled Run exists')
        query=select(ExperimentMember).join(PlatformExperiment).where(ExperimentMember.status=='queued',PlatformExperiment.cancel_requested.is_(False))
        if not allow_model:
            query=query.where(PlatformExperiment.manifest['needs_model'].as_boolean().is_(False))
        member=session.scalar(query.order_by(PlatformExperiment.created_at,ExperimentMember.sequence).with_for_update(of=ExperimentMember).limit(1))
        if member is None: return None
        experiment=session.get(PlatformExperiment,member.experiment_id)
        member.status,member.active_token,member.claimed_at='preparing',uuid4(),datetime.now(timezone.utc)
        return dict(id=member.id,token=member.active_token,manifest=experiment.manifest,
                    manifest_sha256=experiment.manifest_sha256,case_index=member.case_index,arm=member.arm)


def recover_preparation(member_id,token):
    # Caller holds worker singleton lock and confirms the preparation process has stopped.
    from .platform_container import remove_owned
    with SessionLocal() as session:
        member=session.get(ExperimentMember,member_id)
        if member is None or member.active_token!=token: raise RunConflictError('Preparation token differs')
    remove_owned(member_id,'agent')
    with SessionLocal.begin() as session:
        member=session.get(ExperimentMember,member_id,with_for_update=True)
        if member is None or member.active_token!=token: raise RunConflictError('Preparation token differs')
        if session.get(PlatformRun,member_id): member.run_id=member_id
        if member.run_id: stop_run(session,member.run_id)
        member.active_token=None
        member.status='interrupted'
        member.error_code='explicit_recovery_no_replay'
