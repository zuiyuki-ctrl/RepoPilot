"""v2 Day 1：纯协议/规则、模拟事务与 API、离线 PostgreSQL 迁移。"""
from contextlib import nullcontext
from datetime import datetime, timezone
from io import StringIO
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from alembic.migration import MigrationContext
from alembic.operations import Operations

from backend.app.schemas.platform_run import AgentRunRequest, AgentRunResult
from backend.app.schemas.platform_evaluation import EvaluationInput
from backend.app.services.platform_evaluation_service import evaluate_run
from backend.app.services.run_observation_service import summarize_observation, FIELDS
from backend.app.services.run_lifecycle import transition, RunConflictError
from backend.app.services.experiment_contract_service import digest
from backend.app.services.test_report_parser import parse_test_report
from backend.app.services import platform_run_service as service
from backend.app.api.routes import platform_runs
from backend.app.db.models import PlatformRun, PlatformRunEvent, TestRun, RunEvaluation

RUN_ID = UUID(int=1)
ENV = digest({'image': 'sha256:offline', 'timeout_seconds': 120})


def report(failure=False):
    child = '<failure message="synthetic"/>' if failure else ''
    return parse_test_report((f'<testsuite tests="1" failures="{int(failure)}" errors="0" skipped="0">'
        f'<testcase classname="tests.test_demo" name="test_fix">{child}</testcase></testsuite>').encode())


def evidence():
    test = dict(run_id=RUN_ID, test_run_id=UUID(int=10), snapshot_hash='b'*64,
        environment_sha256=ENV, image='sha256:offline', timeout_seconds=120,
        status='finished', exit_code=0, test_report=report())
    return EvaluationInput(run_id=RUN_ID, execution_status='completed', case_id='synthetic', case_version='v1',
        case_sha256='c'*64, task_type='bug_fix',
        rule={'version': 'v1', 'required_tests': [{'classname': 'tests.test_demo', 'name': 'test_fix'}],
              'baseline_failure_tests': [{'classname': 'tests.test_demo', 'name': 'test_fix'}]},
        environment_sha256=ENV, initial_snapshot_hash='a'*64, final_snapshot_hash='b'*64,
        diff_sha256='d'*64, writers_stopped=True, diff_within_scope=True, protected_tests_intact=True,
        final_test=test, baseline_test={**test, 'test_run_id': UUID(int=11), 'snapshot_hash': 'a'*64,
                                        'exit_code': 1, 'test_report': report(True)})


def request():
    value = evidence()
    return AgentRunRequest(run_id=RUN_ID, case_id=value.case_id, case_version=value.case_version,
        task_description='Synthetic offline task', repository_commit='a'*40,
        agent={'name': 'demo', 'version': 'v1', 'adapter': 'process', 'implementation_sha256': 'f'*64},
        config_sha256='e'*64, case_sha256=value.case_sha256, task_type=value.task_type,
        rule_sha256=digest(value.rule.model_dump(mode='json')), environment_sha256=ENV,
        initial_snapshot_hash=value.initial_snapshot_hash, editable_files=['demo.py'])


def row(lifecycle='queued'):
    return SimpleNamespace(id=RUN_ID, repository_id=UUID(int=2), legacy_task_id=None,
        request=request().model_dump(mode='json'), lifecycle=lifecycle, execution_status='pending',
        evaluation_outcome='pending', version=1, event_sequence=1, capabilities={},
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc) if lifecycle in ('running', 'awaiting_input', 'evaluating') else None,
        completed_at=None)


class EvaluationTests(unittest.TestCase):
    def test_independent_success_without_plan_or_retrieval(self):
        self.assertEqual(evaluate_run(evidence()).outcome, 'passed')

    def test_completed_is_not_passed(self):
        data = evidence()
        data.final_test.exit_code = 1
        data.final_test.test_report = report(True)
        self.assertEqual(evaluate_run(data).outcome, 'not_passed')

    def test_execution_failures_override_passing_tests(self):
        for status in ('failed', 'timed_out', 'cancelled'):
            with self.subTest(status=status):
                self.assertEqual(evaluate_run(evidence().model_copy(update={'execution_status': status})).outcome, 'not_passed')

    def test_missing_or_changed_evidence_never_passes(self):
        for changes in ({'writers_stopped': None}, {'final_snapshot_hash': None}, {'diff_sha256': None},
                        {'protected_tests_intact': None}, {'baseline_test': None}, {'final_test': None},
                        {'execution_status': 'unknown'}, {'diff_within_scope': False}):
            with self.subTest(changes=changes):
                self.assertNotEqual(evaluate_run(evidence().model_copy(update=changes)).outcome, 'passed')
        for field, value in (('run_id', UUID(int=99)), ('snapshot_hash', 'f'*64),
                             ('environment_sha256', 'f'*64), ('image', 'other'), ('status', 'running')):
            with self.subTest(field=field):
                data = evidence(); setattr(data.final_test, field, value)
                self.assertEqual(evaluate_run(data).outcome, 'unknown')

    def test_forged_report_missing_test_and_manual_rule(self):
        for variant in ('count', 'missing', 'manual', 'baseline'):
            with self.subTest(variant=variant):
                data = evidence()
                if variant == 'count': data.final_test.test_report['counts']['passed'] = 99
                if variant == 'missing':
                    data.rule.required_tests.append(data.rule.required_tests[0].model_copy(update={'name': 'missing'}))
                if variant == 'manual': data.rule.manual_criteria = ['human check']
                if variant == 'baseline': data.baseline_test.test_report = report()
                self.assertEqual(evaluate_run(data).outcome, 'unknown')

    def test_agent_result_cannot_report_evaluation(self):
        payload = dict(run_id=RUN_ID, agent=request().agent, execution_status='completed', success=True)
        with self.assertRaises(ValidationError): AgentRunResult(**payload)

    def test_request_rejects_unsafe_edit_scope(self):
        for path in ('../outside.py', '/absolute.py', 'D:/host.py', 'a\\b.py', 'a//b.py'):
            with self.subTest(path=path), self.assertRaises(ValidationError):
                AgentRunRequest.model_validate({**request().model_dump(), 'editable_files': [path]})


class ObservationTests(unittest.TestCase):
    def available(self):
        return dict(declared=True, validated=True, availability='available', occurrence='occurred',
                    source='platform', evidence_sequences=[1], expected_records=1, recorded_records=1)

    def test_declaration_alone_never_upgrades(self):
        value = summarize_observation({k: {'declared': True, 'validated': True} for k in FIELDS})
        self.assertEqual(value.level, 'unknown')

    def test_layers_and_missing_count(self):
        fields = {k: self.available() for k in FIELDS[:3]}
        self.assertEqual(summarize_observation(fields).level, 'L0')
        fields.update({k: self.available() for k in FIELDS[3:5]})
        self.assertEqual(summarize_observation(fields).level, 'L1')
        fields.update({k: self.available() for k in FIELDS[5:]})
        self.assertEqual(summarize_observation(fields).level, 'L2')
        fields['model_usage']['expected_records'] = None
        self.assertEqual(summarize_observation(fields).level, 'L0')
        self.assertEqual(summarize_observation(fields).completeness, 'partial')

    def test_not_occurred_requires_explicit_reference(self):
        fields = {k: self.available() for k in FIELDS}
        fields['reflection'].update(occurrence='not_occurred', recorded_records=0, expected_records=0)
        self.assertEqual(summarize_observation(fields).level, 'L2')
        fields['reflection']['evidence_sequences'] = []
        with self.assertRaises(ValidationError): summarize_observation(fields)


class LifecycleTests(unittest.TestCase):
    def test_pause_and_stale_resume(self):
        run = row()
        transition(run, expected_version=1, target='preparing')
        transition(run, expected_version=2, target='running')
        started = run.started_at
        transition(run, expected_version=3, target='awaiting_input')
        with self.assertRaises(RunConflictError): transition(run, expected_version=3, target='running')
        transition(run, expected_version=4, target='running')
        self.assertEqual(run.started_at, started)
        with self.assertRaises(RunConflictError): transition(run, expected_version=5, target='finished')

    def test_interruption_and_prestart_cancellation(self):
        with self.assertRaises(RunConflictError):
            transition(row('preparing'), expected_version=1, target='evaluating', execution_status='completed')
        run = row('running')
        transition(run, expected_version=1, target='interrupted')
        self.assertEqual((run.execution_status, run.evaluation_outcome), ('unknown', 'unknown'))
        run = row()
        transition(run, expected_version=1, target='finished', execution_status='cancelled')
        self.assertIsNone(run.started_at)
        self.assertIsNotNone(run.completed_at)


class StorageTests(unittest.TestCase):
    def test_create_key_replay_and_conflict(self):
        req = request(); run = row(); repository_id = run.repository_id
        run.request_sha256 = digest(dict(request=req.model_dump(mode='json'),
                                        repository_id=str(repository_id), legacy_task_id=None))
        session = MagicMock()
        session.get.return_value = SimpleNamespace(commit_hash=req.repository_commit)
        with patch.object(service.SessionLocal, 'begin', return_value=nullcontext(session)), \
             patch.object(service.repo, 'append_event') as append:
            session.scalar.side_effect = [None, run]
            result = service.create_run(req, repository_id=repository_id, creation_key='same')
            self.assertEqual(result.id, RUN_ID)
            append.assert_not_called()
            session.scalar.side_effect = [None, run]
            with self.assertRaises(RunConflictError):
                service.create_run(req.model_copy(update={'config_sha256': '9'*64}),
                    repository_id=repository_id, creation_key='same')
            append.assert_not_called()

    def test_missing_capability_reference_rejected(self):
        session = MagicMock(); session.scalars.return_value = []
        value = ObservationTests().available()
        with patch.object(service.SessionLocal, 'begin', return_value=nullcontext(session)), \
             patch.object(service.repo, 'get_run', return_value=row('running')):
            with self.assertRaises(RunConflictError):
                service.record_capabilities(RUN_ID, expected_version=1, capabilities={'execution': value})

    def test_models_compile_and_test_owner_is_exclusive(self):
        for model in (PlatformRun, PlatformRunEvent, TestRun, RunEvaluation):
            self.assertIn('CREATE TABLE', str(CreateTable(model.__table__).compile(dialect=postgresql.dialect())))
        self.assertTrue(TestRun.__table__.c.task_id.nullable)
        self.assertTrue(TestRun.__table__.c.run_id.nullable)
        self.assertIn('ck_test_runs_single_owner', {c.name for c in TestRun.__table__.constraints})

    def test_migration_sql_is_additive_and_downgrade_guards_data(self):
        path = Path('backend/migrations/versions/d714a01b0001_add_platform_runs.py')
        spec = importlib.util.spec_from_file_location('day1_migration', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        output = StringIO()
        context = MigrationContext.configure(dialect_name='postgresql', opts={'as_sql': True, 'output_buffer': output})
        with Operations.context(context): module.upgrade()
        sql = output.getvalue()
        self.assertIn('CREATE TABLE platform_runs', sql)
        self.assertIn('task_id DROP NOT NULL', sql)
        self.assertNotIn('DELETE FROM', sql)
        output.seek(0); output.truncate()
        with Operations.context(context): module.downgrade()
        self.assertLess(output.getvalue().index('RAISE EXCEPTION'), output.getvalue().index('DROP TABLE'))

    def test_service_rejects_foreign_test_and_rule_drift(self):
        for variant in ('foreign_test', 'rule'):
            with self.subTest(variant=variant):
                run = row('evaluating'); run.execution_status = 'completed'
                data = evidence()
                if variant == 'rule': data.rule.version = 'changed'
                session = MagicMock(); session.scalar.return_value = None
                session.get.return_value = SimpleNamespace(run_id=UUID(int=99))
                with patch.object(service.SessionLocal, 'begin', return_value=nullcontext(session)), \
                     patch.object(service.repo, 'get_run', return_value=run):
                    with self.assertRaises(RunConflictError): service.finish_evaluation(data, expected_version=1)
                    session.add.assert_not_called()

    def test_finish_persists_terminal_evaluation_and_event_together(self):
        run = row('evaluating'); run.execution_status = 'completed'
        data = evidence(); session = MagicMock(); session.scalar.return_value = None
        session.get.side_effect = [SimpleNamespace(**t.model_dump()) for t in (data.baseline_test, data.final_test)]
        with patch.object(service.SessionLocal, 'begin', return_value=nullcontext(session)), \
             patch.object(service.repo, 'get_run', return_value=run), patch.object(service.repo, 'append_event') as append:
            result = service.finish_evaluation(data, expected_version=1)
            self.assertEqual((result.lifecycle, result.evaluation_outcome), ('finished', 'passed'))
            self.assertIsInstance(session.add.call_args.args[0], RunEvaluation)
            append.assert_called_once()


class ApiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI(); app.include_router(platform_runs.router)
        self.client = TestClient(app)

    def tearDown(self): self.client.close()

    def test_empty_not_found_and_pagination(self):
        with patch.object(service, 'list_runs', return_value=[]):
            self.assertEqual(self.client.get('/api/v2/runs').json(), {'source': 'live', 'items': []})
        with patch.object(service, 'get_run', return_value=None):
            self.assertEqual(self.client.get(f'/api/v2/runs/{RUN_ID}').status_code, 404)
        self.assertEqual(self.client.get('/api/v2/runs?limit=0').status_code, 422)
        with patch.object(service, 'list_events', return_value=[]):
            self.assertEqual(self.client.get(f'/api/v2/runs/{RUN_ID}/events?after_sequence=5').json()['next_after_sequence'], 5)

    def test_database_error_is_503_and_no_private_request_leaks(self):
        with patch.object(service, 'list_runs', side_effect=SQLAlchemyError('synthetic')):
            response = self.client.get('/api/v2/runs')
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('synthetic', response.text)
        with patch.object(service, 'get_run', return_value=service.as_read(row())):
            payload = self.client.get(f'/api/v2/runs/{RUN_ID}').json()
            self.assertNotIn('request', payload)
            self.assertNotIn('task_description', payload)


if __name__ == '__main__': unittest.main()
