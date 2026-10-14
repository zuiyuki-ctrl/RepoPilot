<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { readLive, type PlatformRun, type PlatformEvent, type RunControl } from '../data/platform-runs'
const route = useRoute()
const run = ref<PlatformRun | null>(null)
const events = ref<PlatformEvent[]>([])
const error = ref('')
const loading = ref(false)
const more = ref(false)
const control = ref<RunControl | null>(null)
const submitting = ref(false)
const comment = ref('')
let generation = 0
async function load(append = false) {
  const current = ++generation
  const id = encodeURIComponent(String(route.params.runId))
  loading.value = true; error.value = ''
  if (!append) { run.value = null; control.value = null; events.value = []; more.value = false }
  try {
    const after = append ? events.value.at(-1)?.sequence ?? 0 : 0
    const [detail, page, controls] = await Promise.all([
      readLive<PlatformRun>(`/${id}`),
      readLive<{ items: PlatformEvent[]; next_after_sequence: number }>(`/${id}/events?after_sequence=${after}&limit=50`),
      readLive<RunControl | null>(`/${id}/control`),
    ])
    if (current !== generation) return
    run.value = detail; events.value = append ? [...events.value, ...page.items] : page.items
    control.value = controls
    more.value = page.items.length === 50
  } catch (e) { if (current === generation) error.value = e instanceof Error ? e.message : '读取失败' }
  finally { if (current === generation) loading.value = false }
}
async function decide(decision: 'approved' | 'rejected') {
  const cp = control.value?.checkpoint
  if (!cp || submitting.value) return
  const id = String(route.params.runId)
  submitting.value = true; error.value = ''
  try {
    await readLive(`/${encodeURIComponent(id)}/checkpoints/${cp.id}/decision`, {
      expected_version: cp.run_version, payload_sha256: cp.payload_sha256, decision, comment: comment.value,
    })
    if (id === String(route.params.runId)) { comment.value = ''; await load() }
  } catch (e) { if (id === String(route.params.runId)) error.value = e instanceof Error ? e.message : '审批失败' }
  finally { submitting.value = false }
}
async function cancel() {
  if (!run.value || submitting.value) return
  const id = run.value.id
  submitting.value = true; error.value = ''
  try {
    await readLive(`/${encodeURIComponent(id)}/cancel`, { expected_version: run.value.version })
    if (id === String(route.params.runId)) await load()
  } catch (e) { if (id === String(route.params.runId)) error.value = e instanceof Error ? e.message : '取消失败' }
  finally { submitting.value = false }
}
watch(() => route.params.runId, () => { comment.value = ''; void load() }, { immediate: true })
// 审批内容不自动替换，防止用户阅读途中批准另一份候选；执行阶段定时更新元数据。
const timer = window.setInterval(() => {
  if (!loading.value && !submitting.value && run.value
      && (run.value.lifecycle !== 'awaiting_input' || control.value?.checkpoint?.decision)
      && !['finished', 'interrupted', 'evaluating'].includes(run.value.lifecycle)) void load()
}, 3000)
onUnmounted(() => { window.clearInterval(timer); generation++ })
</script>
<template>
  <section class="live-detail">
    <RouterLink to="/live/runs">返回实时运行</RouterLink>
    <h1>运行详情 · live</h1><button :disabled="loading" @click="load()">刷新</button>
    <p v-if="loading" role="status">读取后端数据…</p><p v-if="error" role="alert">{{ error }}</p>
    <template v-if="run">
      <p>{{ run.case_id }} / {{ run.case_version }} · {{ run.agent.name }} {{ run.agent.version }}</p>
      <p>运行阶段：{{ run.lifecycle }}　执行结果：{{ run.execution_status }}　平台验收：{{ run.evaluation_outcome }}</p>
      <section v-if="control">
        <p>步骤：{{ control.stage }} · {{ control.active ? 'worker 执行中' : control.ready ? '等待 worker 领取' : '暂停或结束' }}
          · 清理：{{ control.cleanup_status }} · 已结算活跃时间：{{ control.active_seconds.toFixed(1) }} 秒</p>
        <p v-if="control.error_code" role="alert">执行问题：{{ control.error_code }}</p>
        <p v-if="control.cleanup_error_code" role="alert">清理问题：{{ control.cleanup_error_code }}</p>
        <p v-if="control.interruption_token">未解决执行标记：{{ control.interruption_token }}。确认旧 worker 及其子进程停止后，按操作文档解除阻塞。</p>
        <p v-if="control.cancel_requested">取消请求已登记。执行中强制停止可能留下未确认的副作用，请关注清理状态。</p>
        <button v-else-if="!['finished', 'interrupted', 'evaluating'].includes(run.lifecycle)"
          :disabled="loading || submitting" @click="cancel">请求取消运行</button>
        <template v-if="control.checkpoint">
          <h2>{{ control.checkpoint.kind === 'plan' ? '计划审批' : '完整候选审批' }}</h2>
          <p>检查点：{{ control.checkpoint.id }} · 决定：{{ control.checkpoint.decision ?? '待决定' }}</p>
          <pre class="approval-content">{{ JSON.stringify(control.checkpoint.payload, null, 2) }}</pre>
          <template v-if="!control.checkpoint.decision && run.lifecycle === 'awaiting_input' && !control.cancel_requested">
            <label>审批备注 <input v-model="comment" maxlength="1000" /></label>
            <button :disabled="submitting || loading" @click="decide('approved')">批准这份内容</button>
            <button :disabled="submitting || loading" @click="decide('rejected')">拒绝并终止</button>
          </template>
        </template>
        <p v-if="run.lifecycle === 'evaluating'">Agent 执行已结束。独立验收采集将在 Day 3 接通；这里不会提前显示通过。</p>
      </section>
      <p>观测摘要：{{ run.observation.level }} / {{ run.observation.completeness }}。层级不是任务能力评分。</p>
      <table><thead><tr><th>能力</th><th>声明 / 校验</th><th>实际证据</th><th>阶段发生</th><th>来源</th><th>记录数 / 应有数</th><th>事件序号</th></tr></thead>
        <tbody><tr v-for="(value, name) in run.observation.capabilities" :key="name">
          <td>{{ name }}</td><td>{{ value.declared }} / {{ value.validated }}</td><td>{{ value.availability }}</td>
          <td>{{ value.occurrence }}</td><td>{{ value.source }}</td><td>{{ value.recorded_records }} / {{ value.expected_records ?? '未知' }}</td>
          <td>{{ value.evidence_sequences.join(', ') || '未记录' }}</td>
        </tr></tbody>
      </table>
      <h2>运行事件</h2><p>Native 阶段结束后映射调用、检索和上下文事件。当前字段标为部分证据，不冒充完整 L2。</p>
      <ol><li v-for="event in events" :key="event.id">#{{ event.sequence }} · {{ event.event_type }} · {{ event.source }} · {{ event.created_at }}</li></ol>
      <button v-if="more" :disabled="loading" @click="load(true)">加载后续事件</button>
    </template>
  </section>
</template>
<style scoped>
.live-detail { padding: 24px; } table { width: 100%; border-collapse: collapse; } th, td { text-align: left; padding: 8px; border-bottom: 1px solid #ddd; } [role=alert] { color: #a52a2a; }
.approval-content { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 540px; overflow: auto; padding: 16px; background: #f5f7fa; }
</style>
