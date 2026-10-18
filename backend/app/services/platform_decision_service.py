"""Pure quality gates: evidence insufficiency cannot become a positive release claim."""
from pydantic import ValidationError
from ..schemas.platform_decision import QualityPolicy


def assess_quality(comparison, policy):
    base = dict(scope='declared_automated_test_quality_only', policy=policy, checks=[],
                resource_status='not_assessed', recommendation=None)
    if policy is None:
        return dict(base, status='not_assessed', reason='no_preregistered_policy')
    try:
        policy = QualityPolicy.model_validate(policy)
    except ValidationError:
        return dict(base, status='insufficient_evidence', reason='invalid_frozen_policy')
    summary = comparison['summary']
    complete = (not comparison['integrity_issues'] and summary['planned_pairs'] > 0
                and summary['comparable_pairs'] == summary['planned_pairs'])
    checks = [dict(name='all_planned_pairs_comparable', actual=summary['comparable_pairs'],
                   required=summary['planned_pairs'], passed=complete)]
    if not complete:
        return dict(base, checks=checks, status='insufficient_evidence', reason='incomplete_or_invalid_pairs')
    case_count = len({p['case_index'] for p in comparison['pairs']})
    for name, actual, required, passed in (
        ('minimum_pairs', summary['comparable_pairs'], policy.min_pairs, summary['comparable_pairs'] >= policy.min_pairs),
        ('minimum_cases', case_count, policy.min_cases, case_count >= policy.min_cases),
        ('maximum_regressions', summary['counts']['regressed'], policy.max_regressions, summary['counts']['regressed'] <= policy.max_regressions),
        ('minimum_pass_delta_pp', summary['paired_pass_delta_percentage_points'], policy.min_pass_delta_pp,
         summary['paired_pass_delta_percentage_points'] >= policy.min_pass_delta_pp),
    ):
        checks.append(dict(name=name, actual=actual, required=required, passed=passed))
    return dict(base, checks=checks,
                status='meets_quality_policy' if all(c['passed'] for c in checks) else 'does_not_meet_quality_policy',
                reason='frozen_quality_checks_evaluated')
