"""短事务领取/落盘。副作用由独立子进程执行，active_token 是不可自动过期的栅栏。"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select, text
from ..db.session import SessionLocal
from ..db.models import PlatformRun, RunWork, RunCheckpoint, TaskEvent
from ..db.repositories import platform_run_repo as repo
from ..schemas.platform_run import AgentRunRequest
from ..agent.adapters.base import StepResult
from .run_lifecycle import transition, RunConflictError
from .experiment_contract_service import digest

WORKER_LOCK = 714202602


def import_native_events(session, run, work):
    """同事务推进旧 sequence 游标；原始序号与平台序号分别保留。"""
    if run.legacy_task_id is None:
        return
    events = list(session.scalars(select(TaskEvent).where(TaskEvent.task_id == run.legacy_task_id,
        TaskEvent.sequence > work.legacy_cursor).order_by(TaskEvent.sequence)))
    capabilities = dict(run.capabilities)
    for event in events:
        mapped = repo.append_event(session, run, event_type=event.event_type, source='adapter', payload={
            'legacy_task_id': str(run.legacy_task_id), 'legacy_sequence': event.sequence,
            'node_name': event.node_name, 'native': event.payload})
        field = None
        if event.event_type.startswith(('MODEL_CALL_', 'EMBEDDING_CALL_')):
            field = 'model_usage'
        elif event.event_type.startswith('TOOL_CALL_'):
            field = 'tool_trace'
        else:
            field = {'RETRIEVAL_COMPLETED': 'retrieval', 'TOOL_CONTEXT_PREPARED': 'context',
                     'PLAN_CREATED': 'planning', 'REFLECTION_FINISHED': 'reflection'}.get(event.event_type)
        if field:
            previous = capabilities.get(field, {})
            refs = [*previous.get('evidence_sequences', []), mapped.sequence]
            # 此处只证明事件已采集。完整调用配对及 usage 覆盖率由汇总器判断，不冒充完整 L2。
            capabilities[field] = dict(declared=True, validated=False, availability='partial',
                occurrence='occurred', source='adapter', evidence_sequences=refs,
                expected_records=None, recorded_records=len(refs))
        work.legacy_cursor = event.sequence
    run.capabilities = capabilities


def claim_next(*, allow_model: bool):
    with SessionLocal.begin() as session:
        # 即使 session advisory lock 的连接丢失，第二个进程也不得越过未清除的 active 栅栏。
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': WORKER_LOCK + 1})
        if session.scalar(select(RunWork.run_id).where(RunWork.active_token.is_not(None)).limit(1)):
            raise RunConflictError('Unsettled worker step exists; stop writers and explicitly recover it')
        statement = select(PlatformRun).join(RunWork).where(RunWork.ready.is_(True),
            PlatformRun.lifecycle.in_(['queued', 'preparing', 'running', 'awaiting_input']))
        if not allow_model:
            statement = statement.where((RunWork.stage.not_in(['plan', 'generate'])) | RunWork.cancel_requested)
        run = session.scalar(statement.order_by(PlatformRun.created_at, PlatformRun.id)
                             .with_for_update(of=PlatformRun, skip_locked=True).limit(1))
        if run is None:
            return None
        work = session.get(RunWork, run.id)
        if work.cancel_requested:
            target = 'finished' if run.lifecycle == 'queued' else 'evaluating'
            transition(run, expected_version=run.version, target=target, execution_status='cancelled')
            work.ready = False
            repo.append_event(session, run, event_type='EXECUTION_CANCELLED', payload={'writers_stopped': True})
            return {'settled': True}
        if run.lifecycle == 'queued':
            transition(run, expected_version=run.version, target='preparing')
        elif run.lifecycle in ('preparing', 'awaiting_input'):
            transition(run, expected_version=run.version, target='running')
        else:
            run.version += 1
        token = uuid4()
        work.active_token, work.active_since, work.ready = token, datetime.now(timezone.utc), False
        work.result = None
        repo.append_event(session, run, event_type='STEP_STARTED', payload={'stage': work.stage, 'token': str(token)})
        request = AgentRunRequest.model_validate(run.request)
        return {'run_id': run.id, 'token': token, 'request': run.request, 'stage': work.stage,
                'state': work.state, 'remaining_seconds': max(0, request.budget.timeout_seconds - work.active_seconds)}


def save_step_result(run_id, token, result):
    with SessionLocal.begin() as session:
        run = repo.get_run(session, run_id, for_update=True)
        work = session.get(RunWork, run_id)
        if run is None or work is None or work.active_token != token or work.result is not None:
            raise RunConflictError('Worker result lost ownership')
        work.result = result


def is_cancelled(run_id, token):
    with SessionLocal() as session:
        work = session.get(RunWork, run_id)
        if work is None or work.active_token != token:
            raise RunConflictError('Worker lost ownership')
        return work.cancel_requested


def settle_step(run_id, token, *, elapsed, forced_reason=None):
    with SessionLocal.begin() as session:
        run = repo.get_run(session, run_id, for_update=True)
        work = session.get(RunWork, run_id)
        if run is None or work is None or work.active_token != token:
            raise RunConflictError('Worker no longer owns this step')
        completed_stage = work.stage
        work.ready = False
        work.active_seconds += max(0, elapsed)
        import_native_events(session, run, work)
        result = work.result
        if forced_reason or result is None:
            # kill 可能发生在写入和事件提交之间。保留栅栏，不能假定子孙进程已清理。
            work.error_code = forced_reason or 'worker_exit_without_result'
            work.cleanup_status = 'unverified'
            transition(run, expected_version=run.version, target='interrupted')
            repo.append_event(session, run, event_type='EXECUTION_INTERRUPTED', payload={
                'reason': work.error_code, 'token': str(token), 'cleanup_status': work.cleanup_status})
            return
        work.cleanup_status = result['cleanup']['status']
        work.error_code = result.get('error_code')
        if work.cleanup_status == 'failed':
            transition(run, expected_version=run.version, target='interrupted')
            repo.append_event(session, run, event_type='CLEANUP_FAILED', payload={'error_code': work.error_code})
            return
        work.active_token, work.active_since = None, None
        if result.get('error_code'):
            transition(run, expected_version=run.version, target='evaluating', execution_status='failed')
            repo.append_event(session, run, event_type='EXECUTION_FAILED', payload={'error_code': work.error_code})
            return
        step = StepResult.model_validate(result['step'])
        work.state = step.state
        if work.cancel_requested:
            transition(run, expected_version=run.version, target='evaluating', execution_status='cancelled')
        elif step.execution_status:
            transition(run, expected_version=run.version, target='evaluating', execution_status=step.execution_status)
        else:
            if not step.next_stage:
                raise ValueError('Adapter did not provide a next stage')
            work.stage = step.next_stage
            if step.checkpoint_kind:
                transition(run, expected_version=run.version, target='awaiting_input')
                cp = RunCheckpoint(run_id=run.id, kind=step.checkpoint_kind, run_version=run.version,
                    payload=step.checkpoint_payload, payload_sha256=digest(step.checkpoint_payload))
                session.add(cp)
                session.flush()
                repo.append_event(session, run, event_type='CHECKPOINT_CREATED', payload={
                    'checkpoint_id': str(cp.id), 'kind': cp.kind, 'payload_sha256': cp.payload_sha256})
            else:
                work.ready = True
                run.version += 1
        repo.append_event(session, run, event_type='STEP_FINISHED', payload={
            'stage': completed_stage, 'next_stage': work.stage if step.next_stage else None,
            'lifecycle': run.lifecycle, 'execution_status': run.execution_status,
            'cleanup_status': work.cleanup_status})


def recover_interrupted(run_id, token):
    """操作者已确认旧 worker/子进程停止后调用；只停止、不重放、不清空历史结果。"""
    with SessionLocal.begin() as session:
        run = repo.get_run(session, run_id, for_update=True)
        work = session.get(RunWork, run_id)
        if run is None or work is None or work.active_token != token:
            raise RunConflictError('Recovery token differs from unresolved step')
        import_native_events(session, run, work)
        if run.lifecycle != 'interrupted':
            transition(run, expected_version=run.version, target='interrupted')
        work.ready = False
        work.active_token, work.active_since = None, None
        work.cleanup_status = 'operator_confirmed'
        repo.append_event(session, run, event_type='INTERRUPTION_ACKNOWLEDGED', payload={
            'token': str(token), 'cleanup_source': 'operator', 'replayed': False})
