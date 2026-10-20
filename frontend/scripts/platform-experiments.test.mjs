import test from 'node:test'
import assert from 'node:assert/strict'
import { draftBody, validDraft, previewMatches, canStartExperiment, canSaveExperimentReview, canCancelExperiment, experimentApi } from '../src/data/platform-experiments.ts'

const draft = () => ({ name: '合成界面检查', suite_id: 'suite-check', baseline_agent_id: 'agent-a', candidate_agent_id: 'agent-b', mode: 'benchmark', changed_fields: [], repetitions: 1, timeout_seconds: 60, order: 'baseline_first', intervention: 'adapter_default', decision_policy: null })
const policy = () => ({ version: 1, min_pairs: 1, min_cases: 1, max_regressions: 0, min_pass_delta_pp: 0 })
const preview = () => ({ preview_sha256: 'a'.repeat(64), manifest: { needs_model: true, run_count: 4, changed_fields: ['native.retrieval_policy'] } })

test('冻结正文保持原字段和干预规则，变更字段去空白，不修改草稿或启用默认门槛', () => {
  const original = draft(), p = policy()
  const body = draftBody(original, ' native.retrieval_policy, , budget ', false, p)
  assert.deepEqual(body.changed_fields, ['native.retrieval_policy', 'budget'])
  assert.equal(body.decision_policy, null)
  assert.equal(body.intervention, 'adapter_default')
  assert.deepEqual(original.changed_fields, [])
  assert.equal(draftBody(original, '', true, p).decision_policy.min_pairs, 1)
})
test('预览输入保留次数、预算和质量门槛范围，空值和重复声明不通过', () => {
  assert.equal(validDraft(draft()), true)
  for (const change of [{ suite_id: '' }, { name: ' ' }, { repetitions: 0 }, { repetitions: 6 }, { repetitions: 1.5 }, { repetitions: undefined }, { timeout_seconds: 3601 }, { timeout_seconds: 0 }, { changed_fields: ['x', 'x'] }, { mode: 'invalid' }, { decision_policy: { ...policy(), min_cases: 0 } }, { decision_policy: { ...policy(), max_regressions: -1 } }, { decision_policy: { ...policy(), min_pass_delta_pp: NaN } }]) assert.equal(validDraft({ ...draft(), ...change }), false)
})
test('编辑任一有效条件后，旧冻结预览不再匹配；字段规范化相同仍匹配', () => {
  const frozen = draftBody(draft(), ' x , y ', true, policy())
  assert.equal(previewMatches(frozen, draftBody(draft(), 'x,y', true, policy())), true)
  for (const change of [{ name: '另一个实验' }, { repetitions: 2 }, { timeout_seconds: 90 }, { order: 'candidate_first' }, { candidate_agent_id: 'agent-c' }]) assert.equal(previewMatches(frozen, draftBody({ ...draft(), ...change }, 'x,y', true, policy())), false)
  assert.equal(previewMatches(frozen, draftBody(draft(), 'x,y', true, { ...policy(), min_pairs: 2 })), false)
  assert.equal(previewMatches(null, draft()), false)
})
test('模型批次必须同时确认和授权，断连、忙碌、旧预览与未知模型标志一律不能启动', () => {
  const state = { busy: false, connected: true, current: true, confirmed: true, allowModel: true, preview: preview() }
  assert.equal(canStartExperiment(state), true)
  for (const change of [{ busy: true }, { connected: false }, { current: false }, { confirmed: false }, { allowModel: false }, { preview: null }, { preview: { ...preview(), manifest: { ...preview().manifest, needs_model: undefined } } }]) assert.equal(canStartExperiment({ ...state, ...change }), false)
  assert.equal(canStartExperiment({ ...state, allowModel: false, preview: { ...preview(), manifest: { ...preview().manifest, needs_model: false } } }), true)
})
test('人工决定要求相同比较 hash、确认、身份与理由，读取中及不支持的决定不能提交', () => {
  const state = { busy: false, loading: false, confirmed: true, targetHash: 'a'.repeat(64), currentHash: 'a'.repeat(64), form: { reviewer: '复核人', action: 'continue_experiment', rationale: '合成检查理由' } }
  assert.equal(canSaveExperimentReview(state), true)
  for (const change of [{ busy: true }, { loading: true }, { confirmed: false }, { targetHash: null }, { currentHash: 'b'.repeat(64) }, { form: { ...state.form, reviewer: ' ' } }, { form: { ...state.form, rationale: '' } }, { form: { ...state.form, action: 'publish' } }]) assert.equal(canSaveExperimentReview({ ...state, ...change }), false)
})
test('已收尾、已取消请求及读取中的批次不能再次取消', () => {
  const detail = { status: 'active', cancel_requested: false }
  assert.equal(canCancelExperiment(detail, false, false), true)
  assert.equal(canCancelExperiment({ ...detail, status: 'settled' }, false, false), false)
  assert.equal(canCancelExperiment({ ...detail, cancel_requested: true }, false, false), false)
  assert.equal(canCancelExperiment(detail, true, false), false)
  assert.equal(canCancelExperiment(detail, false, true), false)
  assert.equal(canCancelExperiment(null, false, false), false)
})
test('GET 和显式 POST 载荷保持边界与原 request key；请求失败不自动重发', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options) => { calls.push({ url, options }); return new Response(JSON.stringify({ ok: true }), { headers: { 'Content-Type': 'application/json' } }) }
  try {
    await experimentApi('experiments')
    const payload = { ...draft(), request_key: 'same-key', preview_sha256: 'a'.repeat(64), confirm_start: true, allow_model: true }
    await experimentApi('experiments', payload)
    assert.equal(calls[0].options.method, 'GET')
    assert.equal(calls[0].options.body, undefined)
    assert.equal(calls[1].options.method, 'POST')
    assert.deepEqual(JSON.parse(calls[1].options.body), payload)
    globalThis.fetch = async (url, options) => { calls.push({ url, options }); return new Response(JSON.stringify({ detail: 'comparison changed' }), { status: 409, headers: { 'Content-Type': 'application/json' } }) }
    await assert.rejects(experimentApi('experiments/check/reviews', { request_key: 'review-key', comparison_sha256: 'old-hash' }), /409/)
    assert.equal(calls.length, 3)
  } finally { globalThis.fetch = originalFetch }
})
