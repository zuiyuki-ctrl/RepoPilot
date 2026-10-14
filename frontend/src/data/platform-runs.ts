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
