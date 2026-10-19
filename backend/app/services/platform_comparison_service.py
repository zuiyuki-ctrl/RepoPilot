"""Read-only v2 comparisons against frozen manifests and persisted test evidence."""
from collections import Counter, defaultdict
from contextlib import nullcontext
from datetime import datetime, timezone
from sqlalchemy import select, text
from ..db.session import SessionLocal
from ..db.models import PlatformRun, PlatformRunEvent, RunEvaluation, TestRun
from ..db.models.platform_experiment import PlatformExperiment, ExperimentMember
from ..schemas.platform_run import AgentRunRequest
from ..schemas.platform_evaluation import EvaluationInput
from ..schemas.run_config import AgentRunConfig
from .experiment_contract_service import digest
from .platform_evaluation_service import evaluate_run
from .platform_experiment_service import differences

ARMS = ('baseline', 'candidate')


def manifest_issues(manifest, expected_hash):
    issues = []
    if digest(manifest) != expected_hash:
        issues.append('manifest_hash_mismatch')
    if manifest.get('schema_version') != 1:
        issues.append('unsupported_manifest_version')
    try:
        for row in [manifest['suite'], *manifest['agents'].values()]:
            if digest(row['descriptor']) != row['content_sha256']:
                issues.append('registered_content_hash_mismatch')
        configs = [{k: v for k, v in manifest['agents'][arm]['descriptor'].items()
                    if k not in ('name', 'version')} for arm in ARMS]
        for config in configs:
            if config['adapter'] == 'native':
                config['native'] = {**config['native'], 'runtime_fingerprint': config['implementation_sha256']}
        changed = differences(*configs)
        if changed != manifest['changed_fields']:
            issues.append('changed_fields_mismatch')
        mode = manifest['draft']['mode']
        if mode not in ('controlled', 'benchmark'):
            issues.append('unsupported_comparison_mode')
        if mode == 'controlled' and (not changed or set(changed) != set(manifest['draft']['changed_fields'])
                or configs[0]['adapter'] != configs[1]['adapter']
                or any(p in ('implementation_sha256', 'process.image', 'declared_capabilities') for p in changed)):
            issues.append('controlled_conditions_invalid')
    except (KeyError, TypeError, ValueError):
        issues.append('manifest_fields_invalid')
    return sorted(set(issues))


def verify_request(run, member, manifest):
    request = AgentRunRequest.model_validate(run.request)
    binding = manifest['suite']['descriptor']['cases'][member.case_index]
    case = binding['case']
    agent = manifest['agents'][member.arm]['descriptor']
    config = agent['process'] if agent['adapter'] == 'process' else AgentRunConfig.model_validate(
        {**agent['native'], 'runtime_fingerprint': agent['implementation_sha256']}).model_dump(mode='json')
    implementation = (config['image'].removeprefix('sha256:') if agent['adapter'] == 'process'
                      else agent['implementation_sha256'])
    expected_identity = dict(name=agent['name'], version=agent['version'], adapter=agent['adapter'],
                             implementation_sha256=implementation)
    environment = digest(dict(image=binding['test_image'], timeout_seconds=120,
                              runner_sha256=manifest['runner_sha256']))
    expected_budget = dict(timeout_seconds=manifest['draft']['timeout_seconds'], max_tokens=None,
                           token_enforcement='advisory',
                           max_tool_calls=config['max_tool_calls'] if agent['adapter'] == 'native' else None)
    valid = (request.run_id == run.id == member.run_id == member.id
             and run.request_sha256 == digest(dict(request=run.request, repository_id=str(run.repository_id),
                  legacy_task_id=str(run.legacy_task_id) if run.legacy_task_id else None))
             and request.agent.model_dump(mode='json') == expected_identity
             and request.config_sha256 == digest(config)
             and request.case_id == case['case_id'] and request.case_version == case['case_version']
             and request.case_sha256 == digest(case) and request.task_type == case['task_type']
             and request.repository_commit == case['repository_commit']
             and request.task_description == case['user_request']
             and request.editable_files == case['editable_files']
             and request.rule_sha256 == digest(binding['acceptance'])
             and request.environment_sha256 == environment
             and request.budget.model_dump() == expected_budget)
    if not valid:
        raise ValueError('Frozen request mismatch')
    return request


def verify_evaluation(run, request, evaluation, tests):
    evidence = EvaluationInput.model_validate(evaluation.evidence)
    decision = evaluate_run(evidence)
    if (evaluation.run_id != run.id or evidence.run_id != run.id
            or decision.evidence_sha256 != evaluation.evidence_sha256
            or decision.rule_sha256 != evaluation.rule_sha256
            or decision.rule_sha256 != request.rule_sha256
            or decision.outcome != evaluation.outcome or decision.outcome != run.evaluation_outcome
            or decision.reason != evaluation.reason
            or evidence.execution_status != run.execution_status
            or (evidence.case_id, evidence.case_version, evidence.case_sha256, evidence.task_type) !=
               (request.case_id, request.case_version, request.case_sha256, request.task_type)
            or evidence.environment_sha256 != request.environment_sha256
            or evidence.initial_snapshot_hash != request.initial_snapshot_hash
            or evaluation.test_run_id != (evidence.final_test.test_run_id if evidence.final_test else None)):
        raise ValueError('Evaluation binding mismatch')
    for test in (evidence.baseline_test, evidence.final_test):
        if test is None:
            continue
        stored = tests.get(test.test_run_id)
        if stored is None or stored.run_id != run.id or test.run_id != run.id:
            raise ValueError('TestRun ownership mismatch')
        if any(getattr(stored, field) != getattr(test, field) for field in
               ('snapshot_hash', 'status', 'exit_code', 'timed_out', 'error', 'test_report', 'image', 'timeout_seconds')):
            raise ValueError('TestRun content mismatch')
    return evidence


def member_summary(member, run, evaluations, tests, manifest):
    row = dict(member_id=str(member.id), sequence=member.sequence, arm=member.arm,
        case_index=member.case_index, repetition=member.repetition, preparation_status=member.status,
        error_code=member.error_code, run_id=str(member.run_id) if member.run_id else None,
        started=bool(run and run.started_at), lifecycle=run.lifecycle if run else None,
        started_at=run.started_at.isoformat() if run and run.started_at else None,
        completed_at=run.completed_at.isoformat() if run and run.completed_at else None,
        execution_status=run.execution_status if run else None,
        reported_outcome=run.evaluation_outcome if run else None, verified_outcome=None,
        evidence_status='pending', issues=[], initial_snapshot_hash=None,
        evaluation_id=None, evidence_sha256=None, baseline_test_run_id=None, final_test_run_id=None)
    if run is None:
        row['evidence_status'] = 'not_started' if member.run_id is None else 'invalid'
        row['issues'] = [member.status if member.run_id is None else 'run_record_missing']
        return row
    try:
        request = verify_request(run, member, manifest)
        row['initial_snapshot_hash'] = request.initial_snapshot_hash
    except (KeyError, ValueError, TypeError, IndexError):
        row.update(evidence_status='invalid', issues=['frozen_request_mismatch'])
        return row
    if run.lifecycle not in ('finished', 'interrupted'):
        return row
    if len(evaluations) != 1:
        row.update(evidence_status='missing' if not evaluations else 'invalid',
                   issues=['evaluation_missing' if not evaluations else 'multiple_evaluations'])
        return row
    evaluation = evaluations[0]
    try:
        evidence = verify_evaluation(run, request, evaluation, tests)
    except (KeyError, ValueError, TypeError):
        row.update(evidence_status='invalid', issues=['evaluation_or_test_binding_invalid'])
        return row
    row.update(evidence_status='verified', verified_outcome=evaluation.outcome,
        evaluation_id=str(evaluation.id), evidence_sha256=evaluation.evidence_sha256,
        baseline_test_run_id=str(evidence.baseline_test.test_run_id) if evidence.baseline_test else None,
        final_test_run_id=str(evidence.final_test.test_run_id) if evidence.final_test else None)
    return row


def build_comparison(experiment, members, runs, evaluations, tests):
    manifest = experiment.manifest
    issues = manifest_issues(manifest, experiment.manifest_sha256)
    grouped = defaultdict(list)
    rows = [member_summary(m, runs.get(m.run_id), evaluations.get(m.run_id, []), tests, manifest) for m in members]
    for row in rows:
        grouped[(row['case_index'], row['repetition'], row['arm'])].append(row)
    cases = manifest.get('suite', {}).get('descriptor', {}).get('cases', [])
    repetitions = manifest.get('draft', {}).get('repetitions', 0)
    if not cases or type(repetitions) is not int or not 1 <= repetitions <= 5:
        issues.append('planned_pairs_invalid')
        repetitions = 0
    expected = {(i, r, arm) for i in range(len(cases)) for r in range(1, repetitions+1) for arm in ARMS}
    if set(grouped) - expected:
        issues.append('unexpected_members')
    if len(members) != manifest.get('run_count') or len(expected) != manifest.get('run_count'):
        issues.append('member_count_mismatch')
    pairs = []
    for index, binding in enumerate(cases):
        for repetition in range(1, repetitions+1):
            pair = dict(case_index=index, case_id=binding.get('case', {}).get('case_id'),
                        repetition=repetition, classification='undecided', reasons=list(issues))
            for arm in ARMS:
                candidates = grouped[(index, repetition, arm)]
                pair[arm] = candidates[0] if len(candidates) == 1 else None
                if len(candidates) != 1:
                    pair['reasons'].append(f'{arm}_member_missing_or_duplicate')
            left, right = pair['baseline'], pair['candidate']
            if pair['reasons']:
                pair['classification'] = 'non_comparable'
            elif any(row['evidence_status'] == 'invalid' for row in (left, right)):
                pair.update(classification='non_comparable', reasons=['invalid_member_evidence'])
            elif (left['initial_snapshot_hash'] and right['initial_snapshot_hash']
                  and left['initial_snapshot_hash'] != right['initial_snapshot_hash']):
                pair.update(classification='non_comparable', reasons=['initial_snapshot_mismatch'])
            elif not all(row['started'] and row['preparation_status'] == 'ready' and row['lifecycle'] == 'finished'
                         and row['evidence_status'] == 'verified'
                         and row['verified_outcome'] in ('passed', 'not_passed') for row in (left, right)):
                pair['reasons'] = ['both_started_and_verified_outcomes_required']
            else:
                passed = [row['verified_outcome'] == 'passed' for row in (left, right)]
                pair['classification'] = {(False, True): 'improved', (True, False): 'regressed',
                    (True, True): 'both_passed', (False, False): 'both_not_passed'}[tuple(passed)]
            pairs.append(pair)
    counts = Counter(pair['classification'] for pair in pairs)
    comparable = sum(counts[k] for k in ('improved', 'regressed', 'both_passed', 'both_not_passed'))
    groups = {}
    for arm in ARMS:
        arm_rows = [row for row in rows if row['arm'] == arm]
        started = [row for row in arm_rows if row['started']]
        passed = sum(row['evidence_status'] == 'verified' and row['verified_outcome'] == 'passed' for row in started) if not issues else 0
        groups[arm] = dict(planned=len(cases)*repetitions, members=len(arm_rows), started=len(started),
            preparation_failed=sum(row['preparation_status'] == 'preparation_failed' for row in arm_rows),
            not_started=sum(not row['started'] for row in arm_rows),
            verified_passed=passed if not issues else None,
            observed_pass_fraction=passed/len(started) if started and not issues else None,
            unresolved_started=sum(row['evidence_status'] != 'verified' or row['verified_outcome'] not in ('passed','not_passed') for row in started),
            preparation_counts=dict(Counter(row['preparation_status'] for row in arm_rows)))
    result = dict(schema_version=1, experiment_id=str(experiment.id), manifest_sha256=experiment.manifest_sha256,
        mode=manifest.get('draft', {}).get('mode'), changed_fields=manifest.get('changed_fields', []),
        integrity_issues=sorted(set(issues)), pairs=pairs, members=rows, groups=groups,
        summary=dict(planned_pairs=len(pairs), comparable_pairs=comparable,
            counts={key: counts[key] for key in ('improved','regressed','both_passed','both_not_passed','undecided','non_comparable')},
            paired_pass_delta_percentage_points=(counts['improved']-counts['regressed'])*100/comparable if comparable else None),
        resource_comparison=dict(status='not_assessed', tokens=None, cost=None, latency=None),
        decision=dict(status='not_assessed', reason='release_policy_not_implemented'),
        limitations=['Only persisted declared automated-test outcomes are compared; no workspace re-read',
            'Observed pass fraction uses every started Run, including unresolved Runs; it is not a final success estimate',
            'Paired delta uses only comparable pairs; check excluded pairs and preparation failures',
            'Benchmark may change multiple variables; no causal attribution or automatic release recommendation',
            'Repeated fixtures are not independent evidence of general Agent quality',
            'Diff artifact bytes and full Trace completeness are not verified by this comparison'])
    from .platform_decision_service import assess_quality
    result['decision'] = assess_quality(result, manifest.get('draft', {}).get('decision_policy'))
    result['comparison_sha256'] = digest(result)
    return result


def get_comparison(experiment_id, *, session=None):
    supplied = session is not None
    with (nullcontext(session) if supplied else SessionLocal()) as session:
        # All member/run/test reads share one PostgreSQL snapshot while workers may advance.
        if not supplied:
            session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        experiment = session.get(PlatformExperiment, experiment_id)
        if experiment is None:
            return None
        members = list(session.scalars(select(ExperimentMember).where(
            ExperimentMember.experiment_id == experiment_id).order_by(ExperimentMember.sequence)))
        ids = [m.run_id for m in members if m.run_id]
        runs = {r.id: r for r in session.scalars(select(PlatformRun).where(PlatformRun.id.in_(ids)))}
        evaluations = defaultdict(list)
        for item in session.scalars(select(RunEvaluation).where(RunEvaluation.run_id.in_(ids)).order_by(RunEvaluation.id)):
            evaluations[item.run_id].append(item)
        tests = {t.id: t for t in session.scalars(select(TestRun).where(TestRun.run_id.in_(ids)))}
        result = build_comparison(experiment, members, runs, evaluations, tests)
        from .platform_resource_service import run_resources, compare_resources
        events = defaultdict(list)
        for event in session.scalars(select(PlatformRunEvent).where(PlatformRunEvent.run_id.in_(ids))
                                     .order_by(PlatformRunEvent.run_id, PlatformRunEvent.sequence)):
            events[event.run_id].append(event)
        from .gateway_observation_service import load_ledgers
        ledgers = load_ledgers(session, runs.keys())
        resources = {str(run.id): run_resources(run, events[run.id], gateway=ledgers[run.id]) for run in runs.values()}
        result['resource_comparison'] = compare_resources(result, resources)
        result.pop('comparison_sha256')
        result['comparison_sha256'] = digest(result)
        result['observed_at'] = datetime.now(timezone.utc).isoformat()
        return result
