export function formatDate(value: string | null | undefined) {
  if (!value || !Number.isFinite(Date.parse(value))) return '未记录'
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Tokyo', dateStyle: 'medium', timeStyle: 'medium', hour12: false }).format(new Date(value))
}
export const taskStatusText = (value: string | null) => value ? ({ completed: '任务已完成', approved: '计划已批准', awaiting_review: '等待审批', executing: '执行中', failed: '任务失败', rejected: '已拒绝' }[value] ?? value) : '未记录'
export const strategyText = (value: string) => ({ vector: 'Vector', hybrid: 'Hybrid', auto: '自由模式' })[value] ?? value
export const eventTitle = (value: string) => ({ MODEL_CALL_STARTED: '模型请求开始', MODEL_CALL_COMPLETED: '模型请求完成', MODEL_CALL_FAILED: '模型请求失败', TOOL_CALL_STARTED: '工具调用开始', TOOL_CALL_COMPLETED: '工具调用完成', TOOL_CALL_FAILED: '工具调用失败', RETRIEVAL_COMPLETED: '检索结果返回', TOOL_CONTEXT_PREPARED: '工具上下文准备' })[value] ?? value
