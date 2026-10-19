"""Offline guardrails for the disposable fault runner and cancellation settlement."""
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
import pytest
from scripts.gateway_fault_checks import FaultSuite, wait_until
from backend.app.services import run_worker_service as worker
from tests.test_model_gateway import ledger


def test_cancelled_worker_error_must_not_report_execution_failed(ledger):
    l=ledger
    l.run.version=1;l.run.legacy_task_id=None;l.run.capabilities={}
    l.work.state={'model_required':True,'bundle_sha256':'b'*64}
    l.work.cancel_requested=True
    l.work.result={'error_code':'RunConflictError','cleanup':{'status':'confirmed'}}
    with patch.object(worker.repo,'append_event'):
        worker.settle_step(l.run.id,l.token,elapsed=1)
    assert l.run.execution_status=='cancelled'
    assert l.run.lifecycle=='evaluating' and l.work.stage=='evaluate'
    assert l.work.active_token is None and l.grant.revoked_at


def test_fault_cleanup_does_not_recover_when_child_stop_unconfirmed():
    suite=object.__new__(FaultSuite)
    child=MagicMock();child.is_alive.return_value=True
    suite.children=[child];suite.blockers=[]
    suite.attempts=[{'run_id':'run','token':'attempt'}]
    suite.worker=NS(recover_interrupted=MagicMock())
    assert suite.cleanup()==['fault_child_stop_unconfirmed']
    suite.worker.recover_interrupted.assert_not_called()


def test_fault_cleanup_removes_blocker_before_recovery():
    suite=object.__new__(FaultSuite)
    suite.children=[];suite.blockers=['owned-blocker']
    suite.attempts=[{'run_id':'run','token':'attempt'}]
    order=[]
    suite.remove_blocker=lambda _:order.append('remove_blocker')
    suite.worker=NS(recover_interrupted=lambda *args:order.append('recover'))
    suite.snapshot=lambda a:{'token':'attempt'}
    assert suite.cleanup()==[]
    assert order==['remove_blocker','recover'] and suite.attempts[0]['recovered']


def test_fault_cleanup_failure_keeps_attempt_for_retry():
    suite=object.__new__(FaultSuite)
    suite.children=[];suite.blockers=[]
    suite.attempts=[{'run_id':'run','token':'attempt'}]
    suite.worker=NS(recover_interrupted=MagicMock(side_effect=RuntimeError('unavailable')))
    suite.snapshot=lambda a:{'token':'attempt'}
    assert suite.cleanup()==['fault_attempt_cleanup_unconfirmed']
    assert not suite.attempts[0].get('recovered')


def test_checkpoint_timeout_never_counts_as_success():
    with pytest.raises(TimeoutError):wait_until(lambda:False,seconds=0)


def test_probe_rejects_reusing_an_imported_database_binding_before_any_docker():
    from scripts.probe_gateway_runtime import run_probe
    with patch('backend.app.services.gateway_runtime.checked') as docker:
        with pytest.raises(RuntimeError,match='fresh interpreter'):
            run_probe('unused','unused','unused',faults=True)
        docker.assert_not_called()


@pytest.mark.parametrize('revoked,absent,expected',[(True,True,[]),(False,True,['fault_attempt_cleanup_unconfirmed']),
                                                (True,False,['fault_attempt_cleanup_unconfirmed'])])
def test_normally_settled_attempt_only_cleans_after_independent_confirmation(revoked,absent,expected):
    suite=object.__new__(FaultSuite)
    suite.children=[];suite.blockers=[];suite.attempts=[{'run_id':'run','token':'attempt'}]
    suite.snapshot=lambda a:{'token':None,'revoked':revoked}
    suite.resources_absent=lambda a:absent
    suite.worker=NS(recover_interrupted=MagicMock())
    assert suite.cleanup()==expected
    suite.worker.recover_interrupted.assert_not_called()
