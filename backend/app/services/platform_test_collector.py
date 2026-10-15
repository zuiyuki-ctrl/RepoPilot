"""Fixed Python/pytest authority, shared by Native and Process. No agent test commands."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from uuid import uuid4
from ..schemas.experiment import ExperimentCase
from ..schemas.experiment_definition import AcceptanceRule
from ..schemas.platform_evaluation import EvaluationInput, TestEvidence
from ..schemas.platform_run import AgentRunRequest
from . import platform_artifacts as artifacts
from .platform_container import run_container
from .experiment_contract_service import digest
from .platform_evaluation_service import platform_test_outcomes as test_outcomes
from .test_report_parser import read_test_report

# Import pytest before adding untrusted code to sys.path. No discovery of workspace
# config/conftest, no autoloaded entry-point plugins, no host PYTEST_* environment.
PYTEST_BOOTSTRAP = """import os, sys
for key in list(os.environ):
    if key.startswith('PYTEST_'):
        del os.environ[key]
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True
import pytest
sys.path.insert(0, '/workspace')
raise SystemExit(pytest.main(sys.argv[1:]))
"""
PROFILE = 'python-authority-v1'


def runner_fingerprint():
    # Freeze actual collector/container implementation, not just a mutable profile label.
    return digest({name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                   for name in ('platform_test_collector.py', 'platform_container.py')})


def environment_fingerprint(image):
    return digest({'image': image, 'timeout_seconds': 120, 'runner_sha256': runner_fingerprint()})


def load_bundle(run_id):
    directory = artifacts.run_directory(run_id)
    manifest = artifacts.decode_json(artifacts.read_bytes(directory / 'manifest.json'))
    before = artifacts.inventory(directory / 'original')
    if artifacts.file_hashes(before) != manifest['files']:
        raise ValueError('Authority source changed')
    return directory, manifest, before


def create_bundle(request, *, workspace, case, rule, image, process_config=None):
    """Trusted preparation only, before enqueue. Partial failures are retained, not overwritten."""
    case = ExperimentCase.model_validate(case)
    rule = AcceptanceRule.model_validate(rule)
    if case.test_profile != 'python-basic':
        raise ValueError('Only fixed python-basic profile is implemented')
    if (digest(case.model_dump(mode='json')) != request.case_sha256
            or digest(rule.model_dump(mode='json')) != request.rule_sha256
            or environment_fingerprint(image) != request.environment_sha256
            or case.editable_files != request.editable_files
            or case.repository_commit != request.repository_commit
            or case.task_type != request.task_type or case.user_request != request.task_description
            or case.case_id != request.case_id or case.case_version != request.case_version):
        raise ValueError('Bundle differs from frozen request')
    before = artifacts.inventory(workspace, source_repository=True)
    artifacts.check_profile(before)
    if artifacts.python_hash(before) != request.initial_snapshot_hash:
        raise ValueError('Initial snapshot differs')
    if any(p not in before for p in case.protected_test_files):
        raise ValueError('Protected test source missing')
    modules = [p[:-3].replace('/', '.') for p in case.protected_test_files]
    if any(not any(t.classname == module or t.classname.startswith(module + '.') for module in modules)
           for t in rule.required_tests):
        raise ValueError('Required tests must belong to platform-protected modules')
    if request.task_type == 'bug_fix' and not rule.baseline_failure_tests:
        raise ValueError('Bug fix requires declared baseline failures')
    if any(Path(p).name in ('conftest.py', '__init__.py') for p in case.protected_test_files):
        raise ValueError('Only standalone test modules supported')
    if any(p not in before for p in case.editable_files):
        raise ValueError('First profile edits existing Python files only')
    directory = artifacts.run_directory(request.run_id)
    directory.mkdir(exist_ok=False)
    artifacts.copy_files(before, directory / 'original')
    # Native uses its registered independent repository. Process gets a separate no-.git copy.
    if request.agent.adapter == 'process':
        if process_config is None or digest(process_config) != request.config_sha256:
            raise ValueError('Process configuration mismatch')
        artifacts.copy_files(before, directory / 'workspace')
        for path in (directory / 'workspace').rglob('*'):
            path.chmod(0o777 if path.is_dir() else 0o666)
        (directory / 'workspace').chmod(0o777)
    authority = directory / 'authority'
    artifacts.copy_files({p: before[p] for p in case.protected_test_files}, authority)
    # Byte-stable across Windows/Linux; this exact configuration is hashed/checked.
    (authority / 'pytest.ini').write_bytes(b'[pytest]\n')
    artifacts.write_json(directory / 'manifest.json', dict(profile=PROFILE,
        request_sha256=digest(request.model_dump(mode='json')), files=artifacts.file_hashes(before),
        case=case.model_dump(mode='json'), rule=rule.model_dump(mode='json'),
        image=image, timeout_seconds=120, runner_sha256=runner_fingerprint(), process_config=process_config))
    return digest(artifacts.decode_json(artifacts.read_bytes(directory / 'manifest.json')))


def checked_bundle(request, state):
    directory, manifest, before = load_bundle(request.run_id)
    if (digest(manifest) != state['bundle_sha256'] or manifest['profile'] != PROFILE
            or manifest['runner_sha256'] != runner_fingerprint()
            or manifest['request_sha256'] != digest(request.model_dump(mode='json'))):
        raise ValueError('Frozen authority bundle changed')
    expected = {p: before[p] for p in manifest['case']['protected_test_files']}
    expected['pytest.ini'] = b'[pytest]\n'
    if artifacts.inventory(directory / 'authority') != dict(sorted(expected.items())):
        raise ValueError('Authority tests/config changed')
    return directory, manifest, before


def collect_test(request, state, *, phase, snapshot, snapshot_hash):
    from ..db.session import SessionLocal
    from ..db.models import TestRun
    directory, manifest, _ = checked_bundle(request, state)
    output = directory / f'{phase}-results'
    output.mkdir(exist_ok=False)
    output.chmod(0o777)
    test_id = uuid4()
    started = datetime.now(timezone.utc)
    with SessionLocal.begin() as session:
        session.add(TestRun(id=test_id, run_id=request.run_id, task_id=None,
            status='running', image=manifest['image'], timeout_seconds=120,
            started_at=started, snapshot_hash=snapshot_hash))
    result, error = None, None
    try:
        result = run_container(request.run_id, phase, image=manifest['image'],
            argv=['python', '-I', '-c', PYTEST_BOOTSTRAP, '-q', '--noconftest',
                  '-c', '/authority/pytest.ini', '--rootdir=/authority', '--import-mode=importlib',
                  '-p', 'no:cacheprovider', '--junitxml=/test-results/junit.xml',
                  '-o', 'junit_family=xunit2',
                  *['/authority/' + p for p in manifest['case']['protected_test_files']]],
            mounts=[(snapshot, '/workspace', True), (directory / 'authority', '/authority', True),
                    (output, '/test-results', False)], workdir='/authority', timeout_seconds=120)
    except Exception as exc:
        error = type(exc).__name__
        raise
    finally:
        # Unconfirmed containers never lead to reading possibly changing JUnit.
        report = read_test_report(output / 'junit.xml') if result else None
        if result and result['timed_out']:
            report = {**report, 'status': 'incomplete', 'counts': None}
        if report is not None:
            report = {**report, 'runner_sha256': manifest['runner_sha256']}
        with SessionLocal.begin() as session:
            row = session.get(TestRun, test_id)
            row.status = 'error' if error else 'finished'
            row.completed_at = datetime.now(timezone.utc)
            row.error = error
            row.test_report = report
            if result:
                for key in ('exit_code', 'timed_out', 'stdout', 'stderr', 'stdout_truncated', 'stderr_truncated'):
                    setattr(row, key, result[key])
    return TestEvidence(run_id=request.run_id, test_run_id=test_id, snapshot_hash=snapshot_hash,
        environment_sha256=request.environment_sha256, image=manifest['image'], timeout_seconds=120,
        runner_sha256=manifest['runner_sha256'],
        status='finished', exit_code=result['exit_code'], timed_out=result['timed_out'], test_report=report)


def prepare_baseline(request, state):
    from ..agent.adapters.base import StepResult
    directory, manifest, _ = checked_bundle(request, state)
    result = collect_test(request, state, phase='baseline', snapshot=directory / 'original',
                          snapshot_hash=request.initial_snapshot_hash)
    outcomes = test_outcomes(result.test_report)
    rule = AcceptanceRule.model_validate(manifest['rule'])
    required = {(t.classname, t.name) for t in rule.required_tests}
    failed = {(t.classname, t.name) for t in rule.baseline_failure_tests}
    valid = (not result.timed_out and outcomes is not None and required <= outcomes.keys()
             and all(v in ('passed', 'failed') for v in outcomes.values()))
    if request.task_type == 'bug_fix':
        valid = valid and result.exit_code == 1 and bool(failed) and all(outcomes.get(k) == 'failed' for k in failed)
    else:
        valid = valid and result.exit_code in (0, 1)
    state = {**state, 'baseline_test': result.model_dump(mode='json')}
    if not valid:
        return StepResult(state=state, execution_status='failed')
    return StepResult(state=state, next_stage='prepare')


def collect_final(request, state, execution_status):
    directory, manifest, before = checked_bundle(request, state)
    if request.agent.adapter == 'native':
        from ..db.session import SessionLocal
        from ..db.models import Repository
        from uuid import UUID
        with SessionLocal() as session:
            repository = session.get(Repository, UUID(state['repository_id']))
            workspace = Path(repository.workspace_path)
        after = artifacts.inventory(workspace, source_repository=True)
    else:
        after = artifacts.inventory(directory / 'workspace')
    comparison = artifacts.compare_files(before, after, request.editable_files, manifest['case']['protected_test_files'])
    artifacts.copy_files(after, directory / 'final')
    snapshot_hash = artifacts.python_hash(after)
    artifacts.write_json(directory / 'diff.json', comparison)
    final = None
    # Do not execute an unsupported or out-of-scope snapshot just to get a green test result.
    if comparison['diff_within_scope'] and comparison['protected_tests_intact']:
        artifacts.check_profile(after)
        final = collect_test(request, state, phase='final', snapshot=directory / 'final', snapshot_hash=snapshot_hash)
    evidence = EvaluationInput(run_id=request.run_id, execution_status=execution_status,
        case_id=request.case_id, case_version=request.case_version, case_sha256=request.case_sha256,
        task_type=request.task_type, rule=manifest['rule'], environment_sha256=request.environment_sha256,
        initial_snapshot_hash=request.initial_snapshot_hash, final_snapshot_hash=snapshot_hash,
        diff_sha256=comparison['diff_sha256'], writers_stopped=True,
        diff_within_scope=comparison['diff_within_scope'], protected_tests_intact=comparison['protected_tests_intact'],
        baseline_test=state.get('baseline_test'), final_test=final)
    return evidence
