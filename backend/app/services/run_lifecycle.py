"""纯状态机：事务、行锁由调用服务管理，不在这里启动任何执行。"""
from datetime import datetime, timezone


class RunConflictError(ValueError):
    pass


TRANSITIONS = {
    'queued': {'preparing', 'finished'},
    'preparing': {'running', 'evaluating', 'interrupted'},
    'running': {'awaiting_input', 'evaluating', 'interrupted'},
    'awaiting_input': {'running', 'evaluating', 'interrupted'},
    'evaluating': {'finished', 'interrupted'},
    'finished': set(), 'interrupted': set(),
}


def transition(run, *, expected_version: int, target: str, execution_status: str | None = None):
    if run.version != expected_version:
        raise RunConflictError('Run version changed')
    if target not in TRANSITIONS.get(run.lifecycle, set()):
        raise RunConflictError('Invalid lifecycle transition')
    execution = execution_status or run.execution_status
    if target in ('running', 'awaiting_input', 'preparing') and execution != 'pending':
        raise RunConflictError('Active execution must remain pending')
    if target == 'evaluating' and execution not in ('completed', 'failed', 'timed_out', 'cancelled'):
        raise RunConflictError('Evaluation requires a terminal execution result')
    if target == 'evaluating' and execution == 'completed' and run.started_at is None:
        raise RunConflictError('An unstarted run cannot report completed execution')
    if target == 'finished' and run.lifecycle == 'queued' and execution != 'cancelled':
        raise RunConflictError('Queued run may only finish by cancellation')
    if target == 'finished' and run.lifecycle == 'evaluating' and execution != run.execution_status:
        raise RunConflictError('Cannot change execution result during evaluation')
    now = datetime.now(timezone.utc)
    if target == 'running' and run.started_at is None:
        run.started_at = now
    if target == 'interrupted':
        execution = 'unknown'
        run.evaluation_outcome = 'unknown'
    if target == 'finished' and run.lifecycle == 'queued':
        run.evaluation_outcome = 'not_passed'
    if target in ('finished', 'interrupted'):
        run.completed_at = now
    run.lifecycle, run.execution_status = target, execution
    run.version += 1
