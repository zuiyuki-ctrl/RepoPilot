export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }
export interface Plan { summary: string; steps: { id: number; description: string; files: string[]; sourceIds: string[]; verification: string }[] }
export interface TestRecord {
  id: string; status: string; exitCode: number | null; timedOut: boolean | null
  stdout: string | null; stderr: string | null; error: string | null
  stdoutTruncated: boolean | null; stderrTruncated: boolean | null
  startedAt: string | null; completedAt: string | null; image: string | null
  snapshotHash: string | null; timeoutSeconds: number | null
}
export interface Hit {
  rank?: number; file_path?: string; start_line?: number; end_line?: number; symbol_name?: string
  source_id?: string; content_sha256?: string; distance?: number; score?: number
  vector_distance?: number; keyword_score?: number; rrf_score?: number
}
export interface EventPayload {
  call_id?: string; tool_call_id?: string; tool_name?: string; model?: string; query?: string; effective_query?: string
  retrieval_strategy?: string; requested_strategy?: string; top_k?: number; hits?: Hit[]; sources?: Hit[]
  duration_ms?: number; disposition?: string; content_chars?: number; content_sha256?: string
  remaining_chars_before?: number; remaining_chars_after?: number; tool_context?: JsonValue[]
  [key: string]: unknown
}
interface BaseEntry { id: string; origin: 'event' | 'snapshot'; title: string; time: string | null; timeBasis: string; sequence: number | null; source: string }
export type TimelineEntry = BaseEntry & (
  { kind: 'event'; data: { eventId: string; node: string; payload: EventPayload } } |
  { kind: 'preparation'; data: { status: string; stage: string; errorType: string | null; editableFiles: string[] | null; protectedTestFiles: string[] | null } } |
  { kind: 'plan'; data: { status: string | null; scopeStatus: string | null; outsideScopeFiles: string[] | null; plan: Plan | null } } |
  { kind: 'review'; data: { decision: string; comment: string | null } } |
  { kind: 'candidate'; data: { filePath: string | null; summary: string | null; content: string | null; baseFileHash: string | null } } |
  { kind: 'apply'; data: { filePath: string | null; created: boolean | null; bytesWritten: number | null; candidateSource: string | null } } |
  { kind: 'test'; data: { test: TestRecord | null; usedForCompletion: boolean } } |
  { kind: 'report'; data: { status: string; completionEventSequence: number | null; plan: Plan | null; test: TestRecord | null; diff: null | { text: string; changedFiles: string[]; untrackedFiles: string[]; truncated: boolean; scope: string }; failure: null | { reason: string; eventType: string; eventSequence: number } } }
)
export interface ContextLink {
  callId: string; toolCallId: string; toolName: string; retrievalSequence: number | null; contextSequence: number | null
  models: { callId: string; outcome: string; startedSequence: number; finishedSequence: number | null }[]
}
export interface RunDetail { schemaVersion: 1; experimentId: string; taskId: string | null; timeline: TimelineEntry[]; warnings: string[]; contextLinks: ContextLink[] }

export async function readRunDetail(experimentId: string): Promise<RunDetail> {
  const response = await fetch(`${import.meta.env.BASE_URL}data/runs/${encodeURIComponent(experimentId)}.json`)
  if (!response.ok) throw new Error(`运行详情读取失败（HTTP ${response.status}）`)
  const data = await response.json() as RunDetail
  if (data.schemaVersion !== 1 || data.experimentId !== experimentId || !Array.isArray(data.timeline)) throw new Error('详情格式或实验关联不一致，请重新整理快照。')
  return data
}
