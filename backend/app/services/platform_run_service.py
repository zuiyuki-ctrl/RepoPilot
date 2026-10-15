"""Day 1 内部写入口与公开只读查询；不启动 Agent 或读取真实工作区。"""
from uuid import UUID
from contextlib import nullcontext
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from ..db.session import SessionLocal
from ..db.models import PlatformRun, Repository, AgentTask, RunEvaluation, TestRun
from ..db.repositories import platform_run_repo as repo
from ..schemas.platform_run import AgentRunRequest, RunRead, RunEventRead
from ..schemas.platform_evaluation import EvaluationInput
from .experiment_contract_service import digest
from .run_observation_service import summarize_observation
from .run_lifecycle import transition, RunConflictError
from .platform_evaluation_service import evaluate_run


def as_read(run):
    request = AgentRunRequest.model_validate(run.request)
    return RunRead(id=run.id, repository_id=run.repository_id, legacy_task_id=run.legacy_task_id,
        case_id=request.case_id, case_version=request.case_version, agent=request.agent,
        lifecycle=run.lifecycle, execution_status=run.execution_status,
        evaluation_outcome=run.evaluation_outcome, version=run.version,
        created_at=run.created_at, started_at=run.started_at, completed_at=run.completed_at,
        observation=summarize_observation(run.capabilities))


def create_run(request: AgentRunRequest, *, repository_id: UUID, creation_key: str,
               legacy_task_id: UUID | None = None) -> RunRead:
    """内部编排入口。相同键/相同请求返回原 Run，冲突拒绝；没有 HTTP 写路由。"""
    if not creation_key.strip() or len(creation_key) > 100:
        raise ValueError('Invalid creation key')
    if request.agent.adapter == 'process' and legacy_task_id is not None:
        raise ValueError('Process run cannot own a legacy task')
    payload = request.model_dump(mode='json')
    fingerprint = digest(dict(request=payload, repository_id=str(repository_id),
                              legacy_task_id=str(legacy_task_id) if legacy_task_id else None))
    with SessionLocal.begin() as session:
        repository = session.get(Repository, repository_id)
        if repository is None or repository.commit_hash != request.repository_commit:
            raise ValueError('Repository missing or commit differs')
        if legacy_task_id is not None:
            task = session.get(AgentTask, legacy_task_id)
            if task is None or task.repository_id != repository_id:
                raise ValueError('Legacy task belongs to another repository')
        inserted = session.scalar(insert(PlatformRun).values(id=request.run_id,
            repository_id=repository_id, legacy_task_id=legacy_task_id, creation_key=creation_key,
            request_sha256=fingerprint, request=payload, lifecycle='queued', execution_status='pending',
            evaluation_outcome='pending', version=1, event_sequence=0, capabilities={})
            .on_conflict_do_nothing().returning(PlatformRun.id))
        run = session.scalar(select(PlatformRun).where(PlatformRun.creation_key == creation_key).with_for_update())
        if run is None or run.request_sha256 != fingerprint:
            raise RunConflictError('Creation key or run identity already used')
        if inserted:
            repo.append_event(session, run, event_type='RUN_CREATED', payload={'protocol_version': 1})
        return as_read(run)


def transition_run(run_id: UUID, *, expected_version: int, target: str, execution_status=None):
    if target == 'finished':
        # 只有排队取消可直接终止；运行后的终态由独立评测入口保存。
        allowed_queued_cancel = execution_status == 'cancelled'
    else:
        allowed_queued_cancel = False
    with SessionLocal.begin() as session:
        run = repo.get_run(session, run_id, for_update=True)
        if run is None:
            return None
        if target == 'finished' and not (allowed_queued_cancel and run.lifecycle == 'queued'):
            raise RunConflictError('Use finish_evaluation to finish an evaluated run')
        transition(run, expected_version=expected_version, target=target, execution_status=execution_status)
        repo.append_event(session, run, event_type='RUN_STATE_CHANGED', payload={
            'lifecycle': run.lifecycle, 'execution_status': run.execution_status, 'version': run.version})
        return as_read(run)


def finish_evaluation(evidence: EvaluationInput, *, expected_version: int, _session=None):
    """平台内部采集入口，验证 TestRun 归属/内容后原子保存评测与终态。"""
    result = evaluate_run(evidence)
    with (nullcontext(_session) if _session is not None else SessionLocal.begin()) as session:
        run = repo.get_run(session, evidence.run_id, for_update=True)
        if run is None:
            return None
        previous = session.scalar(select(RunEvaluation).where(RunEvaluation.run_id == run.id,
            RunEvaluation.evidence_sha256 == result.evidence_sha256))
        if previous is not None:
            return as_read(run)
        request = AgentRunRequest.model_validate(run.request)
        if (run.lifecycle != 'evaluating' or run.execution_status != evidence.execution_status
                or (evidence.execution_status == 'completed' and run.started_at is None)
                or (request.case_id, request.case_version, request.case_sha256) !=
                   (evidence.case_id, evidence.case_version, evidence.case_sha256)
                or request.rule_sha256 != result.rule_sha256
                or request.task_type != evidence.task_type
                or request.environment_sha256 != evidence.environment_sha256
                or request.initial_snapshot_hash != evidence.initial_snapshot_hash):
            raise RunConflictError('Evaluation differs from run execution or frozen case')
        for test in (evidence.baseline_test, evidence.final_test):
            if test is None:
                continue
            stored = session.get(TestRun, test.test_run_id)
            if stored is None or stored.run_id != run.id:
                raise RunConflictError('TestRun does not belong to this run')
            for field in ('snapshot_hash', 'status', 'exit_code', 'timed_out', 'error', 'test_report', 'image', 'timeout_seconds'):
                if getattr(stored, field) != getattr(test, field):
                    raise RunConflictError('TestRun evidence differs from persisted result')
        transition(run, expected_version=expected_version, target='finished')
        run.evaluation_outcome = result.outcome
        session.add(RunEvaluation(run_id=run.id,
            test_run_id=evidence.final_test.test_run_id if evidence.final_test else None,
            evidence_sha256=result.evidence_sha256, rule_sha256=result.rule_sha256,
            outcome=result.outcome, reason=result.reason, evidence=evidence.model_dump(mode='json')))
        repo.append_event(session, run, event_type='EVALUATION_FINISHED', payload=result.model_dump(mode='json'))
        return as_read(run)


def claim_next_run():
    """原子领取原语；不会运行 Agent，Day 2 的单 worker 负责执行与所有权恢复。"""
    with SessionLocal.begin() as session:
        run = repo.next_queued_for_update(session)
        if run is None:
            return None
        transition(run, expected_version=run.version, target='preparing')
        repo.append_event(session, run, event_type='RUN_CLAIMED', payload={'version': run.version})
        return as_read(run)


def record_capabilities(run_id: UUID, *, expected_version: int, capabilities: dict):
    summary = summarize_observation(capabilities)
    with SessionLocal.begin() as session:
        run = repo.get_run(session, run_id, for_update=True)
        if run is None:
            return None
        if run.version != expected_version or run.lifecycle in ('finished', 'interrupted'):
            raise RunConflictError('Capabilities cannot change at this run version/state')
        from ..db.models import PlatformRunEvent
        referenced = {seq for value in summary.capabilities.values() for seq in value.evidence_sequences}
        actual = set(session.scalars(select(PlatformRunEvent.sequence).where(
            PlatformRunEvent.run_id == run_id, PlatformRunEvent.sequence.in_(referenced)))) if referenced else set()
        if actual != referenced:
            raise RunConflictError('Capability evidence refers to missing run events')
        run.capabilities = {k: v.model_dump(mode='json') for k, v in summary.capabilities.items()}
        run.version += 1
        repo.append_event(session, run, event_type='CAPABILITIES_RECORDED', payload={'version': run.version})
        return as_read(run)


def get_run(run_id: UUID):
    with SessionLocal() as session:
        run = repo.get_run(session, run_id)
        return as_read(run) if run else None


def list_runs(*, limit: int, offset: int):
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError('Invalid pagination')
    with SessionLocal() as session:
        return [as_read(run) for run in repo.list_runs(session, limit=limit, offset=offset)]


def list_events(run_id: UUID, *, after_sequence: int, limit: int):
    if after_sequence < 0 or not 1 <= limit <= 100:
        raise ValueError('Invalid pagination')
    with SessionLocal() as session:
        if repo.get_run(session, run_id) is None:
            return None
        return [RunEventRead.model_validate(event) for event in repo.list_events(
            session, run_id, after_sequence=after_sequence, limit=limit)]
