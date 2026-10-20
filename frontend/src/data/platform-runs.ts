export interface Capability {
  declared: boolean; validated: boolean
  availability: string; occurrence: string; source: string
  evidence_sequences: number[]; expected_records: number | null; recorded_records: number
}
export interface PlatformRun {
  id: string; repository_id: string; legacy_task_id: string | null
  case_id: string; case_version: string
  agent: { name: string; version: string; adapter: string }
  lifecycle: string; execution_status: string; evaluation_outcome: string; version: number
  created_at: string; started_at: string | null; completed_at: string | null
  observation: { level: string; completeness: string; capabilities: Record<string, Capability> }
}
export interface PlatformEvent { id: string; sequence: number; event_type: string; source: string; created_at: string }
export interface PlatformTraceEvent extends PlatformEvent {
  legacy_task_id: string | null; legacy_sequence: number | null; node_name: string | null
  details: Record<string, unknown>; detail_status: string; truncated: boolean
  timestamp_semantics: 'platform_recorded_at'
}
export interface PlatformTracePage {
  items: PlatformTraceEvent[]; next_after_sequence: number; through_sequence: number; has_more: boolean
}

export interface GatewayCall {
  id: string; call_id_sha256: string; status: string; usage_source: string
  evidence_source: string; usage_status: string; real_usage_eligible: boolean
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number } | null
  request_sha256: string; response_sha256: string | null; error_code: string | null
  created_at: string; dispatched_at: string | null; completed_at: string | null
  duration_ms: number | null
}
export interface GatewayLedger {
  run_id: string; grant_present: boolean; calls_reserved: number | null
  call_count: number; items: GatewayCall[]; synthetic_usage_known_calls: number
  synthetic_known_total_tokens: number; real_total_tokens: number | null
  real_known_total_tokens: number; real_usage_known_calls: number
  policy: { model: string; max_calls: number; max_output_tokens: number; request_timeout_seconds: number;
    max_total_tokens: number | null; token_enforcement: string } | null
  calls_remaining: number | null; revoked: boolean | null
}

export interface GatewayRequestEvidence {
  run_id: string; call_id: string; request_sha256: string
  status: 'recorded' | 'withheld' | 'missing' | 'invalid' | 'unavailable'
  hash_verified: boolean; dispatch_recorded: boolean
  preview: null | {
    parameters: Record<string, unknown>; message_count: number; original_bytes: number
    redacted: boolean; truncated: boolean; display_status: string; redaction_version: string
    messages: { index: number; role: string; content: string; original_chars: number;
      displayed_chars: number; redacted: boolean; truncated: boolean }[]
  }
}

export interface PlatformReport {
  evaluation_outcome: string; reason: string | null; final_snapshot_hash: string | null
  baseline_test: unknown; final_test: unknown; diff: string | null; diff_truncated: boolean
  changed_files: string[]; artifact_status: string
  process: { protocol_error: string | null; trace_status: string; stdout: string | null; stderr: string | null;
    stdout_truncated: boolean | null; stderr_truncated: boolean | null }
}

export interface Checkpoint {
  id: string; run_id: string; kind: 'plan' | 'candidate'; run_version: number
  payload: Record<string, unknown>; payload_sha256: string; decision: string | null
}
export interface RunControl {
  stage: string; ready: boolean; active: boolean; cancel_requested: boolean
  cleanup_status: string; error_code: string | null; active_seconds: number
  interruption_token: string | null; cleanup_error_code: string | null
  checkpoint: Checkpoint | null
}

export async function readLive<T>(path: string, body?: unknown): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), 10000)
  try {
    const response = await fetch(`/api/v2/runs${path}`, { signal: controller.signal, cache: 'no-store',
      ...(body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
    })
    if (!response.ok) {
      if (response.status === 503) throw new Error('运行存储不可用，请检查数据库连接及 v2 迁移。')
      if (response.status === 404) throw new Error('未找到该运行，或后端尚未加载 v2 接口。')
      if (response.status === 409) throw new Error('状态或审批版本已变化，请刷新后核对；本次请求未覆盖已有决定。')
      throw new Error(`读取失败（HTTP ${response.status}）`)
    }
    if (!response.headers.get('content-type')?.includes('application/json')) {
      throw new Error('未收到 API JSON，请检查后端连接和 /api 代理。')
    }
    return await response.json() as T
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw new Error('后端请求超时，请确认 API 已启动。')
    if (error instanceof TypeError) throw new Error('无法连接后端，请确认 API 已启动。')
    throw error
  } finally { window.clearTimeout(timer) }
}

// 按原页面约束同时保护按钮与提交处理器；不推断未记录的执行控制。
export function canDecideRun(run: PlatformRun | null, control: RunControl | null, busy: boolean): boolean {
  const checkpoint = control?.checkpoint
  return !busy && !!run && !!checkpoint && checkpoint.run_id === run.id
    && checkpoint.run_version === run.version && !checkpoint.decision
    && run.lifecycle === 'awaiting_input' && !control?.cancel_requested
}
export function canCancelRun(run: PlatformRun | null, control: RunControl | null, busy: boolean): boolean {
  return !busy && !!run && !!control && !control.cancel_requested
    && !['finished', 'interrupted', 'evaluating'].includes(run.lifecycle)
}
