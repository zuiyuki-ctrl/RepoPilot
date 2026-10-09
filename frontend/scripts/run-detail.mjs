import path from 'node:path'

// 展示只使用协议中的业务字段，不转发未知配置、认证头或工作区路径。
const payloadKeys = new Set(`sequence schema_version trace_version step_id attempt call_id tool_call_id tool_name model allow_tools tool_context system_prompt_sha256 duration_ms response_type tool_call_count arguments_chars hit_count requested_strategy retrieval_strategy strategy_overridden hits query effective_query top_k diagnostics result_scope repository_id retrieval_parameters index_version embedding_model embedding_dimensions rrf_rank_constant hybrid_candidate_limit overlap_count vector_candidate_count keyword_candidate_count final_keyword_hit_count sources attempted has_error disposition content_chars content_sha256 reserved_chars tool_message_index prepared_result_chars remaining_chars_after remaining_chars_before rank file_id chunk_id end_line file_hash file_path source_id start_line symbol_name vector_rank keyword_rank vector_distance distance score keyword_score rrf_score outcome started_sequence finished_sequence node_name`.split(' '))

export function redactText(value) {
  if (typeof value !== 'string') return value
  return value
    .replace(/\bBearer\s+[A-Za-z0-9._~+\/-]+=*/gi, 'Bearer [已脱敏]')
    .replace(/\bsk-[A-Za-z0-9_-]{12,}\b/g, '[已脱敏]')
    .replace(/((?:api[_-]?key|access[_-]?token|secret[_-]?key|password)\s*[=:]\s*["']?)[^\s"',;]+/gi, '$1[已脱敏]')
}
function payload(value) {
  if (Array.isArray(value)) return value.map(payload)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).filter(([key]) => payloadKeys.has(key)).map(([key, item]) => [key, payload(item)]))
  return redactText(value)
}
function plan(value) {
  if (!value) return null
  return { summary: redactText(value.summary), steps: (value.steps ?? []).map(s => ({ id: s.id, description: redactText(s.description), files: s.files, sourceIds: s.source_ids, verification: redactText(s.verification) })) }
}
function testRun(value) {
  if (!value) return null
  return { id: value.id, status: value.status, exitCode: value.exit_code ?? null, timedOut: value.timed_out ?? null,
    stdout: redactText(value.stdout ?? null), stderr: redactText(value.stderr ?? null), error: redactText(value.error ?? null),
    stdoutTruncated: value.stdout_truncated ?? null, stderrTruncated: value.stderr_truncated ?? null,
    startedAt: value.started_at ?? null, completedAt: value.completed_at ?? null, image: value.image ?? null,
    snapshotHash: value.snapshot_hash ?? null, timeoutSeconds: value.timeout_seconds ?? null }
}

export function buildRunDetail(preparation, records, report, evidence) {
  const p = preparation.data
  const timeline = []
  const warnings = []
  const add = (entry) => timeline.push(entry)
  add({ id: 'preparation', kind: 'preparation', origin: 'snapshot', title: '实验准备记录', time: p.created_at ?? null, sequence: null, source: preparation.source,
    data: { status: p.status, stage: p.stage, errorType: p.error_type ?? null, editableFiles: p.case.editable_files ?? null, protectedTestFiles: p.case.protected_test_files ?? null } })
  const events = evidence?.data.events ?? []
  let previous = 0
  const eventIds = new Set()
  for (const event of events) {
    if (event.task_id !== p.task_id || !Number.isInteger(event.sequence) || event.sequence <= previous || eventIds.has(event.id)) {
      throw new Error(`事件关联或序号异常：${evidence.source}`)
    }
    previous = event.sequence
    eventIds.add(event.id)
    add({ id: `event-${event.sequence}`, kind: 'event', origin: 'event', title: event.event_type, time: event.created_at ?? null, sequence: event.sequence,
      source: evidence.source, data: { eventId: event.id, node: event.node_name, payload: payload(event.payload) } })
  }
  const inspections = records.filter(r => path.basename(r.source).startsWith('plan_inspection_'))
  for (const r of inspections) add({ id: r.source, kind: 'plan', origin: 'snapshot', title: '计划检查快照', time: r.data.inspected_at ?? null, sequence: null, source: r.source,
    data: { status: r.data.task_status ?? r.data.task?.status ?? null, scopeStatus: r.data.scope_status ?? null, outsideScopeFiles: r.data.outside_scope_files ?? null, plan: plan(r.data.task?.result?.plan) } })
  const task = report?.data.task ?? [...inspections].sort((a,b) => Date.parse(b.data.inspected_at) - Date.parse(a.data.inspected_at))[0]?.data.task
  if (task?.review_decision) add({ id: 'review', kind: 'review', origin: 'snapshot', title: '历史审批决定', time: task.reviewed_at ?? null, sequence: null,
    source: report?.source ?? inspections.find(r => r.data.task?.review_decision === task.review_decision)?.source,
    data: { decision: task.review_decision, comment: redactText(task.review_comment ?? null) } })
  for (const r of records) {
    const name = path.basename(r.source)
    const d = r.data
    if (name === 'candidate.json') add({ id: r.source, kind: 'candidate', origin: 'snapshot', title: '修改候选已保存', time: d.created_at ?? null, sequence: null, source: r.source,
      data: { filePath: d.candidate?.proposal?.file_path ?? null, summary: redactText(d.candidate?.proposal?.summary ?? null), content: redactText(d.candidate?.proposal?.content ?? null), baseFileHash: d.candidate?.base_file_hash ?? null } })
    if (name === 'apply-result.json') add({ id: r.source, kind: 'apply', origin: 'snapshot', title: '候选应用结果', time: null, sequence: null, source: r.source,
      data: { filePath: d.result?.file_path ?? null, created: d.result?.created ?? null, bytesWritten: d.result?.bytes_written ?? null,
        candidateSource: records.find(c => path.basename(c.source) === 'candidate.json' && d.candidate_path?.replaceAll('\\', '/').endsWith('/' + c.source))?.source ?? null } })
    if (name === 'test-result.json') add({ id: r.source, kind: 'test', origin: 'snapshot', title: '测试执行记录', time: d.test_run?.completed_at ?? d.test_run?.started_at ?? null, sequence: null, source: r.source,
      data: { test: testRun(d.test_run), usedForCompletion: Boolean(report?.data.test_run && d.test_run?.id === report.data.test_run.id) } })
  }
  if (report) {
    const diff = report.data.final_diff
    if (diff && (diff.task_id !== p.task_id || diff.repository_id !== p.repository_id)) throw new Error(`历史 Diff 关联异常：${report.source}`)
    add({ id: 'report', kind: 'report', origin: 'snapshot', title: '终态报告与历史 Diff', time: report.data.task.completed_at ?? null, sequence: null, source: report.source,
      data: { status: report.data.task.status, completionEventSequence: report.data.completion_event_sequence ?? null,
        plan: plan(report.data.task.result?.plan), test: testRun(report.data.test_run),
        diff: diff ? { text: redactText(diff.diff), changedFiles: diff.changed_files, untrackedFiles: diff.untracked_files, truncated: diff.truncated, scope: report.data.diff_scope } : null,
        failure: report.data.failure ? { reason: redactText(report.data.failure.reason), eventType: report.data.failure.event_type, eventSequence: report.data.failure.event_sequence } : null } })
  }
  warnings.push('原始事件来自检索证据导出，仅覆盖其中保留的相关事件；文件快照不补造事件序号。')
  if (!report) warnings.push('未记录终态报告与历史最终 Diff，不能从已保存候选或测试通过推断任务完成。')
  if (evidence?.data.trace_status === 'not_recorded') warnings.push('该运行未记录新版检索与上下文证据，不根据当前索引补造历史。')
  // 有时间的记录按时间排序；缺少时间的操作单列，不能用文件名猜测其发生时间。
  timeline.sort((a, b) => {
    if (!a.time && !b.time) return a.id.localeCompare(b.id)
    if (!a.time) return 1
    if (!b.time) return -1
    return Date.parse(a.time) - Date.parse(b.time) || (a.sequence ?? 0) - (b.sequence ?? 0)
  })
  const timeBasis = { preparation: '准备记录创建时间', event: '原始事件时间', plan: '计划检查时间', review: '审批时间', candidate: '候选创建时间', apply: '时间未记录', test: 'TestRun 完成时间（缺失时取开始时间）', report: '任务完成时间，非报告导出时间' }
  return { schemaVersion: 1, experimentId: p.experiment_id, taskId: p.task_id ?? null,
    timeline: timeline.map(entry => ({ ...entry, timeBasis: timeBasis[entry.kind] })), warnings,
    contextLinks: (evidence?.data.tool_calls ?? []).map(call => ({ callId: call.call_id, toolCallId: call.tool_call_id,
      toolName: call.tool_name, retrievalSequence: call.retrieval?.sequence ?? null, contextSequence: call.context?.sequence ?? null,
      models: (call.model_calls ?? []).map(model => ({ callId: model.call_id, outcome: model.outcome, startedSequence: model.started_sequence, finishedSequence: model.finished_sequence ?? null })) })) }
}
