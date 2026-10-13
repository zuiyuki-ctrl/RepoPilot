export type Scalar = string | number | boolean | null
export type Fields = Record<string, Scalar>
export type Resources = Record<'tokens' | 'estimated_cost' | 'wall_time_ms', Fields>
export interface Decision {
  verdict: string; policy_source: string; decision_sha256: string
  policy: Fields | null; expectedPairs: Fields[]; checks: Fields[]; quality: Fields
  resources: Resources | null; missingReasons: string[]; nextSteps: string[]; limitations: string[]
  review: Fields | null
}
export interface FailureAnalysis {
  status: string; termination_stage: string; primary_category: string; root_cause_status: string
  review_status: string; analysis_sha256: string; observedStages: string[]; missing: string[]
  facts: { kind: string; evidenceIds: string[] }[]
  hypotheses: { category: string; source: string; statement: string; review_status: string; evidenceIds: string[] }[]
  evidence: { id: string; source: string; reference: Fields; testCases: Fields[]; sequences: number[] }[]
  review: Fields | null
}
export const labels: Record<string, string> = {
  meets_batch_rules: '符合本批条件', does_not_meet_batch_rules: '不符合本批条件', insufficient_evidence: '证据不足',
  preregistered: '运行前冻结', exploratory: '事后探索性分析', not_configured: '未配置门槛',
  stayed_success: '保持成功', improved: '改善', regressed: '退化', both_not_success: '双方未成功',
  undecided: '未决', non_comparable: '不可比', passed: '通过', not_passed: '未通过', unknown: '未知',
  recorded_conditions_match: '已记录条件一致', different: '条件存在差异',
  adopt_candidate: '采用候选策略', keep_baseline: '保留基线', continue_experiment: '继续实验',
  pass: '满足', fail: '未满足', unreviewed: '未复核', reviewed: '已人工复核', not_requested: '未请求复核',
  decision_policy_not_configured: '尚未配置决策门槛', frozen_policies_missing_or_different: '冻结门槛缺失或不一致',
  missing_or_extra_declared_pairs: '所选配对与声明批次不一致',
  declared_batch: '声明批次完整', policy_frozen_before_preparation: '门槛早于准备', minimum_pairs: '最小样本数',
  classification_coverage: '分类覆盖率', all_pair_conditions_and_start_evidence: '条件、验收及启动证据完整',
  regressions: '最大退化数', quality_delta_pp: '最低质量百分点变化', tokens_relative_percent: 'Token 增幅上限 %',
  estimated_cost_relative_percent: '估算成本增幅上限 %', wall_time_ms_relative_percent: '墙钟时长增幅上限 %',
}
export const label = (value: unknown) => labels[String(value)] ?? (value == null ? '未记录' : String(value))
export const display = (value: unknown) => value == null ? '未记录' : String(value)
