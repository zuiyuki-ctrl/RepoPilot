export interface ComparisonRun {
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
  schemaVersion: 1
  generatedAt: string
  source: string
  limitations: string[]
  pairs: { caseId: string; caseVersion: string; differences: string[]; complete: boolean; runs: (ComparisonRun | null)[] }[]
  additional: (ComparisonRun & { caseId: string })[]
}
export async function readComparison(): Promise<ComparisonSnapshot> {
  const response = await fetch(`${import.meta.env.BASE_URL}data/comparison.json`)
  if (!response.ok) throw new Error('无法读取对照快照，请先运行 npm run snapshots。')
  const value = await response.json()
  if (value.schemaVersion !== 1 || !Array.isArray(value.pairs) || !Array.isArray(value.additional)) throw new Error('对照快照格式不受支持。')
  return value
}
