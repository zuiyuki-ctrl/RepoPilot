import test from 'node:test'
import assert from 'node:assert/strict'
import { parseDashboard, totalRecords, statusLabel, readDashboard } from '../src/data/dashboard.ts'

// 仅供边界检查的合成响应，不进入产品数据与实验统计。
const sample = () => ({ source: 'live_database_only', observed_at: '2026-10-20T01:00:00Z',
  agents: { active: 2, draft: 1 }, benchmarks: { active: 1 }, experiments: 2,
  preparation: { prepared: 8 }, lifecycle: { completed: 3, running: 1 },
  execution: { succeeded: 3, unknown: 1 }, evaluation: { passed: 1, unknown: 3 },
  recent_experiments: [{ id: 'experiment-ui-check', name: '界面检查样例', created_at: null }],
  recent_runs: [{ id: 'run-ui-check', lifecycle: 'completed', execution: 'succeeded', evaluation: 'unknown' }],
})

test('只从完整生命周期分组求 Run 记录数，不用执行或验收通过数代替', () => {
  const value = parseDashboard(sample())
  assert.equal(totalRecords(value.lifecycle), 4)
  assert.equal(totalRecords(value.agents), 3)
  assert.notEqual(totalRecords(value.lifecycle), value.evaluation.passed)
})
test('明确的空响应可以是零，缺失分组或缺失实验数量必须拒绝', () => {
  const empty = { ...sample(), agents: {}, lifecycle: {}, experiments: 0, recent_runs: [] }
  assert.equal(totalRecords(parseDashboard(empty).agents), 0)
  for (const field of ['agents', 'benchmarks', 'preparation', 'lifecycle', 'execution', 'evaluation', 'experiments']) {
    const value = sample(); delete value[field]
    assert.throws(() => parseDashboard(value))
  }
})
test('拒绝归档来源、损坏的状态数和错误列表，不伪装实时连接', () => {
  for (const value of [null, { ...sample(), source: 'archived' }, { ...sample(), lifecycle: { completed: null } },
    { ...sample(), execution: { failed: -1 } }, { ...sample(), agents: { active: 1.5 } },
    { ...sample(), observed_at: 'invalid' }, { ...sample(), recent_runs: [{ id: 'run' }] },
    { ...sample(), recent_experiments: [{ id: 'experiment', name: 3 }] }]) assert.throws(() => parseDashboard(value))
})
test('未知状态保留原值，执行完成与平台验收未知仍为两个字段', () => {
  assert.equal(statusLabel('future_status'), 'future_status')
  const run = parseDashboard(sample()).recent_runs[0]
  assert.equal(run.execution, 'succeeded')
  assert.equal(run.evaluation, 'unknown')
})
test('读取器只 GET 既有总览 API，不缓存，不附带写入正文', async () => {
  const result = await readDashboard(undefined, async (url, options) => {
    assert.equal(url, '/api/v2/dashboard')
    assert.equal(options.cache, 'no-store')
    assert.equal(options.body, undefined)
    assert.equal(options.method, undefined)
    assert.ok(options.signal)
    return new Response(JSON.stringify(sample()), { headers: { 'Content-Type': 'application/json' } })
  })
  assert.equal(result.experiments, 2)
})
test('HTTP、HTML、断网与超时均拒绝，不返回默认数据', async () => {
  await assert.rejects(readDashboard(undefined, async () => new Response('', { status: 503 })), /503/)
  await assert.rejects(readDashboard(undefined, async () => new Response('<html>fallback</html>')), /JSON/)
  await assert.rejects(readDashboard(undefined, async () => { throw new TypeError('network') }), /无法连接后端/)
  await assert.rejects(readDashboard(undefined, async () => { throw new DOMException('timeout', 'TimeoutError') }), /超时/)
})
