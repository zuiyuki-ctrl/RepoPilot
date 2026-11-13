export type WorkerPresence = 'present' | 'absent' | 'unknown'

export function parseWorkerPresence(data: unknown): WorkerPresence {
  if (typeof data !== 'object' || data === null) throw new Error('Invalid worker status')
  const value = data as Record<string, unknown>
  if (value.basis !== 'database_advisory_lock' || typeof value.connection_present !== 'boolean') {
    throw new Error('Invalid worker status')
  }
  return value.connection_present ? 'present' : 'absent'
}

export function workerNotice(status: WorkerPresence): string {
  if (status === 'present') return '检测到执行服务连接。校验任务由后台处理'
  if (status === 'absent') return '未检测到执行服务连接。可以登记或提交校验，任务需要等待 worker 启动，无需重复提交。'
  return '执行服务状态尚未确认或读取失败。请刷新或检查后端连接；请不要重复提交任务。'
}

export function pendingValidationText(status: string): string {
  return status === 'validating' ? '校验已提交，尚无已完成的校验结果。请核对执行服务状态，稍后刷新。' : '尚无已完成的校验结果。'
}
