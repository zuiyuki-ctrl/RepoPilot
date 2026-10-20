export type CatalogKind = 'agents' | 'benchmarks'
export interface CatalogEntry {
  id: string; name: string; version: string; status: string; content_sha256: string
  descriptor: Record<string, unknown>; validation: Record<string, unknown> | null
}
export interface CatalogRepository { id: string; name: string; commit_hash: string }
export const catalogLabels: Record<string, string> = { registered: '已登记 · 未校验', validating: '校验排队或执行中', ready: '校验通过', invalid: '校验失败或中断' }
export function canValidateCatalog(entry: CatalogEntry, busy: boolean, connected: boolean): boolean {
  return connected && !busy && entry.status !== 'validating' && entry.validation?.status !== 'interrupted'
}
export function parseCatalogConfiguration(text: string): unknown {
  if (new TextEncoder().encode(text).length > 1_000_000) throw new Error('配置不能超过 1 MB。')
  try { return JSON.parse(text) } catch { throw new Error('配置不是有效的 JSON，请检查后再保存。') }
}
export function makeAgentConfiguration(name: string, version: string, adapter: string, image: string, argv: string): string {
  let args: unknown
  if (adapter === 'process') {
    try { args = JSON.parse(argv) } catch { throw new Error('启动参数必须是 JSON 字符串数组。') }
    if (!Array.isArray(args) || !args.every(item => typeof item === 'string')) throw new Error('启动参数必须是 JSON 字符串数组。')
  }
  return JSON.stringify({ protocol_version: 1, name, version, adapter, declared_capabilities: ['execution'],
    ...(adapter === 'process' ? { process: { protocol_version: 1, image, argv: args, trace: false } }
      : { native: { retrieval_policy: 'vector', max_tool_calls: 4 } }) }, null, 2)
}
export async function catalogRequest<T>(path: string, body?: unknown): Promise<T> {
  try {
    const response = await fetch('/api/v2/' + path, { method: body === undefined ? 'GET' : 'POST', cache: 'no-store',
      headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(15000) })
    if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('未收到 API JSON，请检查后端连接与 /api 代理。')
    const data = await response.json()
    if (!response.ok) throw new Error(`${response.status}: ${typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)}`)
    return data as T
  } catch (error) {
    if (error instanceof TypeError) throw new Error('无法连接后端，请刷新后确认连接。')
    if (error instanceof DOMException && ['TimeoutError', 'AbortError'].includes(error.name)) throw new Error('请求超时；写请求未自动重试，请核对记录后刷新。')
    throw error
  }
}
