"""Offline Day 3 boundary tests: no real DB, Docker, model, or secret configuration."""
from contextlib import nullcontext
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from backend.app.agent.adapters.base import StepResult, get_adapter
from backend.app.agent.adapters.process import ProcessAdapter, parse_result, read_trace
from backend.app.schemas.platform_run import AgentRunRequest
from backend.app.schemas.process_agent import ProcessConfiguration
from backend.app.schemas.experiment import ExperimentCase
from backend.app.schemas.experiment_definition import AcceptanceRule
from backend.app.services import platform_artifacts as artifacts, platform_container as containers
from backend.app.services import platform_test_collector as collector
from backend.app.services import run_worker_service as worker
from backend.app.services.experiment_contract_service import digest
from backend.app.services.platform_evaluation_service import evaluate_run
from backend.app.services.test_report_parser import parse_test_report

RID = UUID(int=33)
IMAGE = 'sha256:' + 'a' * 64
CONFIG = ProcessConfiguration(image=IMAGE, argv=['python', '-I', '/agent/demo.py', '--mode', 'noop'])
CASE = ExperimentCase(case_id='task-list', case_version='v1', task_type='bug_fix', user_request='fix',
    repository_commit='a'*40, editable_files=['task_list.py'], protected_test_files=['tests/test_task_list.py'],
    test_profile='python-basic')
RULE = AcceptanceRule(version='v1', required_tests=[{'classname': 'tests.test_task_list', 'name': 'test_fix'}],
                      baseline_failure_tests=[{'classname': 'tests.test_task_list', 'name': 'test_fix'}])
FILES = {'task_list.py': b'def value(): return 0\n',
         'tests/test_task_list.py': b'from task_list import value\ndef test_fix(): assert value() == 1\n'}


def request():
    return AgentRunRequest(run_id=RID, case_id=CASE.case_id, case_version=CASE.case_version,
        task_description='fix', repository_commit=CASE.repository_commit,
        agent={'name': 'fixture', 'version': 'v1', 'adapter': 'process', 'implementation_sha256': 'a'*64},
        config_sha256=digest(CONFIG.model_dump(mode='json')), case_sha256=digest(CASE.model_dump(mode='json')),
        task_type='bug_fix', rule_sha256=digest(RULE.model_dump(mode='json')),
        environment_sha256=collector.environment_fingerprint(IMAGE),
        initial_snapshot_hash=artifacts.python_hash(FILES), editable_files=['task_list.py'])


def xml(failed=False):
    child = '<failure/>' if failed else ''
    return (f'<testsuite tests="1" failures="{int(failed)}" errors="0" skipped="0">'
        f'<testcase classname="tests.test_task_list" name="test_fix">{child}</testcase></testsuite>').encode()


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root / 'run'
        self.source = self.root / 'source'
        artifacts.copy_files(FILES, self.source)
        self.patch = patch.object(artifacts, 'run_directory', return_value=self.directory)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        sha = collector.create_bundle(request(), workspace=self.source, case=CASE, rule=RULE, image=IMAGE,
                                      process_config=CONFIG.model_dump(mode='json'))
        self.state = {'bundle_sha256': sha}

    def test_snapshot_matches_legacy_python_hash(self):
        from backend.app.services.sandbox_snapshot_service import prepare_python_test_snapshot
        target = self.root / 'legacy'; target.mkdir()
        self.assertEqual(prepare_python_test_snapshot(self.source, target).snapshot_hash, request().initial_snapshot_hash)

    def test_authority_is_separate_and_tamper_rejected(self):
        (self.directory / 'workspace' / 'tests/test_task_list.py').write_text('fake', encoding='utf-8')
        _, _, original = collector.checked_bundle(request(), self.state)
        self.assertEqual(original, FILES)
        (self.directory / 'authority' / 'tests/test_task_list.py').write_text('fake', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Authority tests'):
            collector.checked_bundle(request(), self.state)

    def test_process_prepare_no_model_or_index_required(self):
        step = ProcessAdapter().prepare(request(), self.state)
        self.assertEqual(step.next_stage, 'process_run')
        value = json.loads((self.directory / 'input/request.json').read_text())
        self.assertEqual(value['run_id'], str(RID))
        self.assertNotIn('rule', value)
        self.assertFalse((self.directory / 'workspace/.git').exists())

    def fake_test(self, failed):
        return collector.TestEvidence(run_id=RID, test_run_id=UUID(int=12 if failed else 13),
            snapshot_hash=request().initial_snapshot_hash, environment_sha256=request().environment_sha256,
            image=IMAGE, timeout_seconds=120, status='finished', exit_code=1 if failed else 0,
            runner_sha256=collector.runner_fingerprint(),
            test_report={**parse_test_report(xml(failed)), 'runner_sha256': collector.runner_fingerprint()})

    def test_baseline_failure_required_before_agent(self):
        with patch.object(collector, 'collect_test', return_value=self.fake_test(False)):
            self.assertEqual(collector.prepare_baseline(request(), self.state).execution_status, 'failed')
        with patch.object(collector, 'collect_test', return_value=self.fake_test(True)):
            result = collector.prepare_baseline(request(), self.state)
            self.assertEqual(result.next_stage, 'prepare')
            self.assertEqual(result.state['baseline_test']['exit_code'], 1)

    def test_final_uses_platform_snapshot_and_passing_contract(self):
        (self.directory / 'workspace/task_list.py').write_text('def value(): return 1\n', encoding='utf-8')
        self.state['baseline_test'] = self.fake_test(True).model_dump(mode='json')
        def collect(req, state, **kwargs):
            self.assertEqual(kwargs['snapshot'], self.directory / 'final')
            self.assertEqual((kwargs['snapshot'] / 'task_list.py').read_text(), 'def value(): return 1\n')
            return self.fake_test(False).model_copy(update={'snapshot_hash': kwargs['snapshot_hash']})
        with patch.object(collector, 'collect_test', side_effect=collect):
            evidence = collector.collect_final(request(), self.state, 'completed')
        self.assertEqual(evaluate_run(evidence).outcome, 'passed')
        saved = artifacts.decode_json(artifacts.read_bytes(self.directory / 'diff.json'))
        self.assertEqual(saved['changed_files'], ['task_list.py'])

    def test_protected_tamper_not_executed_or_passed(self):
        (self.directory / 'workspace/tests/test_task_list.py').write_text('def test_fake(): pass\n', encoding='utf-8')
        with patch.object(collector, 'collect_test') as test:
            evidence = collector.collect_final(request(), self.state, 'completed')
        test.assert_not_called()
        self.assertEqual(evaluate_run(evidence).outcome, 'not_passed')

    def test_added_non_python_file_is_outside_scope(self):
        (self.directory / 'workspace/pytest.ini').write_text('[pytest]\n', encoding='utf-8')
        with patch.object(collector, 'collect_test') as test:
            evidence = collector.collect_final(request(), self.state, 'completed')
        test.assert_not_called()
        self.assertFalse(evidence.diff_within_scope)

    def test_collect_test_command_and_database_binding(self):
        session = MagicMock()
        row = NS()
        session.get.return_value = row
        sessions = MagicMock()
        sessions.begin.side_effect = lambda: nullcontext(session)
        def execute(run_id, phase, **kwargs):
            argv = kwargs['argv']
            self.assertEqual(argv[:3], ['python', '-I', '-c'])
            self.assertIn('--noconftest', argv)
            self.assertIn('--import-mode=importlib', argv)
            self.assertEqual(kwargs['workdir'], '/authority')
            self.assertTrue(kwargs['mounts'][0][2])
            self.assertTrue(kwargs['mounts'][1][2])
            self.assertEqual(kwargs['mounts'][1][0], self.directory / 'authority')
            (self.directory / 'baseline-results/junit.xml').write_bytes(xml(True))
            return dict(exit_code=1, timed_out=False, stdout='', stderr='',
                        stdout_truncated=False, stderr_truncated=False, writers_stopped=True)
        with patch('backend.app.db.session.SessionLocal', sessions), patch.object(collector, 'run_container', side_effect=execute):
            result = collector.collect_test(request(), self.state, phase='baseline',
                snapshot=self.directory / 'original', snapshot_hash=request().initial_snapshot_hash)
        self.assertEqual(result.run_id, RID)
        self.assertEqual(row.status, 'finished')
        self.assertEqual(row.test_report['counts']['failed'], 1)
        self.assertEqual(session.add.call_args.args[0].run_id, RID)
        self.assertIsNone(session.add.call_args.args[0].task_id)

    def test_real_local_pytest_ignores_workspace_config_and_environment(self):
        """Actual local pytest protocol check, not a Docker isolation claim."""
        import os
        import subprocess
        import sys
        workspace = self.directory / 'workspace'
        (workspace / 'task_list.py').write_bytes(b'def value(): return 1\n')
        (workspace / 'conftest.py').write_bytes(b'raise RuntimeError("must not load")\n')
        (workspace / 'pytest.ini').write_bytes(b'[pytest]\naddopts = --invalid-workspace-option\n')
        authority = self.directory / 'authority'
        output = self.root / 'local-junit.xml'
        script = collector.PYTEST_BOOTSTRAP.replace("'/workspace'", repr(str(workspace)))
        env = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP') if key in os.environ}
        env.update(PYTEST_ADDOPTS='--invalid-environment-option', PYTEST_PLUGINS='nonexistent_fixture_plugin')
        result = subprocess.run([sys.executable, '-I', '-c', script, '-q', '--noconftest',
            '-c', str(authority / 'pytest.ini'), '--rootdir=' + str(authority), '--import-mode=importlib',
            '-p', 'no:cacheprovider', '--junitxml=' + str(output), '-o', 'junit_family=xunit2',
            str(authority / 'tests/test_task_list.py')], cwd=authority, env=env,
            capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = collector.read_test_report(output)
        self.assertEqual(report['counts']['passed'], 1)
        self.assertIn(('tests.test_task_list', 'test_fix'), collector.test_outcomes(report))

    def test_runner_change_invalidates_bundle(self):
        with patch.object(collector, 'runner_fingerprint', return_value='f'*64):
            with self.assertRaisesRegex(ValueError, 'Frozen authority'):
                collector.checked_bundle(request(), self.state)

    def test_invalid_process_result_does_not_become_completed(self):
        adapter = ProcessAdapter()
        adapter.prepare(request(), self.state)
        (self.directory / 'output/result.json').write_text('{}', encoding='utf-8')
        with patch('backend.app.agent.adapters.process.run_container', return_value=dict(
                exit_code=0, timed_out=False, writers_stopped=True, stdout='', stderr='',
                stdout_truncated=False, stderr_truncated=False)):
            result = adapter.run(request(), 'process_run', self.state)
        self.assertEqual(result.execution_status, 'failed')
        self.assertEqual(result.state['process_execution']['protocol_error'], 'invalid_or_missing_result')


class ArtifactTests(unittest.TestCase):
    def test_json_bounds_and_duplicate_terminals(self):
        for raw in (b'{"a":1,"a":2}', b'['*25+b'0'+b']'*25, b'{"a":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): artifacts.decode_json(raw)
        self.assertEqual(artifacts.decode_json(b'{"text":"[escaped]"}'), {'text': '[escaped]'})

    def test_profile_rejects_config_plugins_and_secrets(self):
        for name in ('conftest.py', 'pytest.ini', 'pyproject.toml', '.env', 'tests/conftest.py', 'sitecustomize.py'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                artifacts.check_profile({**FILES, name: b'x'})

    def test_non_python_and_hidden_files_not_silently_discarded(self):
        diff = artifacts.compare_files(FILES, {**FILES, '.env': b'x'}, ['task_list.py'], CASE.protected_test_files)
        self.assertFalse(diff['diff_within_scope'])
        self.assertIn('.env', diff['changed_files'])

    def test_result_identity_nonzero_and_forbidden_success(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'result.json'
            result = dict(protocol_version=1, run_id=str(RID), agent=request().agent.model_dump(), execution_status='completed')
            path.write_text(json.dumps(result))
            self.assertEqual(parse_result(path, request(), 2)[1], 'failed')
            for extra in ({'run_id': str(UUID(int=99))}, {'success': True}, {'execution_status': 'cancelled'}, {'protocol_version': 2}):
                path.write_text(json.dumps({**result, **extra}))
                with self.assertRaises(ValueError): parse_result(path, request(), 0)

    def test_trace_missing_partial_conflicting_and_invalid(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'trace.jsonl'
            self.assertEqual(read_trace(path, request(), False)['status'], 'unsupported')
            self.assertEqual(read_trace(path, request(), True)['status'], 'missing')
            value = dict(event_id='one', run_id=str(RID), kind='model_call', call_id='call1',
                         input_tokens=2, output_tokens=3, total_tokens=5)
            path.write_text(json.dumps(value)+'\n'+json.dumps(value))
            report = read_trace(path, request(), True)
            self.assertEqual((report['status'], len(report['events'])), ('partial', 1))
            path.write_text(json.dumps(value)+'\n'+json.dumps({**value, 'total_tokens': 6}))
            self.assertEqual(read_trace(path, request(), True)['status'], 'invalid')


class ContainerTests(unittest.TestCase):
    def test_unavailable_daemon_is_not_stopped_proof(self):
        with patch.object(containers, 'docker', return_value=NS(returncode=1)):
            with self.assertRaises(containers.ContainerUnconfirmed): containers.inspect_container('fixture')

    def test_never_removes_someone_elses_container(self):
        with patch.object(containers, 'inspect_container', return_value={'Config': {'Labels': {}}}), \
                patch.object(containers, 'docker') as command:
            with self.assertRaises(containers.ContainerUnconfirmed): containers.remove_owned(RID, 'agent')
        command.assert_not_called()

    def test_container_limits_mounts_and_stopped_confirmation(self):
        process = MagicMock()
        process.stdout = StringIO('fixture stdout'); process.stderr = StringIO('')
        process.poll.return_value = 0
        exited = {'State': {'Running': False, 'Status': 'exited', 'ExitCode': 0}}
        with TemporaryDirectory() as tmp, \
                patch.object(containers, 'inspect_container', side_effect=[None, exited]), \
                patch.object(containers, 'remove_owned') as cleanup, \
                patch.object(containers, 'docker', return_value=NS(returncode=0, stdout=IMAGE)) as docker, \
                patch.object(containers.subprocess, 'Popen', return_value=process):
            result = containers.run_container(RID, 'agent', image=IMAGE, argv=['python', '/demo.py'],
                mounts=[(Path(tmp), '/workspace', False)], workdir='/workspace', timeout_seconds=2)
        args = docker.call_args.args
        for flag in ('--pull=never', '--network', '--read-only', '--cap-drop', '--user', '--pids-limit', '--log-driver'):
            self.assertIn(flag, args)
        self.assertIn('none', args)
        self.assertTrue(result['writers_stopped'])
        cleanup.assert_called_once_with(RID, 'agent')

    def test_timeout_removes_container_before_result(self):
        import subprocess
        process = MagicMock(); process.stdout = StringIO(''); process.stderr = StringIO('')
        process.wait.side_effect = [subprocess.TimeoutExpired('docker', 1), 0]
        process.poll.return_value = None
        with patch.object(containers, 'inspect_container', return_value=None), \
                patch.object(containers, 'remove_owned') as cleanup, \
                patch.object(containers, 'docker', return_value=NS(returncode=0, stdout=IMAGE)), \
                patch.object(containers.subprocess, 'Popen', return_value=process):
            result = containers.run_container(RID, 'agent', image=IMAGE, argv=['python'], mounts=[],
                                              workdir='/workspace', timeout_seconds=1)
        self.assertTrue(result['timed_out']); self.assertIsNone(result['exit_code'])
        cleanup.assert_called_once(); process.kill.assert_called_once()


class SchedulingTests(unittest.TestCase):
    def test_process_registry_is_independent(self):
        self.assertIsInstance(get_adapter('process'), ProcessAdapter)

    def test_prior_agent_cancel_does_not_kill_platform_evaluation(self):
        from backend.app.services import platform_worker
        child = MagicMock()
        child.pid = 42
        child.is_alive.side_effect = [True, True, False, False, False, False]
        claim = {'run_id': RID, 'token': UUID(int=7), 'stage': 'evaluate', 'remaining_seconds': 240}
        with patch.object(platform_worker.store, 'is_cancelled') as cancelled, \
                patch.object(platform_worker.store, 'settle_step') as settle:
            platform_worker.supervise(claim, process_factory=MagicMock(return_value=child))
        cancelled.assert_not_called()
        child.terminate.assert_not_called()
        self.assertIsNone(settle.call_args.kwargs['forced_reason'])

    def test_completed_process_schedules_evaluation_not_false_pass(self):
        from tests.test_platform_day2 import rows
        run, work = rows()
        work.stage = 'process_run'
        work.result = {'step': StepResult(state={'bundle_sha256': 'a'*64}, execution_status='completed').model_dump(),
                       'cleanup': {'status': 'confirmed'}}
        session = MagicMock(); session.get.return_value = work
        with patch.object(worker.SessionLocal, 'begin', return_value=nullcontext(session)), \
                patch.object(worker.repo, 'get_run', return_value=run), \
                patch.object(worker, 'import_native_events'), patch.object(worker.repo, 'append_event'):
            worker.settle_step(run.id, work.active_token, elapsed=1)
        self.assertEqual((run.lifecycle, run.evaluation_outcome, work.stage, work.ready),
                         ('evaluating', 'pending', 'evaluate', True))

    def test_evaluation_terminal_saved_in_same_transaction(self):
        from tests.test_platform_day1 import evidence
        from tests.test_platform_day2 import rows
        from backend.app.services import platform_run_service
        run, work = rows('evaluating')
        run.execution_status = 'completed'
        work.stage = 'evaluate'
        work.result = {'evaluation': evidence().model_dump(mode='json'), 'cleanup': {'status': 'not_needed'}}
        session = MagicMock(); session.get.return_value = work
        with patch.object(worker.SessionLocal, 'begin', return_value=nullcontext(session)), \
                patch.object(worker.repo, 'get_run', return_value=run), \
                patch.object(worker, 'import_native_events'), patch.object(worker.repo, 'append_event', return_value=NS(sequence=4)), \
                patch.object(platform_run_service, 'finish_evaluation') as finish:
            worker.settle_step(run.id, work.active_token, elapsed=4)
        self.assertIs(finish.call_args.kwargs['_session'], session)
        self.assertFalse(work.ready)
        self.assertIsNone(work.active_token)


if __name__ == '__main__':
    unittest.main()
