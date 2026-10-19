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
        from .platform_catalog_service import assert_no_catalog_writer
        assert_no_catalog_writer(session)
        from .platform_experiment_service import assert_no_preparation
        assert_no_preparation(session)
        if session.scalar(select(RunWork.run_id).where(RunWork.active_token.is_not(None)).limit(1)):
            raise RunConflictError('Unsettled worker step exists; stop writers and explicitly recover it')
        statement = select(PlatformRun).join(RunWork).where(RunWork.ready.is_(True),
            PlatformRun.lifecycle.in_(['queued', 'preparing', 'running', 'awaiting_input', 'evaluating']))
        if not allow_model:
            statement = statement.where((RunWork.stage.not_in(['plan', 'generate'])) | RunWork.cancel_requested)
            statement = statement.where(
                RunWork.cancel_requested | RunWork.stage.in_(['baseline', 'evaluate'])
                | RunWork.state['model_required'].as_boolean().is_distinct_from(True))
        run = session.scalar(statement.order_by(PlatformRun.created_at, PlatformRun.id)
                             .with_for_update(of=PlatformRun, skip_locked=True).limit(1))
        if run is None:
            return None
        work = session.get(RunWork, run.id)
        if work.cancel_requested and run.lifecycle != 'evaluating':
            target = 'finished' if run.lifecycle == 'queued' else 'evaluating'
            transition(run, expected_version=run.version, target=target, execution_status='cancelled')
            work.ready = False
            if target == 'evaluating' and work.state.get('bundle_sha256'):
                work.stage, work.ready = 'evaluate', True
            repo.append_event(session, run, event_type='EXECUTION_CANCELLED', payload={'writers_stopped': True})
            return {'settled': True}
        request = AgentRunRequest.model_validate(run.request)
        model_required = False
        if request.agent.adapter == 'process' and work.stage in ('prepare', 'process_run'):
            # Do not trust the scheduling hint alone: check frozen authority/config.
            from .platform_test_collector import checked_bundle
            from ..schemas.process_agent import ProcessConfiguration
            from ..db.models import RunModelGrant
            _, manifest, _ = checked_bundle(request, work.state)
            config = ProcessConfiguration.model_validate(manifest['process_config'])
            if digest(config.model_dump(mode='json')) != request.config_sha256:
                raise RunConflictError('Frozen Process configuration differs')
            model_required = config.model_policy is not None
            if model_required:
                grant = session.get(RunModelGrant, run.id)
                if (allow_model is not True or grant is None or grant.revoked_at
                        or grant.config_sha256 != request.config_sha256
                        or grant.policy != config.model_policy.model_dump(mode='json')):
                    raise RunConflictError('Process requires both entry and worker model authorization')
                work.state = {**work.state, 'model_required': True}
        if run.lifecycle == 'queued':
            transition(run, expected_version=run.version, target='preparing')
        elif run.lifecycle == 'preparing' and work.stage == 'prepare':
            # Baseline/preparation failures must not count as started Agent executions.
            run.version += 1
        elif run.lifecycle in ('preparing', 'awaiting_input'):
            transition(run, expected_version=run.version, target='running')
        else:
            run.version += 1
        token = uuid4()
        work.active_token, work.active_since, work.ready = token, datetime.now(timezone.utc), False
        work.result = None
        if model_required and work.stage == 'process_run':
            from .model_gateway_service import bind_attempt
            bind_attempt(session, run, work, allow_model=allow_model)
        repo.append_event(session, run, event_type='STEP_STARTED', payload={'stage': work.stage, 'token': str(token)})
        request = AgentRunRequest.model_validate(run.request)
        # Evaluation has its own 120s container limit; do not consume the Agent budget.
        remaining = max(0, request.budget.timeout_seconds - work.active_seconds)
        if work.stage in ('baseline', 'evaluate'):
            remaining = 240
        elif request.agent.adapter == 'process':
            # Inner Docker timeout controls the workload. Allow time to confirm cleanup.
            remaining = request.budget.timeout_seconds + 90
        return {'run_id': run.id, 'token': token, 'request': run.request, 'stage': work.stage,
                'state': work.state, 'execution_status': run.execution_status, 'remaining_seconds': remaining}


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
        if work.state.get('model_required') and (completed_stage == 'process_run' or forced_reason
                or work.result is None or work.result.get('error_code')
                or work.result.get('cleanup', {}).get('status') == 'failed'):
            from .model_gateway_service import revoke_attempt
            revoke_attempt(session, run)
        work.ready = False
        if completed_stage not in ('baseline', 'evaluate'):
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
        if completed_stage == 'evaluate':
            if result.get('error_code') or 'evaluation' not in result:
                transition(run, expected_version=run.version, target='interrupted')
                repo.append_event(session, run, event_type='EVALUATION_ERROR', payload={'error_code': work.error_code})
                return
            from ..schemas.platform_evaluation import EvaluationInput
            from .platform_run_service import finish_evaluation
            evidence = EvaluationInput.model_validate(result['evaluation'])
            # All capability references point at this Run's platform events, not agent claims.
            capabilities = dict(run.capabilities)
            for field, present in (('execution', run.started_at is not None), ('diff', evidence.diff_sha256 is not None),
                                   ('tests', evidence.final_test is not None)):
                if present:
                    event = repo.append_event(session, run, event_type=f'{field.upper()}_EVIDENCE',
                        payload={'snapshot_hash': evidence.final_snapshot_hash})
                    availability = 'available'
                    if field == 'tests':
                        report = evidence.final_test.test_report or {}
                        if report.get('status') != 'recorded':
                            availability = 'missing' if report.get('status') in (None, 'missing') else 'invalid'
                    capabilities[field] = dict(declared=True, validated=True, availability=availability,
                        occurrence='occurred', source='platform', evidence_sequences=[event.sequence],
                        expected_records=1, recorded_records=1)
            run.capabilities = capabilities
            finish_evaluation(evidence, expected_version=run.version, _session=session)
            return
        if result.get('error_code'):
            # Revocation can make the child raise before the supervisor observes
            # cancellation. Once cleanup is confirmed, that error must not turn
            # an accepted cancellation into an Agent failure. Unknown writers
            # still take the interrupted/fence-retained branches above.
            cancelled = work.cancel_requested
            transition(run, expected_version=run.version, target='evaluating',
                       execution_status='cancelled' if cancelled else 'failed')
            repo.append_event(session, run, event_type='EXECUTION_CANCELLED' if cancelled else 'EXECUTION_FAILED',
                payload={'error_code': work.error_code, **({'writers_stopped': True} if cancelled else {})})
            if work.state.get('bundle_sha256'):
                work.stage, work.ready = 'evaluate', True
            return
        step = StepResult.model_validate(result['step'])
        work.state = step.state
        process_info = step.state.get('process_execution')
        if process_info:
            repo.append_event(session, run, event_type='PROCESS_EXECUTION_FINISHED', payload={
                'exit_code': process_info['exit_code'], 'timed_out': process_info['timed_out'],
                'protocol_error': process_info['protocol_error'], 'trace_status': process_info['trace']['status']})
            fields = {'model_call': 'model_usage', 'tool_call': 'tool_trace', 'retrieval': 'retrieval',
                      'context': 'context', 'planning': 'planning', 'reflection': 'reflection'}
            capabilities = dict(run.capabilities)
            for value in process_info['trace']['events']:
                event = repo.append_event(session, run, event_type='PROCESS_TRACE', source='agent_reported', payload=value)
                field = fields[value['kind']]
                refs = [*capabilities.get(field, {}).get('evidence_sequences', []), event.sequence]
                capabilities[field] = dict(declared=True, validated=False, availability='partial',
                    occurrence='occurred', source='agent_reported', evidence_sequences=refs,
                    expected_records=None, recorded_records=len(refs))
            run.capabilities = capabilities
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
        if run.lifecycle == 'evaluating' and work.state.get('bundle_sha256'):
            work.stage, work.ready = 'evaluate', True
        repo.append_event(session, run, event_type='STEP_FINISHED', payload={
            'stage': completed_stage, 'next_stage': work.stage if step.next_stage else None,
            'lifecycle': run.lifecycle, 'execution_status': run.execution_status,
            'cleanup_status': work.cleanup_status})


def recover_interrupted(run_id, token):
    """操作者已确认旧 worker/子进程停止后调用；只停止、不重放、不清空历史结果。"""
    # Revoke in a short transaction, then clean Docker/files without holding DB
    # locks. A failed cleanup leaves the original durable active_token untouched.
    with SessionLocal.begin() as session:
        run = repo.get_run(session, run_id, for_update=True)
        work = session.get(RunWork, run_id)
        if run is None or work is None or work.active_token != token:
            raise RunConflictError('Recovery token differs from unresolved step')
        gateway_attempt = work.state.get('model_required') and work.stage == 'process_run'
        if work.state.get('model_required'):
            from .model_gateway_service import revoke_attempt
            revoke_attempt(session, run)
    if gateway_attempt:
        from .gateway_runtime import cleanup_owned_attempt
        cleanup_owned_attempt(run_id, token)
    with SessionLocal.begin() as session:
        run = repo.get_run(session, run_id, for_update=True)
        work = session.get(RunWork, run_id)
        if run is None or work is None or work.active_token != token:
            raise RunConflictError('Recovery token differs from unresolved step')
        if work.state.get('model_required'):
            from .model_gateway_service import revoke_attempt
            revoke_attempt(session, run)
        import_native_events(session, run, work)
        if run.lifecycle != 'interrupted':
            transition(run, expected_version=run.version, target='interrupted')
        work.ready = False
        work.active_token, work.active_since = None, None
        work.cleanup_status = 'operator_confirmed'
        repo.append_event(session, run, event_type='INTERRUPTION_ACKNOWLEDGED', payload={
            'token': str(token), 'cleanup_source': 'operator', 'replayed': False})
