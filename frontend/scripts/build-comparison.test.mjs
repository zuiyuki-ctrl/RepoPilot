import test from 'node:test'
import assert from 'node:assert/strict'
import { buildComparisonSnapshot } from './build-comparison.mjs'

const id = '11111111-1111-4111-8111-111111111111'
function fixture() {
  const run = { experiment_id: id, task_id: 'task', case: { case_id: 'demo', case_version: 'v1' }, strategy: 'vector',
    status: 'completed', retry_count: 0, test: { id: 'test', exit_code: 0, timed_out: false, process_passed: true },
    artifacts: { report: { path: 'D:\\RepoPilot\\reports\\task.json', sha256: 'hash' }, evidence: { path: 'D:/RepoPilot/reports/evidence.json', sha256: 'evidence-hash' } },
    retrieval: { trace_status: 'recorded', queries: [], contexts: [], warnings: [] } }
  return {
    report: { schema_version: 1, generated_at: '2026-10-09', limitations: ['小样本'], additional_attempts: [],
      pairs: [{ case_id: 'demo', case_version: 'v1', pair_complete: false, recorded_condition_differences: [], runs: { vector: run } }] },
    history: { runs: [{ experimentId: id, taskId: 'task', strategy: 'vector', test: { id: 'test' }, reportSource: 'reports/task.json', evidence: { source: 'reports/evidence.json' } }] }, run,
  }
}
const build = ({ report, history }) => buildComparisonSnapshot(report, 'reports/comparisons/selected/comparison.json', history)

test('明确选择的报告可关联详情，缺少策略保持为空；不修改输入', () => {
  const input = fixture()
  const before = JSON.stringify(input)
  const result = build(input)
  assert.equal(result.pairs[0].runs[0].detailMatches, true)
  assert.equal(result.pairs[0].runs[0].detailEvidenceMatches, true)
  assert.equal(result.pairs[0].runs[0].test.exitCode, 0)
  assert.equal(result.pairs[0].runs[1], null)
  assert.equal(JSON.stringify(input), before)
  assert.ok(!JSON.stringify(result).includes('D:'))
})
test('详情选择了另一份报告或测试时不提供匹配链接', () => {
  for (const change of [h => { h.reportSource = 'reports/other.json' }, h => { h.test.id = 'other' }, h => { h.taskId = 'other' }]) {
    const input = fixture()
    change(input.history.runs[0])
    assert.equal(build(input).pairs[0].runs[0].detailMatches, false)
  }
})
test('同一终态报告但不同证据导出保持区分', () => {
  const input = fixture()
  input.history.runs[0].evidence.source = 'reports/new-evidence.json'
  const row = build(input).pairs[0].runs[0]
  assert.equal(row.detailMatches, true)
  assert.equal(row.detailEvidenceMatches, false)
})
test('旧证据未记录、额外准备记录不补造数值', () => {
  const input = fixture()
  input.run.retrieval = { trace_status: 'not_recorded', queries: [], contexts: [] }
  input.report.additional_attempts.push({ ...input.run, experiment_id: '22222222-2222-4222-8222-222222222222', task_id: null, status: 'preparation_incomplete', test: null, retry_count: null, retrieval: null })
  const result = build(input)
  assert.equal(result.pairs[0].runs[0].traceStatus, 'not_recorded')
  assert.equal(result.additional[0].test, null)
  assert.equal(result.additional[0].retryCount, null)
  assert.equal(result.additional[0].traceStatus, null)
})
test('拒绝版本不支持、实验重复、用例错配', () => {
  for (const change of [i => { i.report.schema_version = 2 }, i => { i.report.additional_attempts.push(i.run) }, i => { i.run.case.case_id = 'other' }]) {
    const input = fixture()
    change(input)
    assert.throws(() => build(input))
  }
})
test('只投影诊断字段并脱敏查询，不把未知属性发布到页面', () => {
  const input = fixture()
  input.run.retrieval.queries = [{ query: 'api_key=fixture-secret', event_sequence: 6,
    diagnostics: { keyword_candidate_count: 0, unknown: 'private' }, hits: [] }]
  const result = build(input).pairs[0].runs[0].queries[0]
  assert.equal(result.query, 'api_key=[已脱敏]')
  assert.equal(result.diagnostics.keyword_candidate_count, 0)
  assert.equal(result.diagnostics.vector_candidate_count, null)
  assert.equal(result.diagnostics.unknown, undefined)
})
