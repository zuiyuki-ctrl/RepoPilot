export interface SourceReference { path: string; timestamp: string | null; selected: boolean }
export interface HistoricalRun {
  experimentId: string
  taskId: string | null
  repositoryId: string | null
  caseId: string
  caseVersion: string
  goal: string
  strategy: string
  config: { maxToolCalls: number | null; maxRetries: number | null }
  commit: string
  createdAt: string
  preparationStatus: string
  preparationStage: string
  preparationError: string | null
  taskStatus: string | null
  taskStatusSource: string | null
  progress: 'terminal_report' | 'tested' | 'applied' | 'candidate_saved' | 'plan_snapshot' | 'preparation'
  candidateCount: number
  retryCount: number | null
  test: null | {
    id: string; status: string; exitCode: number | null; timedOut: boolean; passed: boolean
    summary: string | null; startedAt: string; completedAt: string | null
    snapshotHash: string | null; image: string; source: string
  }
  evidence: null | {
    status: string; exportedAt: string; lastSequence: number; fetchedEventCount: number
    savedEventCount: number | null; taskStatusAtExport: string | null; warnings: string[]; source: string
  }
  reportSource: string | null
  issues: string[]
  sources: SourceReference[]
}
export interface HistorySnapshot { schemaVersion: 1; generatedAt: string; sourceRoot: string; runs: HistoricalRun[] }

// 页面依赖这个小接口，未来可以替换为 API 读取实现。
export interface HistoryReader { read(): Promise<HistorySnapshot> }
export const snapshotReader: HistoryReader = {
  async read() {
    const response = await fetch(`${import.meta.env.BASE_URL}data/history.json`)
    if (!response.ok) throw new Error(`历史快照读取失败（HTTP ${response.status}）`)
    const data: unknown = await response.json()
    if (!data || typeof data !== 'object' || !('schemaVersion' in data) || data.schemaVersion !== 1 || !('runs' in data) || !Array.isArray(data.runs)) {
      throw new Error('历史快照格式不受支持，请重新执行 npm run snapshots。')
    }
    return data as HistorySnapshot
  },
}
