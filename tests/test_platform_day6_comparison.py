"""Frozen comparison fixtures; no DB, model, Docker or workspace mutation."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.schemas.platform_run import AgentRunRequest
from backend.app.schemas.run_config import AgentRunConfig
from backend.app.schemas.platform_evaluation import EvaluationInput, TestEvidence
from backend.app.schemas.experiment import ExperimentCase
from backend.app.schemas.experiment_definition import AcceptanceRule
from backend.app.services import platform_comparison_service as service
from backend.app.services.experiment_contract_service import digest
from backend.app.services.platform_evaluation_service import evaluate_run
from backend.app.services.test_report_parser import parse_test_report


IMAGE = 'sha256:'+'a'*64
RUNNER = 'b'*64


def fixture(outcomes=(False, True)):
    case = ExperimentCase(case_id='fixture', case_version='1', task_type='bug_fix', user_request='fix',
        repository_commit='a'*40, editable_files=['task.py'], protected_test_files=['tests/test_task.py'],
        test_profile='python-basic').model_dump(mode='json')
    rule = AcceptanceRule(version='1', required_tests=[{'classname':'tests.test_task','name':'test_fix'}],
        baseline_failure_tests=[{'classname':'tests.test_task','name':'test_fix'}]).model_dump(mode='json')
    binding = dict(repository_id=str(uuid4()), case=case, acceptance=rule, test_image=IMAGE)
    suite = dict(cases=[binding])
    agents = {}
    for arm in service.ARMS:
        descriptor = dict(name=arm,version='1',adapter='process',process={'image':IMAGE,'argv':[arm]})
        agents[arm] = dict(descriptor=descriptor,content_sha256=digest(descriptor))
    manifest = dict(schema_version=1, suite=dict(descriptor=suite,content_sha256=digest(suite)), agents=agents,
        draft=dict(repetitions=1,timeout_seconds=60,mode='benchmark',changed_fields=[]),
        runner_sha256=RUNNER, changed_fields=['process.argv'],run_count=2)
    experiment = NS(id=uuid4(),manifest=manifest,manifest_sha256=digest(manifest))
    members, runs, evaluations, tests = [], {}, {}, {}
    environment = digest(dict(image=IMAGE,timeout_seconds=120,runner_sha256=RUNNER))
    def test(run_id, passed, snapshot):
        xml = (f'<testsuite tests="1" failures="{0 if passed else 1}" errors="0" skipped="0">'
               '<testcase classname="tests.test_task" name="test_fix">'
               + ('' if passed else '<failure/>')+'</testcase></testsuite>').encode()
        evidence = TestEvidence(run_id=run_id,test_run_id=uuid4(),snapshot_hash=snapshot,
            environment_sha256=environment,image=IMAGE,timeout_seconds=120,runner_sha256=RUNNER,
            status='finished',exit_code=0 if passed else 1,
            test_report={**parse_test_report(xml),'runner_sha256':RUNNER})
        tests[evidence.test_run_id] = NS(**evidence.model_dump())
        return evidence
    for sequence, (arm, passed) in enumerate(zip(service.ARMS,outcomes),1):
        run_id = uuid4()
        request = AgentRunRequest(run_id=run_id,case_id='fixture',case_version='1',task_description='fix',
            repository_commit='a'*40,agent=dict(name=arm,version='1',adapter='process',implementation_sha256='a'*64),
            config_sha256=digest(agents[arm]['descriptor']['process']),case_sha256=digest(case),task_type='bug_fix',
            rule_sha256=digest(rule),environment_sha256=environment,initial_snapshot_hash='c'*64,
            editable_files=['task.py'],budget={'timeout_seconds':60})
        evidence = EvaluationInput(run_id=run_id,execution_status='completed',case_id='fixture',case_version='1',
            case_sha256=digest(case),task_type='bug_fix',rule=rule,environment_sha256=environment,
            initial_snapshot_hash='c'*64,final_snapshot_hash='d'*64,diff_sha256='e'*64,
            writers_stopped=True,diff_within_scope=True,protected_tests_intact=True,
            baseline_test=test(run_id,False,'c'*64),final_test=test(run_id,passed,'d'*64))
        result = evaluate_run(evidence)
        evaluations[run_id] = [NS(id=uuid4(),run_id=run_id,test_run_id=evidence.final_test.test_run_id,
            evidence=evidence.model_dump(mode='json'),outcome=result.outcome,reason=result.reason,
            evidence_sha256=result.evidence_sha256,rule_sha256=result.rule_sha256)]
        repository_id = uuid4()
        runs[run_id] = NS(id=run_id,repository_id=repository_id,legacy_task_id=None,request=request.model_dump(mode='json'),
            started_at=datetime.now(timezone.utc),completed_at=datetime.now(timezone.utc),
            lifecycle='finished',execution_status='completed',evaluation_outcome=result.outcome)
        runs[run_id].request_sha256=digest(dict(request=runs[run_id].request,repository_id=str(repository_id),legacy_task_id=None))
        members.append(NS(id=run_id,run_id=run_id,sequence=sequence,case_index=0,repetition=1,
                          arm=arm,status='ready',error_code=None))
    return experiment,members,runs,evaluations,tests


class ComparisonTests(TestCase):
    def test_native_derived_runtime_and_registered_strategy_are_checked(self):
        args=fixture();experiment,members,runs,_,_=args
        for arm,member in zip(service.ARMS,members):
            config=AgentRunConfig(retrieval_policy='vector' if arm=='baseline' else 'hybrid')
            descriptor=dict(name=arm,version='1',adapter='native',implementation_sha256='a'*64,
                            native=config.model_dump(mode='json'))
            experiment.manifest['agents'][arm]=dict(descriptor=descriptor,content_sha256=digest(descriptor))
            run=runs[member.run_id]
            run.request['agent']['adapter']='native'
            run.request['budget']['max_tool_calls']=4
            run.request['config_sha256']=digest(config.model_copy(update={'runtime_fingerprint':'a'*64}).model_dump(mode='json'))
            run.request_sha256=digest(dict(request=run.request,repository_id=str(run.repository_id),legacy_task_id=None))
        experiment.manifest['changed_fields']=['native.retrieval_policy']
        experiment.manifest['draft'].update(mode='controlled',changed_fields=['native.retrieval_policy'])
        experiment.manifest_sha256=digest(experiment.manifest)
        self.assertEqual(service.build_comparison(*args)['summary']['comparable_pairs'],1)

    def test_unknown_execution_remains_unknown_not_a_regression(self):
        args=fixture();run=args[2][args[1][1].run_id];evaluation=args[3][run.id][0]
        run.execution_status='unknown';run.evaluation_outcome='unknown'
        evaluation.evidence['execution_status']='unknown'
        computed=evaluate_run(EvaluationInput.model_validate(evaluation.evidence))
        evaluation.outcome=computed.outcome;evaluation.reason=computed.reason;evaluation.evidence_sha256=computed.evidence_sha256
        result=service.build_comparison(*args)
        self.assertEqual(result['pairs'][0]['classification'],'undecided')
        self.assertEqual(result['groups']['candidate']['unresolved_started'],1)

    def test_four_paired_results(self):
        for outcomes, expected in [((False,True),'improved'),((True,False),'regressed'),
                                   ((True,True),'both_passed'),((False,False),'both_not_passed')]:
            with self.subTest(outcomes=outcomes):
                result=service.build_comparison(*fixture(outcomes))
                self.assertEqual(result['pairs'][0]['classification'],expected)
                self.assertEqual(result['summary']['comparable_pairs'],1)
                self.assertEqual(result['groups']['baseline']['started'],1)
                self.assertIsNone(result['resource_comparison']['tokens'])
                self.assertEqual(result['decision']['status'],'not_assessed')

    def test_preparation_failure_retained_and_not_in_started_denominator(self):
        args=fixture();member=args[1][1];member.run_id=None;member.status='preparation_failed'
        result=service.build_comparison(*args)
        self.assertEqual(result['pairs'][0]['classification'],'undecided')
        self.assertEqual(result['groups']['candidate']['preparation_failed'],1)
        self.assertEqual(result['groups']['candidate']['started'],0)
        self.assertIsNone(result['groups']['candidate']['observed_pass_fraction'])

    def test_running_stays_in_denominator(self):
        args=fixture();run=args[2][args[1][1].run_id];run.lifecycle='running';run.evaluation_outcome='pending'
        result=service.build_comparison(*args)
        self.assertEqual(result['groups']['candidate']['started'],1)
        self.assertEqual(result['groups']['candidate']['unresolved_started'],1)
        self.assertEqual(result['summary']['comparable_pairs'],0)

    def test_missing_evaluation_not_a_failure_or_success(self):
        args=fixture();args[3].clear()
        result=service.build_comparison(*args)
        self.assertEqual(result['pairs'][0]['classification'],'undecided')
        self.assertEqual(result['members'][0]['evidence_status'],'missing')

    def test_tampered_manifest_blocks_positive_conclusion(self):
        args=fixture();args[0].manifest['draft']['timeout_seconds']=90
        result=service.build_comparison(*args)
        self.assertIn('manifest_hash_mismatch',result['integrity_issues'])
        self.assertEqual(result['summary']['comparable_pairs'],0)
        self.assertIsNone(result['groups']['candidate']['verified_passed'])

    def test_different_snapshots_not_comparable(self):
        args=fixture();run=args[2][args[1][1].run_id]
        run.request['initial_snapshot_hash']='f'*64
        run.request_sha256=digest(dict(request=run.request,repository_id=str(run.repository_id),legacy_task_id=None))
        # Remove evaluation so the independent snapshot gate is exercised.
        args[3][run.id]=[]
        result=service.build_comparison(*args)
        self.assertEqual(result['pairs'][0]['reasons'],['initial_snapshot_mismatch'])

    def test_request_agent_and_config_must_match_frozen_arm(self):
        for field in ('config_sha256','environment_sha256','rule_sha256'):
            with self.subTest(field=field):
                args=fixture();args[2][args[1][1].run_id].request[field]='f'*64
                result=service.build_comparison(*args)
                self.assertEqual(result['pairs'][0]['classification'],'non_comparable')

    def test_test_evidence_must_match_stored_row_and_ownership(self):
        for field,value in [('run_id',uuid4()),('exit_code',99)]:
            args=fixture();run_id=args[1][1].run_id
            test=args[4][args[3][run_id][0].test_run_id];setattr(test,field,value)
            result=service.build_comparison(*args)
            self.assertEqual(result['pairs'][0]['classification'],'non_comparable')
            self.assertEqual(result['members'][1]['issues'],['evaluation_or_test_binding_invalid'])

    def test_evaluation_hash_and_outcome_verified(self):
        for field,value in [('evidence_sha256','f'*64),('outcome','not_passed')]:
            args=fixture();setattr(args[3][args[1][1].run_id][0],field,value)
            self.assertEqual(service.build_comparison(*args)['summary']['comparable_pairs'],0)

    def test_duplicate_or_missing_member_not_silently_paired(self):
        args=fixture();args[1].append(deepcopy(args[1][0]))
        result=service.build_comparison(*args)
        self.assertEqual(result['pairs'][0]['classification'],'non_comparable')
        self.assertEqual(len(result['members']),3)
        args=fixture();args[1].pop()
        self.assertEqual(service.build_comparison(*args)['pairs'][0]['classification'],'non_comparable')

    def test_repetition_not_paired_with_another_attempt(self):
        args=fixture();args[1][1].repetition=2
        self.assertIn('unexpected_members',service.build_comparison(*args)['integrity_issues'])

    def test_controlled_declaration_checked_without_requiring_vector_hybrid(self):
        args=fixture();manifest=args[0].manifest
        manifest['draft'].update(mode='controlled',changed_fields=['process.argv'])
        args[0].manifest_sha256=digest(manifest)
        self.assertEqual(service.build_comparison(*args)['summary']['comparable_pairs'],1)
        manifest['draft']['changed_fields']=[];args[0].manifest_sha256=digest(manifest)
        self.assertIn('controlled_conditions_invalid',service.build_comparison(*args)['integrity_issues'])

    def test_multiple_evaluations_not_cherry_picked(self):
        args=fixture();args[3][args[1][1].run_id]*=2
        self.assertEqual(service.build_comparison(*args)['pairs'][0]['classification'],'non_comparable')

    def test_hash_deterministic_and_changes_with_evidence(self):
        args=fixture()
        first=service.build_comparison(*args)
        self.assertEqual(first['comparison_sha256'],service.build_comparison(*args)['comparison_sha256'])
        args[1][1].status='interrupted'
        self.assertNotEqual(first['comparison_sha256'],service.build_comparison(*args)['comparison_sha256'])

    def test_http_missing_and_returned_result(self):
        with TestClient(app) as client,patch.object(service,'get_comparison',return_value=None) as read:
            path=f'/api/v2/experiments/{uuid4()}/comparison'
            self.assertEqual(client.get(path).status_code,404)
            read.return_value=service.build_comparison(*fixture())
            self.assertEqual(client.get(path).json()['pairs'][0]['classification'],'improved')
