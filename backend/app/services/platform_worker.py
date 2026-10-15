"""独立进程 worker；API 线程不执行模型，审批等待不占执行槽位。"""
import logging
import multiprocessing
import time
from sqlalchemy import text
from ..db.session import engine
from ..schemas.platform_run import AgentRunRequest
from ..agent.adapters.base import get_adapter
from . import run_worker_service as store

logger = logging.getLogger(__name__)


def execute_step(claim):
    adapter = get_adapter(AgentRunRequest.model_validate(claim['request']).agent.adapter)
    result = {}
    try:
        request = AgentRunRequest.model_validate(claim['request'])
        if claim['stage'] == 'evaluate':
            from .platform_test_collector import collect_final
            evidence = collect_final(request, claim['state'], claim['execution_status'])
            result['evaluation'] = evidence.model_dump(mode='json')
        else:
            if claim['stage'] == 'baseline':
                from .platform_test_collector import prepare_baseline
                step = prepare_baseline(request, claim['state'])
            else:
                step = (adapter.prepare(request, claim['state']) if claim['stage'] == 'prepare'
                        else adapter.run(request, claim['stage'], claim['state']))
            result['step'] = step.model_dump(mode='json')
    except Exception as exc:
        # 顶层 worker 边界保存错误类别；网络/模型错误不变成用户 422。
        logger.exception('Run step failed; run_id=%s stage=%s', claim['run_id'], claim['stage'])
        result['error_code'] = type(exc).__name__
    finally:
        try:
            result['cleanup'] = adapter.cleanup()
            if claim['stage'] in ('baseline', 'evaluate'):
                from .platform_container import remove_owned
                remove_owned(claim['run_id'], 'baseline' if claim['stage'] == 'baseline' else 'final')
        except Exception as exc:
            logger.exception('Adapter cleanup failed; run_id=%s', claim['run_id'])
            result['cleanup'] = {'status': 'failed', 'error_code': type(exc).__name__}
    store.save_step_result(claim['run_id'], claim['token'], result)


def supervise(claim, *, process_factory=None):
    """累计活跃时间预算不计人工等待；强制停止只记 interrupted/unknown。"""
    factory = process_factory or multiprocessing.get_context('spawn').Process
    child = factory(target=execute_step, args=(claim,))
    started = time.monotonic()
    forced = None
    try:
        if claim['remaining_seconds'] <= 0:
            forced = 'active_time_budget_exceeded'
        else:
            child.start()
            logger.info('Run %s step %s child_pid=%s token=%s',
                        claim['run_id'], claim['stage'], child.pid, claim['token'])
            while child.is_alive():
                child.join(timeout=0.5)
                if not child.is_alive():
                    break
                # A previously accepted Agent cancellation must not cancel its platform assessment.
                if claim.get('stage') != 'evaluate' and store.is_cancelled(claim['run_id'], claim['token']):
                    forced = 'cancelled_during_step'
                    break
                if time.monotonic() - started >= claim['remaining_seconds']:
                    forced = 'active_time_budget_exceeded'
                    break
    finally:
        if child.pid is not None:
            if child.is_alive():
                child.terminate()
                child.join(timeout=5)
            if child.is_alive():
                child.kill()
                child.join(timeout=5)
            if child.is_alive():
                raise RuntimeError('Child stop unconfirmed; durable ownership fence retained')
        if child.pid is not None:
            child.close()
        uses_container = (claim.get('request', {}).get('agent', {}).get('adapter') == 'process'
                          or claim.get('stage') in ('baseline', 'evaluate'))
        if uses_container and claim.get('state', {}).get('bundle_sha256'):
            # Also covers an abrupt child crash with no result, not just parent timeouts.
            # Killing docker CLI does not stop its container.
            from .platform_container import remove_owned
            for purpose in ('agent', 'baseline', 'final'):
                try:
                    remove_owned(claim['run_id'], purpose)
                except Exception:
                    forced = forced or 'container_cleanup_unconfirmed'
                    logger.exception('Owned container cleanup unconfirmed; durable fence retained')
    store.settle_step(claim['run_id'], claim['token'],
                      elapsed=time.monotonic() - started, forced_reason=forced)


def run_worker(*, once=False, allow_model=False):
    # 独立连接持有 session advisory lock，不在 ORM 事务中等模型。
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        if not connection.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': store.WORKER_LOCK}):
            raise RuntimeError('Another platform worker is running')
        try:
            while True:
                connection.execute(text('SELECT 1'))
                claim = store.claim_next(allow_model=allow_model)
                if claim and not claim.get('settled'):
                    supervise(claim)
                if not claim:
                    from .platform_catalog_service import claim_validation
                    from .catalog_validation_service import execute_validation
                    claim = claim_validation()
                    if claim:
                        logger.info('Catalog validation %s kind=%s token=%s', claim['id'], claim['kind'], claim['token'])
                        execute_validation(claim)
                if not claim:
                    from .platform_experiment_service import claim_preparation
                    from .experiment_preparation import execute_preparation
                    claim=claim_preparation(allow_model=allow_model)
                    if claim:
                        logger.info('Experiment preparation %s token=%s',claim['id'],claim['token'])
                        execute_preparation(claim)
                if once:
                    return
                if not claim:
                    time.sleep(1)
        finally:
            connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': store.WORKER_LOCK})
