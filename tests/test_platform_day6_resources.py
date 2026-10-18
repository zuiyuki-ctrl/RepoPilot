from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services.platform_resource_service import run_resources, compare_resources
from backend.app.services import platform_export_service as exports
from backend.app.services.experiment_contract_service import digest


def run():
    return NS(id=uuid4(),legacy_task_id=uuid4(),lifecycle='finished',event_sequence=2,capabilities={},
        started_at=datetime(2026,10,16,tzinfo=timezone.utc),completed_at=datetime(2026,10,16,tzinfo=timezone.utc)+timedelta(seconds=30))


def events(run, total=5):
    def event(sequence, suffix, payload):
        return NS(sequence=sequence,event_type='MODEL_CALL_'+suffix,payload={
            'legacy_task_id':str(run.legacy_task_id),'node_name':'model','native':payload})
    return [event(1,'STARTED',{'call_id':'a'}),event(2,'COMPLETED',{'call_id':'a','model_observation':{
        'call_id':'a','request_attempted':True,'usage_status':'complete','duration_ms':100,
        'usage':{'input_tokens':2,'output_tokens':3,'total_tokens':total}}})]


def comparison():
    return dict(experiment_id=str(uuid4()),comparison_sha256='a'*64,integrity_issues=[],
        summary={'planned_pairs':2},groups={},members=[],decision={'status':'not_assessed'},limitations=[],
        resource_comparison={},pairs=[dict(case_index=i,repetition=1,classification='improved',
            baseline={'run_id':f'b{i}'},candidate={'run_id':f'c{i}'}) for i in range(2)])


class ResourceTests(TestCase):
    def test_no_events_unknown_not_zero(self):
        value=run_resources(run(),[])
        self.assertIsNone(value['tokens']['total_tokens'])
        self.assertEqual(value['source'],'not_recorded')
        self.assertIsNone(value['cost']['total'])
        self.assertIsNone(value['human_wait_ms'])

    def test_paired_native_events_only_prove_subtotal(self):
        row=run();value=run_resources(row,events(row))
        self.assertEqual(value['tokens']['known_total_tokens'],5)
        self.assertIsNone(value['tokens']['total_tokens'])
        self.assertEqual(value['wall_clock_ms'],30000)

    def test_complete_scope_requires_verified_capability_and_contiguous_events(self):
        row=run();row.capabilities={'model_usage':dict(validated=True,availability='available',
            expected_records=2,recorded_records=2,evidence_sequences=[1,2])}
        self.assertEqual(run_resources(row,events(row))['tokens']['total_tokens'],5)
        row.event_sequence=3
        self.assertIsNone(run_resources(row,events(row))['tokens']['total_tokens'])

    def test_missing_start_and_inconsistent_usage_not_counted(self):
        row=run()
        for observed in (events(row)[1:],events(row,total=99)):
            value=run_resources(row,observed)
            self.assertEqual(value['tokens']['known_total_tokens'],0)
            self.assertIsNone(value['tokens']['total_tokens'])

    def test_cross_run_native_record_rejected(self):
        row=run();observed=events(row);observed[0].payload['legacy_task_id']=str(uuid4())
        value=run_resources(row,observed)
        self.assertTrue(value['invalid_observations'])
        self.assertIsNone(value['tokens']['total_tokens'])

    def test_external_self_report_stays_partial_and_duplicate_call_not_summed(self):
        row=run()
        event=NS(sequence=1,event_type='PROCESS_TRACE',payload=dict(protocol_version=1,event_id='e',
            run_id=str(row.id),kind='model_call',call_id='a',input_tokens=2,output_tokens=3,total_tokens=5))
        value=run_resources(row,[event])
        self.assertEqual(value['source'],'agent_reported')
        self.assertEqual(value['tokens']['known_total_tokens'],5)
        self.assertIsNone(value['tokens']['total_tokens'])
        self.assertEqual(run_resources(row,[event,event])['tokens']['known_total_tokens'],0)

    def test_resource_means_use_same_pairs_not_separate_arm_cohorts(self):
        resources={key:dict(tokens={'total_tokens':tokens},wall_clock_ms=duration)
            for key,tokens,duration in [('b0',10,100),('c0',20,200),('b1',1000,400),('c1',None,800)]}
        value=compare_resources(comparison(),resources)
        tokens=value['metrics']['total_tokens']
        self.assertEqual((tokens['baseline_mean'],tokens['candidate_mean']),(10,20))
        self.assertEqual(tokens['valid_pairs'],1)
        self.assertEqual(value['metrics']['wall_clock_ms']['valid_pairs'],2)

    def test_noncomparable_pairs_excluded_and_zero_relative_not_infinite(self):
        data=comparison();data['pairs'][1]['classification']='non_comparable'
        resources={key:dict(tokens={'total_tokens':0},wall_clock_ms=0) for key in ('b0','c0','b1','c1')}
        value=compare_resources(data,resources)['metrics']['total_tokens']
        self.assertEqual(value['valid_pairs'],1)
        self.assertIsNone(value['relative_percent'])
        self.assertEqual(value['relative_status'],'baseline_zero')

    def test_export_snapshot_preserves_old_review_and_hash(self):
        data=comparison();session=MagicMock();session.get.return_value=NS(manifest={'draft':{}},manifest_sha256='b'*64)
        old={'decision':{'status':'old'},'comparison_sha256':'c'*64}
        session.scalars.return_value=[NS(id=uuid4(),reviewer='<script>',action='keep_baseline',rationale='reason',
            created_at=datetime.now(timezone.utc),comparison_sha256='c'*64,snapshot=old)]
        with patch.object(exports,'SessionLocal') as factory,patch.object(exports,'get_comparison',return_value=data):
            factory.return_value.__enter__.return_value=session
            report=exports.export_report(uuid4())
        self.assertEqual(report['reviews'][0]['snapshot'],old)
        self.assertFalse(report['reviews'][0]['matches_current_comparison'])
        expected=report['report_sha256'];self.assertEqual(digest({k:v for k,v in report.items() if k!='report_sha256'}),expected)
        markdown=exports.render_markdown(report)
        self.assertNotIn('\n<script>',markdown)
        self.assertIn('    ',markdown)

    def test_export_routes_and_missing(self):
        data=comparison()
        report=dict(experiment_id=data['experiment_id'],exported_at='now',manifest={},manifest_sha256='b'*64,
                    comparison=data,reviews=[],limitations=[],report_sha256='d'*64)
        with TestClient(app) as client,patch.object(exports,'export_report',return_value=report) as read:
            url=f'/api/v2/experiments/{data["experiment_id"]}/export'
            for format in ('json','markdown'):
                response=client.get(url,params={'format':format})
                self.assertEqual(response.status_code,200)
                self.assertIn('attachment',response.headers['content-disposition'])
                self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertEqual(client.get(url+'?format=xml').status_code,422)
            read.return_value=None
            self.assertEqual(client.get(url).status_code,404)
