export interface ComparedMember {
  member_id: string; run_id: string | null; preparation_status: string; started: boolean
  reported_outcome: string | null; verified_outcome: string | null; evidence_status: string
  issues: string[]; evaluation_id: string | null; evidence_sha256: string | null
  baseline_test_run_id: string | null; final_test_run_id: string | null
}
export interface ExperimentComparison {
  resource_comparison: {
    status: string; cost: {status:string;total:string|null;currency:string|null}
    metrics: Record<string,{baseline_mean:number|null;candidate_mean:number|null;delta:number|null;relative_percent:number|null;valid_pairs:number;eligible_pairs:number;planned_pairs:number;coverage:number|null}>
    runs: Record<string,unknown>
  }
  decision: QualityDecision
  experiment_id: string; mode: string; comparison_sha256: string; observed_at: string
  integrity_issues: string[]; changed_fields: string[]
  summary: { planned_pairs: number; comparable_pairs: number; counts: Record<string, number>; paired_pass_delta_percentage_points: number | null }
  groups: Record<string, { planned: number; members: number; started: number; not_started: number; preparation_failed: number
    verified_passed: number | null; unresolved_started: number; observed_pass_fraction: number | null }>
  pairs: { case_index: number; case_id: string; repetition: number; classification: string; reasons: string[]
    baseline: ComparedMember | null; candidate: ComparedMember | null }[]
}

export interface QualityDecision {
  status: string; reason: string; scope: string
  checks: { name: string; actual: number; required: number; passed: boolean }[]
}
export interface ExperimentReview {
  id: string; comparison_sha256: string; reviewer: string; action: string; rationale: string; created_at: string
  machine_decision: QualityDecision; snapshot: Record<string, unknown>
}
export const decisionLabels: Record<string,string> = {
  not_assessed: '未评估（没有预先声明门槛）', insufficient_evidence: '证据不足',
  meets_quality_policy: '达到本批质量门槛', does_not_meet_quality_policy: '未达到本批质量门槛',
}

export const comparisonLabels: Record<string, string> = {
  improved: '改善', regressed: '退化', both_passed: '双方通过', both_not_passed: '双方未通过',
  undecided: '待定', non_comparable: '不可比',
}
