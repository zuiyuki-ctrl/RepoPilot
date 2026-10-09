import test from 'node:test'
import assert from 'node:assert/strict'
import { buildHistory, parsePytestSummary } from './build-snapshots.mjs'

const prep = {
  experiment_id: 'experiment-1', task_id: 'task-1', repository_id: 'repository-1',
  created_at: '2026-10-09T00:00:00Z', status: 'prepared', stage: 'create_task',
  case: { case_id: 'sample', case_version: 'v1', user_request: '目标', repository_commit: 'fixed-commit' },
  run_config: { retrieval_policy: 'vector', max_tool_calls: 4 },
}
const record = (name, data) => ({ source: `reports/experiments/experiment-1/${name}`, data })
const preparation = record('preparation.json', prep)

test('未记录的测试和重试不填零，候选不意味着已经应用', () => {
  const run = buildHistory([preparation, record('operations/one/candidate.json', {
    experiment_id: 'experiment-1', candidate: { task_id: 'task-1', repository_id: 'repository-1' },
  })]).runs[0]
  assert.equal(run.progress, 'candidate_saved')
  assert.equal(run.test, null)
  assert.equal(run.retryCount, null)
  assert.equal(run.evidence, null)
})

test('拒绝错配的任务、仓库与 TestRun，保留来源和问题', () => {
  for (const report of [
    { task: { id: 'another', repository_id: 'repository-1' } },
    { task: { id: 'task-1', repository_id: 'another' } },
    { task: { id: 'task-1', repository_id: 'repository-1' }, test_run: { id: 'test-1', task_id: 'another' } },
  ]) {
    const run = buildHistory([preparation, record('operations/one/task_report.json', report)]).runs[0]
    assert.equal(run.reportSource, null)
    assert.equal(run.issues.length, 1)
    assert.equal(run.sources.length, 2)
  }
})

test('重复证据按导出时间选最新，不丢弃旧导出，不以 recorded 宣称全流程完整', () => {
  const older = record('evidence/old/evidence.json', { task_id: 'task-1', exported_at: '2026-10-09T00:00:00Z', trace_status: 'not_recorded', events: [] })
  const newer = record('evidence/new/evidence.json', { task_id: 'task-1', exported_at: '2026-10-09T01:00:00Z', trace_status: 'recorded', events: [{ id: 'event-1', task_id: 'task-1', sequence: 1 }], task_snapshot_before_event_fetch: { status: 'awaiting_review' } })
  const run = buildHistory([preparation, newer, older]).runs[0]
  assert.equal(run.evidence.status, 'recorded')
  assert.equal(run.evidence.taskStatusAtExport, 'awaiting_review')
  assert.equal(run.sources.length, 3)
  assert.equal(run.sources.find(s => s.path === older.source).selected, false)
})

test('终态报告与旧规划状态分开，pytest 耗时仅保留原始汇总', () => {
  const report = record('operations/one/task_report.json', {
    task: { id: 'task-1', repository_id: 'repository-1', status: 'completed', retry_count: 0, max_retries: 1 },
    test_run: { id: 'test-1', task_id: 'task-1', status: 'finished', exit_code: 0, timed_out: false, stdout: '........\n8 passed in 0.09s\n' },
  })
  const run = buildHistory([preparation, record('plan_inspection_old.json', { task: { id: 'task-1', status: 'awaiting_review' } }), report]).runs[0]
  assert.equal(run.taskStatus, 'completed')
  assert.equal(run.test.id, 'test-1')
  assert.equal(run.test.passed, true)
  assert.equal(run.test.summary, '8 passed in 0.09s')
  assert.equal(run.retryCount, 0)
  assert.equal(parsePytestSummary('some text 8 passed in 0.09s'), null)
  assert.equal(parsePytestSummary('=== 2 passed, 1 skipped in 0.12s ==='), '=== 2 passed, 1 skipped in 0.12s ===')
})

test('准备错误不产生任务；工作区路径和未知字段不进入前端输出', () => {
  const run = buildHistory([record('preparation.json', { ...prep, task_id: null, status: 'error', error_type: 'ValueError', workspace_path: 'private-local-directory', server_secret: 'do-not-copy' })]).runs[0]
  assert.equal(run.taskId, null)
  assert.equal(run.preparationStatus, 'error')
  assert.equal(JSON.stringify(run).includes('private-local-directory'), false)
  assert.equal(JSON.stringify(run).includes('do-not-copy'), false)
})

test('没有终态报告时仍展示已保存的 TestRun，但不自动判定任务完成', () => {
  const run = buildHistory([preparation, record('operations/test/test-result.json', {
    experiment_id: 'experiment-1', task_id: 'task-1',
    test_run: { id: 'test-1', task_id: 'task-1', status: 'finished', exit_code: 0, timed_out: false, stdout: '1 passed in 0.01s\n' },
  })]).runs[0]
  assert.equal(run.progress, 'tested')
  assert.equal(run.test.passed, true)
  assert.equal(run.taskStatus, null)
  assert.equal(run.reportSource, null)
})

test('多次测试按 TestRun 完成时间选择，不能用随机操作目录排序', () => {
  const make = (id, completedAt) => ({ experiment_id: 'experiment-1', task_id: 'task-1', test_run: {
    id, task_id: 'task-1', completed_at: completedAt, status: 'finished', exit_code: 0, timed_out: false, stdout: '1 passed in 0.01s\n',
  } })
  const run = buildHistory([preparation,
    record('operations/z/test-result.json', make('latest-test', '2026-10-09T02:00:00Z')),
    record('operations/a/test-result.json', make('old-test', '2026-10-09T01:00:00Z')),
  ]).runs[0]
  assert.equal(run.test.id, 'latest-test')
})
