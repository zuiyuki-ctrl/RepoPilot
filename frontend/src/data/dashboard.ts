export type StatusCounts = Record<string, number>
export interface Dashboard {
  source: 'live_database_only'; observed_at: string
  agents: StatusCounts; benchmarks: StatusCounts; experiments: number
  preparation: StatusCounts; lifecycle: StatusCounts; execution: StatusCounts; evaluation: StatusCounts
  recent_experiments: { id: string; name: string; created_at: string | null }[]
  recent_runs: { id: string; lifecycle: string; execution: string; evaluation: string }[]
}
function object(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value) }
function count(value: unknown): value is number { return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 }
function counts(value: unknown): value is StatusCounts { return object(value) && Object.values(value).every(count) }
export function parseDashboard(value: unknown): Dashboard {
  if (!object(value) || value.source !== 'live_database_only' || typeof value.observed_at !== 'string' || !Number.isFinite(Date.parse(value.observed_at)) || !count(value.experiments)) throw new Error('总览数据格式或来源不符合实时接口约定。')
  for (const key of ['agents', 'benchmarks', 'preparation', 'lifecycle', 'execution', 'evaluation']) {
    if (!counts(value[key])) throw new Error(`总览的 ${key} 数量未完整记录，无法展示。`)
  }
  if (!Array.isArray(value.recent_experiments) || !value.recent_experiments.every(item => object(item) && typeof item.id === 'string' && typeof item.name === 'string' && (item.created_at == null || typeof item.created_at === 'string' && Number.isFinite(Date.parse(item.created_at))))) throw new Error('最近实验数据格式不符合约定。')
  if (!Array.isArray(value.recent_runs) || !value.recent_runs.every(item => object(item) && ['id', 'lifecycle', 'execution', 'evaluation'].every(key => typeof item[key] === 'string'))) throw new Error('最近运行数据格式不符合约定。')
  return value as unknown as Dashboard
}
export function totalRecords(value: StatusCounts): number { return Object.values(value).reduce((sum, item) => sum + item, 0) }
export function statusLabel(value: string): string {
  return ({ active: '可用', inactive: '未启用', registered: '已登记', draft: '草稿', frozen: '已冻结', ready: '就绪', pending: '待处理', preparing: '准备中', prepared: '已准备', queued: '排队中', created: '已创建', running: '运行中', executing: '执行中', awaiting_review: '等待审批', completed: '已完成', finished: '已结束', failed: '失败', error: '错误', cancelled: '已取消', cancelling: '取消中', passed: '通过', not_passed: '未通过', unknown: '未知', not_started: '未开始', not_run: '未执行', succeeded: '执行成功', success: '成功', rejected: '已拒绝', stopped: '已停止' } as Record<string, string>)[value] ?? value
}
export async function readDashboard(signal?: AbortSignal, fetcher: typeof fetch = fetch): Promise<Dashboard> {
  try {
    const response = await fetcher('/api/v2/dashboard', { cache: 'no-store', signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000) })
    if (!response.ok) throw new Error(`无法读取实时总览（HTTP ${response.status}），请确认后端服务可用。`)
    if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('未收到总览 JSON，请检查后端连接与 API 代理。')
    return parseDashboard(await response.json())
  } catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') throw new Error('总览读取超时，请稍后重试。')
    if (error instanceof TypeError) throw new Error('无法连接后端，可以先查看历史快照或报告文件。')
    throw error
  }
}
