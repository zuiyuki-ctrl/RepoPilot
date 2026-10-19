"""Worker-owned, non-model preparation. Never replay an uncertain filesystem operation."""
import logging
from pathlib import Path
from uuid import UUID, uuid4
from sqlalchemy import select, text
from ..db.session import SessionLocal
from ..db.models import Repository, RepositoryFile, CodeChunk, PlatformRun, RunWork
from ..db.models.platform_experiment import PlatformExperiment, ExperimentMember
from ..schemas.platform_catalog import BenchmarkCaseBinding
from ..schemas.platform_run import AgentRunRequest
from ..schemas.run_config import AgentRunConfig
from . import platform_artifacts as artifacts
from .experiment_contract_service import digest
from .run_lifecycle import RunConflictError, transition

logger=logging.getLogger(__name__)


def index_content(session,repository_id):
    fields=('file_path','symbol_name','symbol_type','start_line','end_line','content','chunk_metadata','embedding_model')
    return [{**{k:getattr(c,k) for k in fields},'embedding':c.embedding.tolist() if c.embedding is not None else None}
            for c in session.scalars(select(CodeChunk).where(CodeChunk.repository_id==repository_id)
                .order_by(CodeChunk.file_path,CodeChunk.start_line,CodeChunk.end_line,CodeChunk.symbol_name,CodeChunk.id))]


def prepare(claim):
    from .catalog_validation_service import validate_benchmark, require_image
    from .platform_test_collector import create_bundle, environment_fingerprint, runner_fingerprint
    from .platform_run_service import create_run
    from .run_control_service import enqueue_process, enqueue_native
    manifest=claim['manifest']
    if digest(manifest)!=claim['manifest_sha256']: raise ValueError('Experiment manifest changed')
    if runner_fingerprint()!=manifest['runner_sha256']: raise ValueError('Test runner changed')
    binding=BenchmarkCaseBinding.model_validate(manifest['suite']['descriptor']['cases'][claim['case_index']])
    # Repeat filesystem/image checks. Does not run tests or use models.
    checked=validate_benchmark(dict(id=claim['id'],descriptor=dict(name='prepare',version='1',cases=[binding.model_dump(mode='json')])))
    expected=manifest['suite']['validation']['cases'][claim['case_index']]
    if checked['cases'][0]['files_sha256']!=expected['files_sha256']: raise ValueError('Frozen repository files changed')
    agent=manifest['agents'][claim['arm']]['descriptor']
    with SessionLocal() as session:
        repository=session.get(Repository,binding.repository_id)
        root=Path(repository.workspace_path)
    repository_id=binding.repository_id
    files=artifacts.inventory(root,source_repository=True)
    task_id=None
    config=agent.get('process')
    if agent['adapter']=='process':
        require_image(config['image'])
        identity=dict(name=agent['name'],version=agent['version'],adapter='process',implementation_sha256=config['image'].removeprefix('sha256:'))
        budget={'timeout_seconds':manifest['draft']['timeout_seconds']}
    else:
        from ..agent.adapters.native import NativeAdapter
        from ..schemas.repository import RepositoryCreate
        from ..schemas.task import TaskCreate
        from .repository_service import create_repository
        from .task_service import create_task
        from ..core.config import EMBEDDING_MODEL
        metadata=NativeAdapter().metadata()
        if metadata['implementation_sha256']!=agent['implementation_sha256']: raise ValueError('Native implementation changed')
        with SessionLocal() as session:
            source_index=index_content(session,binding.repository_id)
        if digest(source_index)!=manifest['native_index_hashes'][str(binding.repository_id)]:
            raise ValueError('Frozen Native index changed')
        if not source_index or any(c['embedding'] is None or c['embedding_model']!=EMBEDDING_MODEL for c in source_index):
            raise ValueError('Native requires complete existing embeddings; prepare index explicitly')
        fresh=create_repository(RepositoryCreate(name=f'Experiment {claim["id"]}',source_path=str(root)))
        repository_id=fresh.id
        root=Path(fresh.workspace_path)
        # Copy only verified same-content index into an independent repository. No new embedding call.
        with SessionLocal.begin() as session:
            ids={}
            for path in sorted({c['file_path'] for c in source_index}):
                if path not in files: raise ValueError('Index path missing')
                import hashlib
                source=session.scalar(select(RepositoryFile).where(RepositoryFile.repository_id==binding.repository_id,RepositoryFile.path==path))
                if source is None or source.file_hash!=hashlib.sha256(files[path]).hexdigest(): raise ValueError('Stale source index')
                row=RepositoryFile(id=uuid4(),repository_id=repository_id,path=path,language=source.language,file_hash=source.file_hash,size=source.size)
                session.add(row); ids[path]=row.id
            session.flush()
            for chunk in source_index:
                session.add(CodeChunk(repository_id=repository_id,file_id=ids[chunk['file_path']],**chunk))
        native=AgentRunConfig.model_validate({**agent['native'],'runtime_fingerprint':agent['implementation_sha256']})
        task=create_task(TaskCreate(repository_id=repository_id,user_request=binding.case.user_request,task_type='plan',run_config=native))
        if task is None: raise ValueError('Native task creation failed')
        task_id=task.id
        identity=dict(name=agent['name'],version=agent['version'],adapter='native',
                      implementation_sha256=metadata['implementation_sha256'])
        config=native.model_dump(mode='json')
        budget=dict(timeout_seconds=manifest['draft']['timeout_seconds'],max_tool_calls=native.max_tool_calls)
    request=AgentRunRequest(run_id=claim['id'],case_id=binding.case.case_id,case_version=binding.case.case_version,
        task_description=binding.case.user_request,repository_commit=binding.case.repository_commit,agent=identity,
        config_sha256=digest(config),case_sha256=digest(binding.case.model_dump(mode='json')),
        task_type=binding.case.task_type,rule_sha256=digest(binding.acceptance.model_dump(mode='json')),
        environment_sha256=environment_fingerprint(binding.test_image),initial_snapshot_hash=artifacts.python_hash(files),
        editable_files=binding.case.editable_files,budget=budget)
    run=create_run(request,repository_id=repository_id,legacy_task_id=task_id,creation_key=f'experiment:{claim["id"]}')
    with SessionLocal.begin() as session:
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':714202603})
        member=session.get(ExperimentMember,claim['id'],with_for_update=True)
        if member.active_token!=claim['token']: raise RunConflictError('Preparation ownership lost')
        member.run_id=run.id
    bundle=create_bundle(request,workspace=root,case=binding.case,rule=binding.acceptance,image=binding.test_image,
                         process_config=config if agent['adapter']=='process' else None)
    if agent['adapter']=='process': enqueue_process(run.id,bundle_sha256=bundle,allow_model=manifest.get('allow_model') is True)
    else: enqueue_native(run.id,bundle_sha256=bundle)


def execute_preparation(claim):
    from .platform_container import remove_owned
    from .platform_experiment_service import stop_run
    error=None
    cleanup=True
    try: prepare(claim)
    except Exception as exc:
        logger.exception('Experiment preparation failed; member=%s',claim['id'])
        error=type(exc).__name__
    finally:
        try: remove_owned(claim['id'],'agent')
        except Exception:
            cleanup=False
            logger.exception('Preparation container cleanup unconfirmed')
    with SessionLocal.begin() as session:
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':714202603})
        member=session.get(ExperimentMember,claim['id'],with_for_update=True)
        if member.active_token!=claim['token']: raise RunConflictError('Preparation ownership lost')
        run=session.get(PlatformRun,claim['id'])
        if run: member.run_id=run.id
        member.error_code=error or (None if cleanup else 'cleanup_unconfirmed')
        member.status='ready' if not error and cleanup else ('preparation_failed' if cleanup else 'interrupted')
        if error and run:
            work=session.get(RunWork,run.id)
            if work: work.ready=False
            if run.lifecycle=='queued': transition(run,expected_version=run.version,target='preparing')
            transition(run,expected_version=run.version,target='interrupted')
        if cleanup: member.active_token=None
        experiment=session.get(PlatformExperiment,member.experiment_id)
        if experiment.cancel_requested and run: stop_run(session,run.id)
