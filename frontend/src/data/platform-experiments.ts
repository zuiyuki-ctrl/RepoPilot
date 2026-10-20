export interface CatalogVersion { id: string; name: string; version: string; status: string }
export interface ExperimentListItem { id: string; name: string; created_at?: string | null; cancel_requested?: boolean; manifest_sha256?: string }
export interface ExperimentMember {
  id: string; sequence: number; case_index: number; repetition: number; arm: string; status: string
  error_code: string | null; run_id: string | null; lifecycle: string | null
  execution_status: string | null; evaluation_outcome: string | null
}
export interface ExperimentDetail {
  id: string; status: string; manifest_sha256: string; manifest: Record<string, unknown>
  members: ExperimentMember[]; cancel_requested: boolean; created_at?: string | null
}
export interface QualityPolicy { version: number; min_pairs: number; min_cases: number; max_regressions: number; min_pass_delta_pp: number }
export interface ExperimentDraft {
  name: string; suite_id: string; baseline_agent_id: string; candidate_agent_id: string
  mode: string; changed_fields: string[]; repetitions: number; timeout_seconds: number
  order: string; intervention: string; decision_policy: QualityPolicy | null
}
export interface ExperimentPreview {
  preview_sha256: string
  manifest: { run_count: number; needs_model: boolean; changed_fields: string[]; [key: string]: unknown }
}
export interface ReviewForm { reviewer: string; action: string; rationale: string }
export const reviewActions: Record<string, string> = { adopt_candidate: '采用 Candidate', keep_baseline: '保留 Baseline', continue_experiment: '继续实验' }
export function draftBody(draft: ExperimentDraft, fields: string, enabled: boolean, policy: QualityPolicy): ExperimentDraft {
  return { ...draft, changed_fields: fields.split(',').map(field => field.trim()).filter(Boolean), decision_policy: enabled ? { ...policy } : null }
}
export function validDraft(draft: ExperimentDraft): boolean {
  const integer = (value: number, min: number, max: number) => Number.isInteger(value) && value >= min && value <= max
  const p = draft.decision_policy
  return Boolean(draft.name.trim() && draft.name.length <= 100 && draft.suite_id && draft.baseline_agent_id && draft.candidate_agent_id
    && ['benchmark', 'controlled'].includes(draft.mode) && ['baseline_first', 'candidate_first'].includes(draft.order)
    && integer(draft.repetitions, 1, 5) && integer(draft.timeout_seconds, 1, 3600)
    && draft.changed_fields.length <= 20 && new Set(draft.changed_fields).size === draft.changed_fields.length
    && (!p || p.version === 1 && integer(p.min_pairs, 1, 20) && integer(p.min_cases, 1, 20) && integer(p.max_regressions, 0, 20)
      && Number.isFinite(p.min_pass_delta_pp) && p.min_pass_delta_pp >= -100 && p.min_pass_delta_pp <= 100))
}
export function previewMatches(frozen: ExperimentDraft | null, current: ExperimentDraft): boolean {
  return frozen !== null && JSON.stringify(frozen) === JSON.stringify(current)
}
export function canStartExperiment(state: { busy: boolean; connected: boolean; current: boolean; confirmed: boolean; allowModel: boolean; preview: ExperimentPreview | null }): boolean {
  return !state.busy && state.connected && state.current && state.confirmed && state.preview !== null
    && (state.preview.manifest.needs_model === false || state.preview.manifest.needs_model === true && state.allowModel)
}
export function canSaveExperimentReview(state: { busy: boolean; loading: boolean; confirmed: boolean; targetHash: string | null; currentHash: string | null; form: ReviewForm }): boolean {
  return !state.busy && !state.loading && state.confirmed && Boolean(state.targetHash && state.targetHash === state.currentHash)
    && Boolean(state.form.reviewer.trim() && state.form.rationale.trim()) && state.form.reviewer.length <= 100
    && state.form.rationale.length <= 2000 && Object.hasOwn(reviewActions, state.form.action)
}
export function canCancelExperiment(detail: ExperimentDetail | null, busy: boolean, loading: boolean): boolean {
  return !busy && !loading && detail !== null && !detail.cancel_requested && detail.status !== 'settled'
}
export async function experimentApi<T>(path: string, body?: unknown): Promise<T> {
  try {
    const response = await fetch('/api/v2/' + path, { method: body === undefined ? 'GET' : 'POST', cache: 'no-store',
      headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(20000) })
    if (!response.headers.get('content-type')?.includes('application/json')) throw new Error(`未收到实验 API JSON（HTTP ${response.status}），请检查后端连接。`)
    const data = await response.json()
    if (!response.ok) throw new Error(`${response.status}: ${typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)}`)
    return data as T
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'TimeoutError') throw new Error('实验请求超时。涉及写入时请先核对记录，不会自动重发。')
    if (cause instanceof TypeError) throw new Error('无法连接实验服务，请检查后端连接。')
    throw cause
  }
}
