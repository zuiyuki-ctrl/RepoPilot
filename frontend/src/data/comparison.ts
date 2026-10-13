import type { Decision, FailureAnalysis, Fields, Resources } from './assessment'
export interface ComparisonRun {
  acceptance: Fields | null
  metrics: { started: boolean | null; event_scope_complete: boolean | null; wall_clock_ms: number | null;
    resources: Fields; cost: Fields; tests: { report_status: string | null; source: string | null; test_run_id: string | null; counts: Fields | null } } | null
  failureAnalysis: FailureAnalysis | null
  experimentId: string
  taskId: string | null
  strategy: string
  status: string
  retryCount: number | null
  stage: string
  errorType: string | null
  completionSequence: number | null
  detailMatches: boolean
  detailEvidenceMatches: boolean
  test: { id: string; exitCode: number | null; timedOut: boolean; passed: boolean; image: string } | null
  traceStatus: string | null
  traceLastSequence: number | null
  warnings: string[]
  queries: { query: string; sequence: number; diagnostics: Record<string, number | null> | null;
    hits: { rank: number; filePath: string; symbol: string | null; vectorRank: number | null; keywordRank: number | null }[] }[]
  contexts: { tool: string; sequence: number; disposition: string; chars: number; modelAttempts: number }[]
  artifactHashes: { name: string; sha256: string }[]
}
export interface ComparisonSnapshot {
  decision: Decision | null
  analysisCounts: Record<string, number | null> | null
  schemaVersion: 1
  generatedAt: string
  source: string
  limitations: string[]
  pairs: { caseId: string; caseVersion: string; repeatIndex: number; analysis: Fields | null;
    comparability: { status: string; missing: string[]; differences: Fields[] } | null;
    resources: Resources | null; differences: string[]; complete: boolean; runs: (ComparisonRun | null)[] }[]
  additional: (ComparisonRun & { caseId: string })[]
}
export async function readComparison(): Promise<ComparisonSnapshot> {
  const response = await fetch(`${import.meta.env.BASE_URL}data/comparison.json`)
  if (!response.ok) throw new Error('无法读取对照快照，请先运行 npm run snapshots。')
  const value = await response.json()
  if (value.schemaVersion !== 1 || !Array.isArray(value.pairs) || !Array.isArray(value.additional)) throw new Error('对照快照格式不受支持。')
  return value
}
