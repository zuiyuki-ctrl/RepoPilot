"""独立规则引擎：纯输入，不访问工作区、不信任 Agent 自报成功。"""
from ..schemas.platform_evaluation import EvaluationInput, EvaluationDecision
from .experiment_contract_service import digest, test_outcomes


def platform_test_outcomes(report):
    """v2 adds platform provenance; JUnit content still passes the exact v1 integrity check."""
    if not isinstance(report, dict):
        return None
    junit = {key: value for key, value in report.items() if key != 'runner_sha256'}
    return test_outcomes(junit)


def evaluate_run(evidence: EvaluationInput) -> EvaluationDecision:
    def decision(outcome, reason):
        return EvaluationDecision(run_id=evidence.run_id, outcome=outcome, reason=reason,
            rule_sha256=digest(evidence.rule.model_dump(mode='json')),
            evidence_sha256=digest(evidence.model_dump(mode='json')))

    if evidence.execution_status in ('failed', 'timed_out', 'cancelled'):
        return decision('not_passed', 'execution_failed')
    if evidence.execution_status != 'completed':
        return decision('unknown', 'execution_not_confirmed')
    if evidence.writers_stopped is not True:
        return decision('unknown', 'writers_not_confirmed_stopped')
    if evidence.diff_within_scope is False or evidence.protected_tests_intact is False:
        return decision('not_passed', 'workspace_constraints_violated')
    if (not evidence.final_snapshot_hash or not evidence.diff_sha256
            or evidence.diff_within_scope is not True or evidence.protected_tests_intact is not True):
        return decision('unknown', 'workspace_evidence_missing')

    def linked(test, snapshot):
        if test is None:
            return False
        identity = {'image': test.image, 'timeout_seconds': test.timeout_seconds}
        if test.runner_sha256 is not None:
            identity['runner_sha256'] = test.runner_sha256
            if not test.test_report or test.test_report.get('runner_sha256') != test.runner_sha256:
                return False
        return (test is not None and test.run_id == evidence.run_id and test.snapshot_hash == snapshot
                and test.environment_sha256 == evidence.environment_sha256
                and digest(identity) == test.environment_sha256)

    final = evidence.final_test
    if not linked(final, evidence.final_snapshot_hash):
        return decision('unknown', 'final_test_binding_missing_or_different')
    if final.status == 'running':
        return decision('unknown', 'test_not_finished')
    if final.status != 'finished' or final.exit_code != 0 or final.timed_out or final.error:
        return decision('not_passed', 'test_process_failed')
    outcomes = platform_test_outcomes(final.test_report)
    if outcomes is None:
        return decision('unknown', 'test_report_invalid_or_missing')
    if any(value != 'passed' for value in outcomes.values()):
        return decision('not_passed', 'tests_not_all_passed')
    if any((t.classname, t.name) not in outcomes for t in evidence.rule.required_tests):
        return decision('unknown', 'required_tests_missing')
    if evidence.task_type == 'bug_fix':
        before = evidence.baseline_test
        if not linked(before, evidence.initial_snapshot_hash) or not evidence.rule.baseline_failure_tests:
            return decision('unknown', 'baseline_evidence_missing')
        results = platform_test_outcomes(before.test_report)
        if (before.status != 'finished' or before.exit_code != 1 or before.timed_out or before.error
                or results is None or any(v in ('errors', 'skipped') for v in results.values())
                or any(results.get((t.classname, t.name)) != 'failed' for t in evidence.rule.baseline_failure_tests)):
            return decision('unknown', 'baseline_failure_not_demonstrated')
    if evidence.rule.manual_criteria:
        return decision('unknown', 'manual_review_required')
    return decision('passed', 'declared_test_contract_satisfied')
