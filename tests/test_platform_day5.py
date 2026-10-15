from contextlib import nullcontext
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4
from pydantic import ValidationError
from backend.app.schemas.platform_experiment import ExperimentDraft, ExperimentStart
from backend.app.services import platform_experiment_service as service
from backend.app.services.experiment_contract_service import digest
from backend.app.services.run_lifecycle import RunConflictError


def draft(**kwargs):
    return ExperimentDraft(name='test',suite_id=uuid4(),baseline_agent_id=uuid4(),candidate_agent_id=uuid4(),**kwargs)


def row(descriptor):
    return NS(id=uuid4(),status='ready',descriptor=descriptor,content_sha256=digest(descriptor),validation={'cleanup_confirmed':True,'cases':[]})


def records():
    suite=row({'cases':[{'case_id':'fixture'}]})
    agent=dict(name='demo',version='v1',adapter='process',process={'image':'a','argv':['noop']})
    return [suite,row(agent),row({**agent,'version':'v2','process':{'image':'a','argv':['fix']}})]


class ExperimentTests(TestCase):
    def test_controlled_exact_difference(self):
        session=MagicMock();session.get.side_effect=records()
        result=service.freeze(session,draft(mode='controlled',changed_fields=['process.argv']))
        self.assertEqual(result['changed_fields'],['process.argv'])
        self.assertEqual(result['run_count'],2);self.assertFalse(result['needs_model'])

    def test_unexplained_change_rejected(self):
        session=MagicMock();session.get.side_effect=records()
        with self.assertRaises(RunConflictError):service.freeze(session,draft(mode='controlled'))

    def test_derived_runtime_binding_is_not_a_strategy_change(self):
        native=dict(name='native',version='v1',adapter='native',implementation_sha256='a'*64,
                    native={'runtime_fingerprint':None})
        session=MagicMock();session.get.side_effect=[records()[0],row(native),
            row({**native,'version':'v2','native':{'runtime_fingerprint':'a'*64}})]
        with self.assertRaises(RunConflictError):
            service.freeze(session,draft(mode='controlled',changed_fields=['native.runtime_fingerprint']))

    def test_unready_version_cannot_start(self):
        items=records();items[1].status='invalid'
        session=MagicMock();session.get.side_effect=items
        with self.assertRaises(RunConflictError):service.freeze(session,draft())

    def test_content_tampering_rejected(self):
        items=records();items[1].descriptor['name']='changed'
        session=MagicMock();session.get.side_effect=items
        with self.assertRaises(RunConflictError):service.freeze(session,draft())

    def test_changed_preview_not_accepted(self):
        data=ExperimentStart(**draft().model_dump(),request_key=uuid4(),preview_sha256='0'*64,confirm_start=True)
        session=MagicMock();session.scalar.return_value=None
        with patch.object(service.SessionLocal,'begin',return_value=nullcontext(session)),patch.object(service,'freeze',return_value={'needs_model':False}):
            with self.assertRaises(RunConflictError): service.start(data)

    def test_start_retry_same_key_returns_same_experiment(self):
        data=ExperimentStart(**draft().model_dump(),request_key=uuid4(),preview_sha256='0'*64,confirm_start=True)
        existing=NS(id=uuid4(),manifest_sha256='a'*64,request_sha256=digest(data.model_dump(mode='json')))
        session=MagicMock();session.scalar.return_value=existing
        with patch.object(service.SessionLocal,'begin',return_value=nullcontext(session)),patch.object(service,'freeze') as freeze:
            self.assertEqual(service.start(data)['id'],existing.id);freeze.assert_not_called()

    def test_native_requires_explicit_authorization(self):
        manifest={'needs_model':True}
        data=ExperimentStart(**draft().model_dump(),request_key=uuid4(),preview_sha256=digest(manifest),confirm_start=True)
        session=MagicMock();session.scalar.return_value=None
        with patch.object(service.SessionLocal,'begin',return_value=nullcontext(session)),patch.object(service,'freeze',return_value=manifest):
            with self.assertRaises(RunConflictError):service.start(data)

    def test_active_preparation_fence(self):
        session=MagicMock();session.scalar.return_value=uuid4()
        with self.assertRaises(RunConflictError):service.assert_no_preparation(session)

    def test_budget_and_confirmation_constraints(self):
        with self.assertRaises(ValidationError):draft(repetitions=0)
        with self.assertRaises(ValidationError):draft(timeout_seconds=3601)
        with self.assertRaises(ValidationError):
            ExperimentStart(**draft().model_dump(),request_key=uuid4(),preview_sha256='0'*64,confirm_start=False)

    def test_preparation_failure_is_retained_without_run(self):
        from backend.app.services import experiment_preparation as prep
        from backend.app.db.models.platform_experiment import ExperimentMember,PlatformExperiment
        token=uuid4(); member=NS(active_token=token,experiment_id=uuid4(),run_id=None)
        session=MagicMock();session.get.side_effect=lambda model,key,**kw: member if model is ExperimentMember else (NS(cancel_requested=False) if model is PlatformExperiment else None)
        with patch.object(prep,'prepare',side_effect=ValueError('stale snapshot')), patch('backend.app.services.platform_container.remove_owned'), patch.object(prep.SessionLocal,'begin',return_value=nullcontext(session)):
            prep.execute_preparation({'id':uuid4(),'token':token})
        self.assertEqual(member.status,'preparation_failed');self.assertEqual(member.error_code,'ValueError')
        self.assertIsNone(member.active_token)

    def test_preparation_cleanup_uncertain_blocks_replay(self):
        from backend.app.services import experiment_preparation as prep
        from backend.app.db.models.platform_experiment import ExperimentMember,PlatformExperiment
        token=uuid4();member=NS(active_token=token,experiment_id=uuid4(),run_id=None)
        session=MagicMock();session.get.side_effect=lambda model,key,**kw: member if model is ExperimentMember else (NS(cancel_requested=False) if model is PlatformExperiment else None)
        with patch.object(prep,'prepare',side_effect=ValueError('synthetic')), patch('backend.app.services.platform_container.remove_owned',side_effect=RuntimeError('uncertain')), patch.object(prep.SessionLocal,'begin',return_value=nullcontext(session)):
            prep.execute_preparation({'id':uuid4(),'token':token})
        self.assertEqual(member.status,'interrupted');self.assertEqual(member.active_token,token)
