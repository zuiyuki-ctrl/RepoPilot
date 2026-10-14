"""Day 2: simulated storage/model/worker, no paid requests."""
from contextlib import nullcontext
from datetime import datetime, timezone
from io import StringIO
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID
from fastapi import FastAPI
from fastapi.testclient import TestClient
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from backend.app.agent.adapters.native import NativeAdapter
from backend.app.agent.adapters import native
from backend.app.agent.adapters.base import StepResult
from backend.app.api.routes import platform_runs
from backend.app.api.native_task_guard import guard_native_task
from backend.app.db.models import RunWork, RunCheckpoint
from backend.app.schemas.platform_run import AgentRunRequest
from backend.app.schemas.run_control import ApprovalRequest, CancelRequest
from backend.app.schemas.run_config import AgentRunConfig
from backend.app.schemas.edit import TaskFileEditRead
from backend.app.schemas.task import TaskPlanResult
from backend.app.services import run_control_service as control, run_worker_service as worker, platform_worker
from backend.app.services.experiment_contract_service import digest
from backend.app.services.run_lifecycle import RunConflictError

RID, TID, REPO, TOKEN, CPID = [UUID(int=i) for i in range(1, 6)]


def request():
    return AgentRunRequest(run_id=RID, case_id='fixture', case_version='v1', task_description='fix demo',
        repository_commit='a'*40, agent={'name': 'Native', 'version': 'v2', 'adapter': 'native',
        'implementation_sha256': 'b'*64}, config_sha256=digest(AgentRunConfig().model_dump(mode='json')),
        case_sha256='c'*64, task_type='bug_fix', rule_sha256='d'*64, environment_sha256='e'*64,
        initial_snapshot_hash='f'*64, editable_files=['demo.py'], budget={'max_tool_calls': 4})


def rows(lifecycle='running'):
    run = NS(id=RID, legacy_task_id=TID, repository_id=REPO, request=request().model_dump(mode='json'),
        lifecycle=lifecycle, execution_status='pending', evaluation_outcome='pending', version=3,
        event_sequence=1, capabilities={}, started_at=datetime.now(timezone.utc), completed_at=None)
    work = NS(run_id=RID, active_token=TOKEN, active_since=datetime.now(timezone.utc),
        ready=False, cancel_requested=False, stage='plan', state={}, result=None,
        active_seconds=0, cleanup_status='not_needed', error_code=None, legacy_cursor=0)
    return run, work


def checkpoint():
    return NS(id=CPID, run_id=RID, kind='plan', run_version=3, payload={'plan': 'fixture'},
        payload_sha256='a'*64, decision=None, comment=None, decided_at=None)


def decision():
    return ApprovalRequest(expected_version=3, payload_sha256='a'*64, decision='approved', comment='checked')


class NativeTests(unittest.TestCase):
    def task(self):
        return NS(id=TID, repository_id=REPO, run_config=AgentRunConfig(), status='created',
                  task_type='plan', user_request='fix demo')

    def test_complete_flow_preserves_exact_approved_content(self):
        adapter = NativeAdapter(); task = self.task()
        planned = NS(status='awaiting_review', result=TaskPlanResult(repository_id=REPO, plan={
            'summary': 'fix', 'steps': [{'id': 1, 'description': 'fix', 'files': ['demo.py'],
                                       'source_ids': ['S1'], 'verification': 'run tests'}]}))
        candidate = TaskFileEditRead(task_id=TID, repository_id=REPO, base_file_hash='a'*64,
            proposal={'file_path': 'demo.py', 'summary': 'fix', 'content': 'answer = 42\n'})
        state = {'task_id': str(TID), 'repository_id': str(REPO)}
        with patch.object(adapter, '_task', return_value=task), \
                patch.object(native.task_service, 'run_task', return_value=planned) as plan, \
                patch.object(native.task_service, 'review_task_plan') as review, \
                patch.object(native.task_service, 'begin_plan_execution') as begin, \
                patch.object(native.edit_proposal_service, 'generate_task_file_edit', return_value=candidate) as generate, \
                patch.object(native.plan_execution_service, 'apply_task_file_edit', return_value=NS()) as apply:
            step = adapter.run(request(), 'plan', state)
            self.assertEqual(step.checkpoint_kind, 'plan'); apply.assert_not_called()
            step.state['approval'] = {'decision': 'approved', 'comment': 'ok'}
            step = adapter.run(request(), 'review_plan', step.state)
            step = adapter.run(request(), step.next_stage, step.state)
            step = adapter.run(request(), step.next_stage, step.state)
            self.assertEqual(step.checkpoint_kind, 'candidate'); apply.assert_not_called()
            step.state['approval'] = {'decision': 'approved', 'comment': 'ok'}
            final = adapter.run(request(), step.next_stage, step.state)
            self.assertEqual(final.execution_status, 'completed')
            self.assertNotIn('passed', final.model_dump())
            self.assertEqual(apply.call_args.kwargs['proposal'].content, 'answer = 42\n')
            self.assertEqual(apply.call_args.kwargs['base_file_hash'], 'a'*64)
            for mock in (plan, review, begin, generate, apply): self.assertEqual(mock.call_count, 1)

    def test_rejected_candidate_never_writes(self):
        adapter = NativeAdapter()
        with patch.object(adapter, '_task', return_value=self.task()), \
                patch.object(native.plan_execution_service, 'apply_task_file_edit') as apply:
            result = adapter.run(request(), 'apply', {'approval': {'decision': 'rejected'}})
            self.assertEqual(result.execution_status, 'cancelled'); apply.assert_not_called()

    def test_runtime_or_config_drift_rejected_before_model(self):
        adapter, task = NativeAdapter(), self.task()
        with patch.object(native.task_service, 'get_task', return_value=task), \
                patch.object(adapter, 'metadata', return_value={'implementation_sha256': 'x'*64}):
            with self.assertRaisesRegex(ValueError, 'runtime'):
                adapter._task(request(), {'task_id': str(TID), 'repository_id': str(REPO)})
        task.run_config = AgentRunConfig(max_tool_calls=3)
        with patch.object(native.task_service, 'get_task', return_value=task):
            with self.assertRaisesRegex(ValueError, 'configuration'):
                adapter._task(request(), {'task_id': str(TID), 'repository_id': str(REPO)})

    def test_prepare_checks_snapshot_before_planning(self):
        adapter = NativeAdapter(); task = self.task()
        session = MagicMock(); session.get.return_value = NS(commit_hash='a'*40, workspace_path='fixture')
        with patch.object(adapter, '_task', return_value=task), \
                patch.object(native, 'SessionLocal', return_value=nullcontext(session)), \
                patch.object(native, 'TemporaryDirectory', return_value=nullcontext('fixture-temp')), \
                patch.object(native, 'prepare_python_test_snapshot', return_value=NS(snapshot_hash='f'*64)) as snapshot:
            self.assertEqual(adapter.prepare(request(), {}).next_stage, 'plan')
            snapshot.return_value.snapshot_hash = 'changed'
            with self.assertRaisesRegex(ValueError, 'snapshot'): adapter.prepare(request(), {})


class ControlTests(unittest.TestCase):
    def context(self, work, cp):
        session = MagicMock()
        session.get.side_effect = lambda model, key: cp if model is RunCheckpoint else work
        return session

    def test_duplicate_approval_does_not_repeat_event_or_resume_twice(self):
        run, work = rows('awaiting_input'); work.active_token = None
        cp = checkpoint(); session = self.context(work, cp)
        with patch.object(control.SessionLocal, 'begin', return_value=nullcontext(session)), \
                patch.object(control.repo, 'get_run', return_value=run), patch.object(control.repo, 'append_event') as emit:
            first = control.decide_checkpoint(RID, CPID, decision())
            second = control.decide_checkpoint(RID, CPID, decision())
            self.assertEqual(first, second); self.assertEqual(run.version, 4)
            self.assertEqual(emit.call_count, 1); self.assertTrue(work.ready)
            self.assertEqual(run.lifecycle, 'awaiting_input')

    def test_stale_or_changed_approval_is_conflict(self):
        for field, value in [('expected_version', 2), ('payload_sha256', 'b'*64), ('decision', 'rejected')]:
            run, work = rows('awaiting_input'); work.active_token = None
            cp = checkpoint(); cp.decision = 'approved'; cp.comment = 'checked'
            session = self.context(work, cp)
            data = decision().model_copy(update={field: value})
            with self.subTest(field=field), patch.object(control.SessionLocal, 'begin', return_value=nullcontext(session)), \
                    patch.object(control.repo, 'get_run', return_value=run):
                with self.assertRaises(RunConflictError): control.decide_checkpoint(RID, CPID, data)

    def test_cancel_idempotent_and_prevents_pending_approval(self):
        run, work = rows('awaiting_input'); work.active_token = None
        cp = checkpoint(); session = self.context(work, cp)
        with patch.object(control.SessionLocal, 'begin', return_value=nullcontext(session)), \
                patch.object(control.repo, 'get_run', return_value=run), patch.object(control.repo, 'append_event') as emit:
            data = CancelRequest(expected_version=3)
            control.request_cancel(RID, data); control.request_cancel(RID, data)
            self.assertEqual(emit.call_count, 1)
            with self.assertRaises(RunConflictError): control.decide_checkpoint(RID, CPID, decision())


class WorkerTests(unittest.TestCase):
    def settle(self, run, work, **kwargs):
        session = MagicMock(); session.get.return_value = work
        with patch.object(worker.SessionLocal, 'begin', return_value=nullcontext(session)), \
                patch.object(worker.repo, 'get_run', return_value=run), \
                patch.object(worker, 'import_native_events'), patch.object(worker.repo, 'append_event'):
            worker.settle_step(RID, TOKEN, elapsed=2, **kwargs)
        return session

    def test_completed_step_waits_for_independent_evaluation(self):
        run, work = rows()
        work.result = {'step': StepResult(execution_status='completed').model_dump(), 'cleanup': {'status': 'not_needed'}}
        self.settle(run, work)
        self.assertEqual((run.lifecycle, run.execution_status, run.evaluation_outcome), ('evaluating', 'completed', 'pending'))
        self.assertIsNone(work.active_token)

    def test_checkpoint_persisted_and_slot_released(self):
        run, work = rows()
        work.result = {'step': StepResult(state={'files': ['demo.py']}, next_stage='review_plan',
            checkpoint_kind='plan', checkpoint_payload={'summary': 'fixture'}).model_dump(), 'cleanup': {'status': 'not_needed'}}
        session = self.settle(run, work); cp = session.add.call_args.args[0]
        self.assertEqual(cp.payload_sha256, digest({'summary': 'fixture'}))
        self.assertEqual(cp.run_version, run.version); self.assertEqual(run.lifecycle, 'awaiting_input')
        self.assertFalse(work.ready); self.assertIsNone(work.active_token)

    def test_cleanup_failure_keeps_ownership_fence(self):
        run, work = rows()
        work.result = {'error_code': 'ValueError', 'cleanup': {'status': 'failed', 'error_code': 'OSError'}}
        self.settle(run, work)
        self.assertEqual(run.lifecycle, 'interrupted')
        self.assertEqual(work.active_token, TOKEN)
        self.assertEqual(work.error_code, 'ValueError')

    def test_recovery_stops_without_replaying_saved_result(self):
        run, work = rows()
        work.result = {'step': {'state': {}, 'next_stage': 'apply'}}
        session = MagicMock(); session.get.return_value = work
        with patch.object(worker.SessionLocal, 'begin', return_value=nullcontext(session)), \
                patch.object(worker.repo, 'get_run', return_value=run), patch.object(worker, 'import_native_events'), \
                patch.object(worker.repo, 'append_event'):
            worker.recover_interrupted(RID, TOKEN)
        self.assertEqual(run.lifecycle, 'interrupted')
        self.assertIsNone(work.active_token); self.assertFalse(work.ready)
        self.assertEqual(work.cleanup_status, 'operator_confirmed')

    def test_crash_or_forced_stop_retains_global_fence(self):
        for reason in (None, 'cancelled_during_step', 'active_time_budget_exceeded'):
            run, work = rows(); self.settle(run, work, forced_reason=reason)
            self.assertEqual((run.lifecycle, run.execution_status), ('interrupted', 'unknown'))
            self.assertEqual(work.cleanup_status, 'unverified'); self.assertEqual(work.active_token, TOKEN)

    def test_unsettled_step_blocks_all_new_claims(self):
        session = MagicMock(); session.scalar.return_value = RID
        with patch.object(worker.SessionLocal, 'begin', return_value=nullcontext(session)):
            with self.assertRaisesRegex(RunConflictError, 'Unsettled'): worker.claim_next(allow_model=True)
        self.assertEqual(session.scalar.call_count, 1)

    def test_failure_and_cleanup_are_separate(self):
        claim = {'request': request().model_dump(mode='json'), 'stage': 'plan', 'state': {}, 'run_id': RID, 'token': TOKEN}
        adapter = MagicMock(); adapter.run.side_effect = ValueError('synthetic'); adapter.cleanup.side_effect = RuntimeError('synthetic cleanup')
        with patch.object(platform_worker, 'get_adapter', return_value=adapter), patch.object(platform_worker.store, 'save_step_result') as save:
            platform_worker.execute_step(claim)
        stored = save.call_args.args[2]
        self.assertEqual(stored['error_code'], 'ValueError')
        self.assertEqual(stored['cleanup'], {'status': 'failed', 'error_code': 'RuntimeError'})

    def test_native_event_cursor_prevents_duplicate_import(self):
        run, work = rows()
        events = [NS(sequence=7, event_type='RETRIEVAL_COMPLETED', node_name='tools', payload={'call_id': 'one', 'hits': []})]
        session = MagicMock(); session.scalars.side_effect = [events, []]
        def emit(session, run, **kwargs):
            run.event_sequence += 1
            return NS(sequence=run.event_sequence)
        with patch.object(worker.repo, 'append_event', side_effect=emit) as append:
            worker.import_native_events(session, run, work); worker.import_native_events(session, run, work)
        self.assertEqual(append.call_count, 1); self.assertEqual(work.legacy_cursor, 7)
        self.assertEqual(append.call_args.kwargs['payload']['legacy_sequence'], 7)
        self.assertIsNone(run.capabilities['retrieval']['expected_records'])

    def test_exhausted_budget_never_starts_child(self):
        claim = {'remaining_seconds': 0, 'run_id': RID, 'token': TOKEN}
        child = MagicMock(); child.pid = None
        with patch.object(platform_worker.store, 'settle_step') as settle:
            platform_worker.supervise(claim, process_factory=MagicMock(return_value=child))
        child.start.assert_not_called()
        self.assertEqual(settle.call_args.kwargs['forced_reason'], 'active_time_budget_exceeded')

    def test_model_disabled_filter_and_resumption_take_new_token(self):
        run, work = rows('awaiting_input'); work.active_token = None
        work.stage = 'review_plan'; work.ready = True
        session = MagicMock(); session.scalar.side_effect = [None, run]; session.get.return_value = work
        with patch.object(worker.SessionLocal, 'begin', return_value=nullcontext(session)), patch.object(worker.repo, 'append_event'):
            claim = worker.claim_next(allow_model=False)
        sql = str(session.scalar.call_args.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
        self.assertIn("'plan', 'generate'", sql); self.assertEqual(run.lifecycle, 'running')
        self.assertNotEqual(claim['token'], TOKEN); self.assertEqual(claim['remaining_seconds'], 600)


class ApiMigrationTests(unittest.TestCase):
    def test_approval_api_conflict_is_409_not_422(self):
        app = FastAPI(); app.include_router(platform_runs.router)
        with TestClient(app) as client, patch.object(control, 'decide_checkpoint', side_effect=RunConflictError('stale')):
            response = client.post(f'/api/v2/runs/{RID}/checkpoints/{CPID}/decision', json=decision().model_dump())
        self.assertEqual(response.status_code, 409)

    def test_v1_bound_task_write_blocked_but_read_unchanged(self):
        session = MagicMock(); session.scalar.return_value = RID
        with patch('backend.app.api.native_task_guard.SessionLocal', return_value=nullcontext(session)):
            guard_native_task(NS(method='GET', path_params={'task_id': str(TID)}))
            with self.assertRaises(Exception) as error: guard_native_task(NS(method='POST', path_params={'task_id': str(TID)}))
        self.assertEqual(error.exception.status_code, 409)

    def test_migration_and_models_compile_offline(self):
        path = Path('backend/migrations/versions/d714a02b0001_add_run_work_checkpoints.py')
        spec = importlib.util.spec_from_file_location('day2_migration', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        output = StringIO()
        context = MigrationContext.configure(dialect_name='postgresql', opts={'as_sql': True, 'output_buffer': output})
        with Operations.context(context): module.upgrade(); module.downgrade()
        self.assertIn('CREATE TABLE run_work', output.getvalue()); self.assertIn('RAISE EXCEPTION', output.getvalue())
        for model in (RunWork, RunCheckpoint):
            self.assertIn('CREATE TABLE', str(CreateTable(model.__table__).compile(dialect=postgresql.dialect())))


if __name__ == '__main__': unittest.main()
