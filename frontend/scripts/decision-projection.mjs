import { redactText } from './run-detail.mjs'

// 只投影协议内的展示字段；不转发任意配置、日志、XML、源码和本机路径。
const text = value => typeof value === 'string' ? redactText(value)
  .replace(/[A-Za-z]:[\\/][^\s"<>]+/g, '[本机路径]')
  .replace(/\/(?:Users|home|tmp|private|mnt)\/[^\s"<>]+/g, '[本机路径]') : value
const list = value => Array.isArray(value) ? value : []
const scalar = value => value == null ? null : ['string', 'number', 'boolean'].includes(typeof value) ? text(value) : '[结构化字段]'
const pick = (object, keys) => Object.fromEntries(keys.map(key => [key, scalar(object?.[key])]))

export function projectResources(value) {
  if (!value) return null
  return Object.fromEntries(['tokens', 'estimated_cost', 'wall_time_ms'].map(key => [key,
    pick(value[key], ['baseline', 'candidate', 'absolute', 'relative_percent', 'status', 'valid_pairs', 'coverage', 'currency'])]))
}

export function projectDecision(value) {
  if (!value) return null
  return {
    ...pick(value, ['verdict', 'policy_source', 'decision_sha256']),
    policy: value.policy ? pick(value.policy, ['version', 'declared_at', 'min_pairs', 'min_classification_coverage',
      'max_regressions', 'min_quality_delta_pp', 'min_resource_coverage', 'max_token_increase_percent',
      'max_cost_increase_percent', 'max_wall_time_increase_percent', 'cost_currency']) : null,
    expectedPairs: list(value.policy?.expected_pairs).map(p => pick(p, ['case_id', 'case_version', 'repeat_index'])),
    checks: list(value.checks).map(c => pick(c, ['name', 'observed', 'threshold', 'status'])),
    quality: pick(value.quality, ['delta_pp', 'classified_started_pairs', 'selected_pairs', 'coverage', 'regressions']),
    resources: projectResources(value.resource_deltas),
    missingReasons: list(value.missing_reasons).map(text), nextSteps: list(value.next_steps).map(text),
    limitations: list(value.limitations).map(text),
    review: value.review ? pick(value.review, ['action', 'reviewer', 'recorded_at', 'rationale']) : null,
  }
}

export function projectPair(pair) {
  return {
    repeatIndex: pair.repeat_index ?? 1,
    analysis: pair.analysis ? pick(pair.analysis, ['category', 'reason', 'both_test_processes_passed']) : null,
    comparability: pair.comparability ? {
      status: scalar(pair.comparability.status), missing: list(pair.comparability.missing).map(text),
      differences: list(pair.comparability.differences).map(d => pick(d, ['field', 'baseline', 'candidate', 'expected', 'actual'])),
    } : null,
    resources: projectResources(pair.resource_deltas),
  }
}

export function projectRun(run) {
  const analysis = run.failure_analysis
  return {
    acceptance: run.acceptance ? pick(run.acceptance, ['outcome', 'reason', 'rule_version', 'scope']) : null,
    metrics: run.metrics ? {
      ...pick(run.metrics, ['started', 'event_scope_complete', 'wall_clock_ms']),
      resources: pick(run.metrics.resources, ['status', 'total_tokens', 'known_total_tokens', 'usage_coverage',
        'usage_known_calls', 'usage_expected_calls', 'scope_complete']),
      cost: pick(run.cost, ['status', 'total', 'known_subtotal', 'currency']),
      tests: { ...pick(run.metrics.tests, ['report_status', 'source', 'test_run_id']),
        counts: run.metrics.tests?.counts ? pick(run.metrics.tests.counts, ['passed', 'failed', 'errors', 'skipped']) : null },
    } : null,
    failureAnalysis: analysis ? {
      ...pick(analysis, ['status', 'termination_stage', 'primary_category', 'root_cause_status', 'review_status', 'analysis_sha256']),
      observedStages: list(analysis.observed_stages).map(text), missing: list(analysis.missing_evidence).map(text),
      facts: list(analysis.facts).map(f => ({ kind: scalar(f.kind), evidenceIds: list(f.evidence_ids).map(text) })),
      hypotheses: list(analysis.hypotheses).map(h => ({ ...pick(h, ['category', 'source', 'statement', 'review_status']),
        evidenceIds: list(h.evidence_ids).map(text) })),
      evidence: list(analysis.evidence).map(e => ({ ...pick(e, ['id', 'source']),
        reference: pick(e.value, ['id', 'sequence', 'event_sequence', 'event_type', 'sha256', 'snapshot_hash', 'phase', 'failure_stage', 'error_type']),
        testCases: list(e.value?.nonpassing_tests).map(t => pick(t, ['classname', 'name', 'outcome'])),
        sequences: list(e.value?.finished_sequences).map(scalar),
      })),
      review: analysis.review ? pick(analysis.review, ['reviewer', 'recorded_at', 'rationale']) : null,
    } : null,
  }
}
