export interface InspectedReport { source: 'uploaded_report_only'; integrity: 'hashes_consistent'; report: Record<string, unknown> }
export async function inspectSavedReport(file: Blob): Promise<InspectedReport> {
  if (file.size > 10_000_000) throw new Error('报告不能超过 10 MB。')
  try {
    // 原始文件直接交给既有接口核验，不能先 parse/stringify 改写重复键或 hash 依据。
    const response = await fetch('/api/v2/reports/inspect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: file, signal: AbortSignal.timeout(15000) })
    if (!response.ok) throw new Error(`报告格式或 hash 校验失败（HTTP ${response.status}），请确认选择的是原始 JSON 导出文件。`)
    if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('未收到报告核验 JSON，请检查 API 代理。')
    const data = await response.json()
    if (data.source !== 'uploaded_report_only' || data.integrity !== 'hashes_consistent' || !data.report || typeof data.report !== 'object' || Array.isArray(data.report)) throw new Error('报告核验响应的来源或状态不符合约定。')
    return data as InspectedReport
  } catch (error) {
    if (error instanceof TypeError) throw new Error('无法连接当前 API，报告尚未核验。')
    if (error instanceof DOMException && ['TimeoutError', 'AbortError'].includes(error.name)) throw new Error('报告核验超时，请重新选择文件。')
    throw error
  }
}
