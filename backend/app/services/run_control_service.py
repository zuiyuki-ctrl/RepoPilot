"""只登记决定与调度状态；API 调用这些函数不会调用模型或写源码。"""
from datetime import datetime, timezone
from sqlalchemy import select
from ..db.session import SessionLocal
from ..db.models import PlatformRun, RunWork, RunCheckpoint, AgentTask, Repository
from ..db.repositories import platform_run_repo as repo
from ..schemas.platform_run import AgentRunRequest
from ..schemas.run_control import ControlRead, CheckpointRead
from .run_lifecycle import RunConflictError
from .experiment_contract_service import digest


def enqueue_native(run_id, *, bundle_sha256=None):
    """内部开发/未来调度入口；只接纳已冻结且绑定 fresh task 的 Native Run。"""
    with SessionLocal.begin() as session:
        run = repo.get_run(session, run_id, for_update=True)
        if run is None:
            raise RunConflictError('Run not found')
        existing = session.get(RunWork, run_id)
        if existing:
            return
        request = AgentRunRequest.model_validate(run.request)
        task = session.get(AgentTask, run.legacy_task_id) if run.legacy_task_id else None
        if (run.lifecycle != 'queued' or request.agent.adapter != 'native' or task is None
                or task.status != 'created' or task.task_type != 'plan'
                or task.repository_id != run.repository_id or task.user_request != request.task_description):
            raise RunConflictError('Native run requires a fresh matching task')
        # 同一工作副本不能被两个 v2 Run 使用，即使其中一个正在等待审批。
        session.scalar(select(Repository).where(Repository.id == run.repository_id).with_for_update())
        occupied = session.scalar(select(RunWork.run_id).join(PlatformRun).where(
            PlatformRun.repository_id == run.repository_id, PlatformRun.id != run.id))
        if occupied:
            raise RunConflictError('Use an independent repository workspace for each run')
        state = {'task_id': str(task.id), 'repository_id': str(run.repository_id)}
        if bundle_sha256:
            state['bundle_sha256'] = bundle_sha256
        session.add(RunWork(run_id=run_id, stage='baseline' if bundle_sha256 else 'prepare', state=state, ready=True,
            cancel_requested=False, active_seconds=0, cleanup_status='not_needed', legacy_cursor=0))
        repo.append_event(session, run, event_type='WORK_ENQUEUED', payload={})


def enqueue_process(run_id, *, bundle_sha256, allow_model=False):
    from .platform_test_collector import checked_bundle
    from ..schemas.process_agent import ProcessConfiguration
    from .model_gateway_service import authorize_process
    with SessionLocal.begin() as session:
        run = repo.get_run(session, run_id, for_update=True)
        if run is None:
            raise RunConflictError('Run not found')
        request = AgentRunRequest.model_validate(run.request)
        state = {'bundle_sha256': bundle_sha256, 'repository_id': str(run.repository_id)}
        _, manifest, _ = checked_bundle(request, state)
        config = ProcessConfiguration.model_validate(manifest['process_config'])
        if digest(config.model_dump(mode='json')) != request.config_sha256:
            raise RunConflictError('Frozen Process configuration differs')
        existing = session.get(RunWork, run_id)
        if existing:
            if existing.state.get('bundle_sha256') != bundle_sha256:
                raise RunConflictError('Run already bound to another bundle')
            if config.model_policy is not None and allow_model is not True:
                raise RunConflictError('Process model authorization required')
            return
        if run.lifecycle != 'queued' or request.agent.adapter != 'process' or run.legacy_task_id is not None:
            raise RunConflictError('Expected fresh independent Process Run')
        authorize_process(session, run, config, allow_model=allow_model)
        if config.model_policy is not None:
            state['model_required'] = True
        session.add(RunWork(run_id=run.id, stage='baseline', state=state, ready=True,
            cancel_requested=False, active_seconds=0, cleanup_status='not_needed', legacy_cursor=0))
        repo.append_event(session, run, event_type='WORK_ENQUEUED', payload={'adapter': 'process'})


def latest_checkpoint(session, run_id):
    return session.scalar(select(RunCheckpoint).where(RunCheckpoint.run_id == run_id)
        .order_by(RunCheckpoint.run_version.desc()).limit(1))


def get_control(run_id):
    with SessionLocal() as session:
        work = session.get(RunWork, run_id)
        if work is None:
            return None
        checkpoint = latest_checkpoint(session, run_id)
        return ControlRead(stage=work.stage, ready=work.ready,
            active=work.active_token is not None and work.cleanup_status not in ('unverified', 'failed'),
            cancel_requested=work.cancel_requested, cleanup_status=work.cleanup_status,
            error_code=work.error_code, active_seconds=work.active_seconds,
            interruption_token=work.active_token if work.cleanup_status in ('unverified', 'failed') else None,
            cleanup_error_code=(work.result or {}).get('cleanup', {}).get('error_code'),
            checkpoint=CheckpointRead.model_validate(checkpoint) if checkpoint else None)


def decide_checkpoint(run_id, checkpoint_id, data):
    with SessionLocal.begin() as session:
        run = repo.get_run(session, run_id, for_update=True)
        cp = session.get(RunCheckpoint, checkpoint_id)
        work = session.get(RunWork, run_id)
        if run is None or work is None or cp is None or cp.run_id != run_id:
            return None
        if cp.payload_sha256 != data.payload_sha256 or cp.run_version != data.expected_version:
            raise RunConflictError('Approval content or version differs')
        # 同一决定重发返回历史记录；不能将 approved 改成 rejected。
        if cp.decision is not None:
            if cp.decision != data.decision or cp.comment != data.comment:
                raise RunConflictError('Checkpoint already decided differently')
            return CheckpointRead.model_validate(cp)
        if (run.lifecycle != 'awaiting_input' or run.version != data.expected_version
                or work.cancel_requested or work.active_token is not None):
            raise RunConflictError('Checkpoint is no longer awaiting approval')
        cp.decision, cp.comment, cp.decided_at = data.decision, data.comment, datetime.now(timezone.utc)
        work.state = {**work.state, 'approval': {'decision': data.decision, 'comment': data.comment}}
        if cp.kind == 'candidate':
            # 执行时使用审批页面对应的那份候选，不重新生成。
            work.state = {**work.state, 'candidate': cp.payload}
        work.ready = True
        run.version += 1
        repo.append_event(session, run, event_type='APPROVAL_RECORDED', payload={
            'checkpoint_id': str(cp.id), 'payload_sha256': cp.payload_sha256, 'decision': cp.decision})
        return CheckpointRead.model_validate(cp)


def request_cancel(run_id, data):
    with SessionLocal.begin() as session:
        run = repo.get_run(session, run_id, for_update=True)
        work = session.get(RunWork, run_id)
        if run is None or work is None:
            return None
        if work.cancel_requested:
            return {'cancel_requested': True}
        if run.version != data.expected_version or run.lifecycle in ('finished', 'interrupted', 'evaluating'):
            raise RunConflictError('Run cannot be cancelled at this version/state')
        work.cancel_requested = True
        if work.state.get('model_required'):
            from .model_gateway_service import revoke_attempt
            revoke_attempt(session, run)
        work.ready = True
        run.version += 1
        repo.append_event(session, run, event_type='CANCEL_REQUESTED', payload={})
        return {'cancel_requested': True}
