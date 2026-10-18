from contextlib import nullcontext
from copy import deepcopy
from io import StringIO
import importlib.util
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.app.main import app
from backend.app.schemas.platform_decision import QualityPolicy, ExperimentReviewRequest
from backend.app.schemas.platform_experiment import ExperimentDraft
from backend.app.services.platform_decision_service import assess_quality
from backend.app.services import platform_review_service as reviews
from backend.app.services import platform_experiment_service as experiments
from backend.app.services.experiment_contract_service import digest
from backend.app.services.run_lifecycle import RunConflictError


POLICY = dict(version=1,min_pairs=2,min_cases=2,max_regressions=0,min_pass_delta_pp=0)


def comparison():
    return dict(comparison_sha256='a'*64,observed_at='today',integrity_issues=[],
        summary=dict(planned_pairs=2,comparable_pairs=2,counts={'regressed':0},paired_pass_delta_percentage_points=50),
        pairs=[{'case_index':0},{'case_index':1}],decision={'status':'not_assessed'})


def request(**changes):
    return ExperimentReviewRequest(**{**dict(request_key=uuid4(),comparison_sha256='a'*64,reviewer='operator',
        action='continue_experiment',rationale='Need more cases'),**changes})


class DecisionTests(TestCase):
    def test_frozen_policy_pass_and_each_failed_gate(self):
        self.assertEqual(assess_quality(comparison(),POLICY)['status'],'meets_quality_policy')
        for changed in (dict(min_pairs=3),dict(min_cases=3),dict(min_pass_delta_pp=60)):
            self.assertEqual(assess_quality(comparison(),{**POLICY,**changed})['status'],'does_not_meet_quality_policy')
        data=comparison();data['summary']['counts']['regressed']=1
        self.assertEqual(assess_quality(data,POLICY)['status'],'does_not_meet_quality_policy')

    def test_partial_or_invalid_never_positive(self):
        for changed in ('partial','invalid','empty'):
            data=comparison()
            if changed=='partial':data['summary']['comparable_pairs']=1
            if changed=='invalid':data['integrity_issues']=['broken']
            if changed=='empty':data['summary'].update(planned_pairs=0,comparable_pairs=0)
            self.assertEqual(assess_quality(data,POLICY)['status'],'insufficient_evidence')

    def test_repeat_is_not_a_new_case(self):
        data=comparison();data['pairs']=[{'case_index':0},{'case_index':0}]
        self.assertEqual(assess_quality(data,POLICY)['status'],'does_not_meet_quality_policy')

    def test_old_experiment_has_no_retroactive_policy(self):
        self.assertEqual(assess_quality(comparison(),None)['reason'],'no_preregistered_policy')
        draft=ExperimentDraft(name='old',suite_id=uuid4(),baseline_agent_id=uuid4(),candidate_agent_id=uuid4())
        self.assertNotIn('decision_policy',draft.model_dump(mode='json'))
        frozen=draft.model_copy(update={'decision_policy':QualityPolicy(**POLICY)})
        self.assertNotEqual(digest(draft.model_dump(mode='json')),digest(frozen.model_dump(mode='json')))

    def test_invalid_thresholds_and_resource_gates_rejected(self):
        for changes in (dict(min_pairs=0),dict(min_pass_delta_pp=float('nan')),dict(max_cost=3)):
            with self.assertRaises(ValidationError):QualityPolicy(**{**POLICY,**changes})
        self.assertEqual(assess_quality(comparison(),{})['status'],'insufficient_evidence')
        with self.assertRaises(ValidationError):request(reviewer='   ')

    def test_start_cannot_require_more_cases_than_suite(self):
        suite=NS(status='ready',validation={'cleanup_confirmed':True},descriptor={'cases':[{}]})
        agent=NS(status='ready',validation={'cleanup_confirmed':True},descriptor={'name':'a','version':'1','adapter':'process','process':{}})
        for row in (suite,agent):row.content_sha256=digest(row.descriptor)
        session=MagicMock();session.get.side_effect=[suite,agent,agent]
        draft=ExperimentDraft(name='x',suite_id=uuid4(),baseline_agent_id=uuid4(),candidate_agent_id=uuid4(),decision_policy=POLICY)
        with self.assertRaises(RunConflictError):experiments.freeze(session,draft)

    def test_review_is_separate_and_keeps_snapshot(self):
        data=request(action='adopt_candidate');session=MagicMock();session.scalar.return_value=None
        original=comparison();saved=deepcopy(original)
        with patch.object(reviews.SessionLocal,'begin',return_value=nullcontext(session)), \
                patch.object(reviews,'get_comparison',return_value=original),patch.object(reviews,'as_read',side_effect=lambda row:row):
            row=reviews.save_review(uuid4(),data)
        self.assertEqual(row.snapshot['decision']['status'],'not_assessed')
        self.assertEqual(row.action,'adopt_candidate')
        self.assertNotIn('observed_at',row.snapshot)
        self.assertEqual(original,saved)
        self.assertEqual(session.add.call_count,1)

    def test_stale_review_does_not_insert(self):
        session=MagicMock();session.scalar.return_value=None
        with patch.object(reviews.SessionLocal,'begin',return_value=nullcontext(session)),patch.object(reviews,'get_comparison',return_value=comparison()):
            with self.assertRaises(RunConflictError):reviews.save_review(uuid4(),request(comparison_sha256='b'*64))
        session.add.assert_not_called()

    def test_same_request_idempotent_and_conflicting_reuse_rejected(self):
        experiment_id=uuid4();data=request()
        previous=NS(request_sha256=digest(dict(experiment_id=str(experiment_id),request=data.model_dump(mode='json'))))
        session=MagicMock();session.scalar.return_value=previous
        with patch.object(reviews.SessionLocal,'begin',return_value=nullcontext(session)),patch.object(reviews,'get_comparison') as read,patch.object(reviews,'as_read',return_value={'id':'saved'}):
            self.assertEqual(reviews.save_review(experiment_id,data),{'id':'saved'})
            read.assert_not_called()
            with self.assertRaises(RunConflictError):reviews.save_review(experiment_id,data.model_copy(update={'rationale':'different'}))
        session.add.assert_not_called()

    def test_http_conflict_and_invalid_request(self):
        with TestClient(app) as client,patch.object(reviews,'save_review',side_effect=RunConflictError('stale')):
            url=f'/api/v2/experiments/{uuid4()}/reviews'
            self.assertEqual(client.post(url,json=request().model_dump(mode='json')).status_code,409)
            self.assertEqual(client.post(url,json={}).status_code,422)

    def test_migration_is_additive_and_protects_history(self):
        spec=importlib.util.spec_from_file_location('decision_migration','backend/migrations/versions/d716a06b0001_add_experiment_reviews.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        output=StringIO();context=MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output})
        with Operations.context(context):module.upgrade()
        self.assertIn('CREATE TABLE experiment_reviews',output.getvalue())
        self.assertNotIn('UPDATE ',output.getvalue())
        output.seek(0);output.truncate()
        with Operations.context(context):module.downgrade()
        self.assertLess(output.getvalue().index('RAISE EXCEPTION'),output.getvalue().index('DROP TABLE'))
