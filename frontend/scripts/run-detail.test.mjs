import test from 'node:test'
import assert from 'node:assert/strict'
import { buildRunDetail, redactText } from './run-detail.mjs'

const preparation = { source: 'reports/experiments/e/preparation.json', data: {
  experiment_id: 'e', task_id: 'task', repository_id: 'repository', created_at: '2026-10-09T00:00:00Z',
  status: 'prepared', stage: 'create_task', case: { editable_files: ['sample.py'], protected_test_files: ['tests/test_sample.py'] },
} }
const event = (sequence, type = 'MODEL_CALL_STARTED') => ({ id: `event-${sequence}`, task_id: 'task', sequence, event_type: type,
  created_at: `2026-10-09T00:00:${String(sequence).padStart(2, '0')}Z`, payload: { model: 'saved-model', server_credentials: 'excluded-value' } })
const evidence = events => ({ source: 'reports/experiments/e/evidence/evidence.json', data: { events, trace_status: 'recorded' } })
const candidate = { source: 'reports/experiments/e/operations/generate/candidate.json', data: { created_at: '2026-10-09T00:01:00Z', candidate: {
  proposal: { file_path: 'sample.py', summary: '候选', content: 'print("<script>")' }, base_file_hash: 'original-hash',
} } }

test('审批和候选是文件快照，不能补造应用、测试、终态事件', () => {
  const inspection = { source: 'reports/experiments/e/plan_inspection_one.json', data: { inspected_at: '2026-10-09T00:00:30Z', task: {
    review_decision: 'approved', reviewed_at: '2026-10-09T00:00:20Z', review_comment: '批准',
  } } }
  const detail = buildRunDetail(preparation, [inspection, candidate], undefined, evidence([event(2)]))
  assert.equal(detail.timeline.filter(e => e.origin === 'event').length, 1)
  assert.equal(detail.timeline.find(e => e.kind === 'review').sequence, null)
  assert.equal(detail.timeline.find(e => e.kind === 'candidate').data.content, 'print("<script>")')
  assert.equal(detail.timeline.some(e => ['apply', 'test', 'report'].includes(e.kind)), false)
})

test('未记录应用时间单列，保留候选关联且不暴露机器绝对路径', () => {
  const applied = { source: 'reports/experiments/e/operations/apply/apply-result.json', data: {
    candidate_path: 'D:\\RepoPilot\\reports\\experiments\\e\\operations\\generate\\candidate.json', result: { file_path: 'sample.py', bytes_written: 1, created: false },
  } }
  const detail = buildRunDetail(preparation, [candidate, applied])
  const item = detail.timeline.find(e => e.kind === 'apply')
  assert.equal(item.time, null)
  assert.equal(item.sequence, null)
  assert.equal(item.data.candidateSource, candidate.source)
  assert.equal(JSON.stringify(detail).includes('D:'), false)
})

test('旧任务不补造新版检索，未知事件字段不打包', () => {
  const old = evidence([event(2), event(3, 'MODEL_CALL_COMPLETED')])
  old.data.trace_status = 'not_recorded'
  const detail = buildRunDetail(preparation, [], undefined, old)
  assert.equal(detail.timeline.some(e => e.title === 'RETRIEVAL_COMPLETED'), false)
  assert.equal(JSON.stringify(detail).includes('excluded-value'), false)
  assert.ok(detail.warnings.some(w => w.includes('未记录新版')))
})

test('事件错配、重复、错序必须拒绝', () => {
  for (const events of [[{ ...event(2), task_id: 'other' }], [event(2), event(2)], [event(3), event(2)]]) {
    assert.throws(() => buildRunDetail(preparation, [], undefined, evidence(events)), /事件关联或序号异常/)
  }
})

test('历史 Diff 关联拒绝错配；完成事件只引用，不合成事件', () => {
  const report = { source: 'reports/experiments/e/operations/report/task_report.json', data: {
    task: { id: 'task', status: 'completed', completed_at: '2026-10-09T00:03:00Z' }, completion_event_sequence: 31,
    final_diff: { task_id: 'task', repository_id: 'repository', diff: '+ saved historical diff', changed_files: ['sample.py'], untracked_files: [], truncated: true },
  } }
  const detail = buildRunDetail(preparation, [], report)
  const item = detail.timeline.find(e => e.kind === 'report')
  assert.equal(item.data.completionEventSequence, 31)
  assert.equal(item.data.diff.text, '+ saved historical diff')
  assert.equal(item.data.diff.truncated, true)
  assert.ok(item.timeBasis.includes('非报告导出时间'))
  assert.equal(detail.timeline.some(e => e.title === 'TASK_COMPLETED'), false)
  report.data.final_diff.repository_id = 'other'
  assert.throws(() => buildRunDetail(preparation, [], report), /Diff 关联异常/)
})

test('凭据展示脱敏只影响派生文本，保留空输出和缺失输出的区别', () => {
  assert.equal(redactText('Authorization: Bearer fake-auth-token'), 'Authorization: Bearer [已脱敏]')
  assert.equal(redactText('API_KEY=synthetic-secret'), 'API_KEY=[已脱敏]')
  const report = { source: 'report', data: { task: { status: 'completed' }, test_run: { id: 'test', stdout: '', stderr: undefined } } }
  const detail = buildRunDetail(preparation, [], report)
  const item = detail.timeline.find(e => e.kind === 'report')
  assert.equal(item.data.test.stdout, '')
  assert.equal(item.data.test.stderr, null)
})
