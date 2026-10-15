"""Worker-only protocol/environment probes; never run a paid Native model stage."""
import hashlib
import logging
import subprocess
from pathlib import Path
from ..db.session import SessionLocal
from ..db.models import Repository
from ..schemas.platform_catalog import AgentRegistration, BenchmarkRegistration
from ..schemas.platform_run import AgentRunRequest
from ..agent.adapters.process import parse_result, read_trace
from . import platform_artifacts as artifacts, platform_catalog_service as store
from .platform_container import docker, run_container, remove_owned
from .experiment_contract_service import digest

logger = logging.getLogger(__name__)


def require_image(image):
    result = docker('image', 'inspect', '--format', '{{.Id}}', image)
    if result.returncode or result.stdout.strip() != image:
        raise ValueError('local_image_unavailable')


def validate_agent(claim):
    descriptor = dict(claim['descriptor'])
    frozen_native = descriptor.pop('implementation_sha256', None)
    registration = AgentRegistration.model_validate(descriptor)
    if registration.adapter == 'native':
        from ..agent.adapters.native import NativeAdapter
        if NativeAdapter().metadata()['implementation_sha256'] != frozen_native:
            raise ValueError('native_runtime_changed')
        if registration.native.runtime_fingerprint not in (None, frozen_native):
            raise ValueError('native_runtime_changed')
        if registration.native.test_image_id:
            require_image(registration.native.test_image_id)
        return dict(passed=True, scope='native_static_contract', reason='runtime_matches_no_model_execution',
                    validated_capabilities=[], declared_capabilities=registration.declared_capabilities)
    config = registration.process
    require_image(config.image)
    directory = artifacts.run_directory(claim['id'])
    directory.mkdir()  # Never reuse an interrupted validation workspace.
    for name in ('input', 'output'):
        (directory / name).mkdir()
    files = {'task_list.py': b'def list_tasks(tasks, **kwargs): return tasks\n',
             'tests/test_task_list.py': b'def test_protocol_fixture(): pass\n'}
    artifacts.copy_files(files, directory / 'workspace')
    (directory / 'output').chmod(0o777)
    request = AgentRunRequest(run_id=claim['id'], case_id='task-list', case_version='protocol-probe-v1',
        task_description='Protocol validation fixture: respond using result.json; only task_list.py is editable. No model calls required.',
        repository_commit='0'*40, agent=dict(name=registration.name, version=registration.version,
            adapter='process', implementation_sha256=config.image.removeprefix('sha256:')),
        config_sha256=digest(config.model_dump(mode='json')), case_sha256=digest({'fixture':'protocol-probe-v1'}),
        task_type='bug_fix', rule_sha256=digest({'scope':['task_list.py']}), environment_sha256=digest({'image':config.image}),
        initial_snapshot_hash=artifacts.python_hash(files), editable_files=['task_list.py'], budget={'timeout_seconds':10})
    artifacts.write_json(directory / 'input' / 'request.json', request.model_dump(mode='json'))
    result = run_container(claim['id'], 'agent', image=config.image, argv=config.argv,
        mounts=[(directory/'input','/input',True), (directory/'workspace','/workspace',False),
                (directory/'output','/output',False)], workdir='/workspace', timeout_seconds=10)
    artifacts.write_json(directory / 'process-log.json', result)
    if result['timed_out']:
        raise ValueError('protocol_probe_timed_out')
    reported, status = parse_result(directory/'output'/'result.json', request, result['exit_code'])
    if status != 'completed':
        raise ValueError('protocol_probe_not_completed')
    after = artifacts.inventory(directory/'workspace')
    artifacts.check_profile(after)
    changed = {p for p in files.keys() | after.keys() if files.get(p) != after.get(p)}
    if changed - {'task_list.py'} or 'task_list.py' not in after:
        raise ValueError('protocol_probe_scope_violated')
    trace = read_trace(directory/'output'/'trace.jsonl', request, config.trace)
    if config.trace and trace['status'] in ('missing', 'invalid'):
        raise ValueError('declared_trace_missing_or_invalid')
    return dict(passed=True, scope='process_protocol_probe', reason='protocol_and_scope_checked',
                validated_capabilities=['execution'], declared_capabilities=registration.declared_capabilities,
                trace_status=trace['status'], task_success_evaluated=False)


def validate_benchmark(claim):
    registration = BenchmarkRegistration.model_validate(claim['descriptor'])
    checks = []
    checked_images = set()
    for item in registration.cases:
        with SessionLocal() as session:
            repo = session.get(Repository, item.repository_id)
            if repo is None or not repo.workspace_path or repo.commit_hash != item.case.repository_commit:
                raise ValueError('repository_binding_mismatch')
            root = Path(repo.workspace_path)
        for arguments, expected in [(['rev-parse','HEAD'],item.case.repository_commit),
                                     (['status','--porcelain','--untracked-files=all'],'')]:
            result = subprocess.run(['git','-C',str(root),*arguments], capture_output=True, text=True, timeout=15)
            if result.returncode or result.stdout.strip() != expected:
                raise ValueError('repository_commit_or_clean_state_mismatch')
        files = artifacts.inventory(root, source_repository=True)
        artifacts.check_profile(files)
        if set(item.case.editable_files + item.case.protected_test_files) - files.keys():
            raise ValueError('declared_file_missing')
        require_image(item.test_image)
        if item.test_image not in checked_images:
            probe = run_container(claim['id'], 'agent', image=item.test_image,
                argv=['python', '-I', '-c', 'import pytest; print(pytest.__version__)'],
                mounts=[], workdir='/tmp', timeout_seconds=10)
            if probe['timed_out'] or probe['exit_code'] != 0:
                raise ValueError('test_image_pytest_unavailable')
            checked_images.add(item.test_image)
        checks.append(dict(case_id=item.case.case_id, case_version=item.case.case_version,
            initial_snapshot_hash=artifacts.python_hash(files), files_sha256=digest({
                path: hashlib.sha256(content).hexdigest() for path,content in sorted(files.items())}),
            protected_test_hashes={path: hashlib.sha256(files[path]).hexdigest() for path in item.case.protected_test_files},
            test_image=item.test_image, pytest_import_checked=True))
    return dict(passed=True, scope='benchmark_environment', reason='environment_checked_baseline_not_run', cases=checks)


def execute_validation(claim):
    cleanup_confirmed = True
    try:
        if digest(claim['descriptor']) != claim['content_sha256']:
            raise ValueError('registered_content_hash_mismatch')
        report = validate_agent(claim) if claim['kind'] == 'agents' else validate_benchmark(claim)
    except Exception as exc:
        logger.exception('Catalog validation failed; job_id=%s', claim['id'])
        # Do not expose arbitrary subprocess/configuration exception text to HTTP clients.
        known = {'local_image_unavailable', 'native_runtime_changed', 'protocol_probe_timed_out',
                 'protocol_probe_not_completed', 'protocol_probe_scope_violated',
                 'declared_trace_missing_or_invalid', 'repository_binding_mismatch',
                 'repository_commit_or_clean_state_mismatch', 'declared_file_missing',
                 'registered_content_hash_mismatch', 'test_image_pytest_unavailable', 'Result identity mismatch'}
        report = dict(passed=False, reason=str(exc) if str(exc) in known else 'validation_failed',
                      error_type=type(exc).__name__)
    finally:
        if claim['kind'] == 'benchmarks' or claim['descriptor'].get('adapter') == 'process':
            try:
                remove_owned(claim['id'], 'agent')
            except Exception:
                logger.exception('Catalog cleanup unconfirmed; job_id=%s token=%s', claim['id'], claim['token'])
                cleanup_confirmed = False
    store.settle_validation(claim, report, cleanup_confirmed=cleanup_confirmed)
