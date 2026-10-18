<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { readLive, type PlatformRun, type PlatformTraceEvent, type PlatformTracePage, type RunControl, type PlatformReport } from '../data/platform-runs'
const route = useRoute()
const run = ref<PlatformRun | null>(null)
const events = ref<PlatformTraceEvent[]>([])
const traceBoundary = ref<number | null>(null)
const expanded = ref<number | null>(null)
const error = ref('')
const loading = ref(false)
const more = ref(false)
const control = ref<RunControl | null>(null)
const report = ref<PlatformReport | null>(null)
const submitting = ref(false)
const comment = ref('')
let generation = 0
async function load(append = false) {
  const current = ++generation
  const id = encodeURIComponent(String(route.params.runId))
  loading.value = true; error.value = ''
  if (!append) { run.value = null; control.value = null; report.value = null; events.value = []; more.value = false; traceBoundary.value = null; expanded.value = null }
  try {
    const after = append ? events.value.at(-1)?.sequence ?? 0 : 0
    const [detail, page, controls, evidence] = await Promise.all([
      readLive<PlatformRun>(`/${id}`),
      readLive<PlatformTracePage>(`/${id}/trace?after_sequence=${after}&limit=50${append && traceBoundary.value !== null ? `&through_sequence=${traceBoundary.value}` : ''}`),
      readLive<RunControl | null>(`/${id}/control`),
      readLive<PlatformReport>(`/${id}/report`),
    ])
    if (current !== generation) return
    run.value = detail; events.value = append ? [...events.value, ...page.items] : page.items
    control.value = controls
    report.value = evidence
    traceBoundary.value = page.through_sequence
    more.value = page.has_more
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
      && expanded.value === null
      && (run.value.lifecycle !== 'awaiting_input' || control.value?.checkpoint?.decision)
      && !['finished', 'interrupted'].includes(run.value.lifecycle)) void load()
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
        <p v-if="run.lifecycle === 'evaluating'">Agent 执行已结束，等待平台独立验收。旧开发入口未绑定权威测试包的 Run 仍保持待验收。</p>
      </section>
      <section v-if="report">
        <h2>平台独立评测</h2>
        <p>结论：{{ report.evaluation_outcome }} · 原因：{{ report.reason ?? '尚未生成' }}</p>
        <p>最终源码快照：{{ report.final_snapshot_hash ?? '未采集' }}</p>
        <details><summary>原始基线与最终测试（平台采集）</summary>
          <pre class="approval-content">基线：{{ JSON.stringify(report.baseline_test, null, 2) }}
最终：{{ JSON.stringify(report.final_test, null, 2) }}</pre>
        </details>
        <p>Diff 证据：{{ report.artifact_status }} · 修改文件：{{ report.changed_files.join(', ') || '无记录' }}</p>
        <pre v-if="report.diff !== null" class="approval-content">{{ report.diff || '无源码差异' }}</pre>
        <p v-if="report.diff_truncated">页面仅展示前 50,000 字符；后台保存完整 Diff。</p>
        <p v-if="report.process.protocol_error" role="alert">Agent 协议错误：{{ report.process.protocol_error }}</p>
        <p v-if="run.agent.adapter === 'process'">外部上报轨迹：{{ report.process.trace_status }}。未上报用量不代表 Token 为零。</p>
        <details v-if="report.process.stdout !== null"><summary>外部 Agent 日志（不是平台验收结果）</summary>
          <pre class="approval-content">{{ report.process.stdout }}{{ report.process.stderr }}</pre>
          <p v-if="report.process.stdout_truncated || report.process.stderr_truncated">日志已截断，不代表完整输出。</p>
        </details>
      </section>
      <p>观测摘要：{{ run.observation.level }} / {{ run.observation.completeness }}。层级不是任务能力评分。</p>
      <p>available = 有可用证据；partial = 部分记录；missing = 缺失；unsupported = 未支持；invalid = 无效。
        not_occurred 必须有明确证据，不能从“没有事件”推断。应有数未知时不计算覆盖率；记录数也不等于模型调用数。</p>
      <table><thead><tr><th>能力</th><th>声明 / 校验</th><th>实际证据</th><th>阶段发生</th><th>来源</th><th>记录数 / 应有数</th><th>事件序号</th></tr></thead>
        <tbody><tr v-for="(value, name) in run.observation.capabilities" :key="name">
          <td>{{ name }}</td><td>{{ value.declared }} / {{ value.validated }}</td><td>{{ value.availability }}</td>
          <td>{{ value.occurrence }}</td><td>{{ value.source }}</td><td>{{ value.recorded_records }} / {{ value.expected_records ?? '未知' }}</td>
          <td>{{ value.evidence_sequences.join(', ') || '未记录' }}</td>
        </tr></tbody>
      </table>
      <h2>Trace · 已保存证据</h2>
      <p>本次翻页截至平台事件 #{{ traceBoundary }}，刷新可查看新增事件。时间为平台落库时间，外部 Agent 的实际发生时间未知。
        展开详情时暂停自动刷新。未支持的字段不会补造。</p>
      <p>RETRIEVAL_COMPLETED 是工具返回结果；TOOL_CONTEXT_PREPARED 是预算处理后的消息摘要；
        MODEL_CALL_STARTED 的 tool_context 是该次请求包含的摘要清单。hash 一致可核对消息身份，但不证明模型理解或采纳了代码。</p>
      <ol class="trace-list"><li v-for="event in events" :key="event.id">
        <button :aria-expanded="expanded === event.sequence" @click="expanded = expanded === event.sequence ? null : event.sequence">
          #{{ event.sequence }} · {{ event.event_type }} · {{ event.source }}
        </button>
        <span> · {{ event.created_at }}</span>
        <section v-if="expanded === event.sequence">
          <p v-if="event.legacy_sequence !== null">Native 原任务 {{ event.legacy_task_id }} · 原事件 #{{ event.legacy_sequence }} · 节点 {{ event.node_name }}</p>
          <p>展示状态：{{ event.detail_status }}。仅展示允许公开的已记录字段，不返回原始请求、认证信息或工作区文件正文。</p>
          <p v-if="event.truncated">详情已截断，仅用于浏览；不能作为完整证据导出。</p>
          <pre class="approval-content">{{ JSON.stringify(event.details, null, 2) }}</pre>
        </section>
      </li></ol>
      <button v-if="more" :disabled="loading" @click="load(true)">加载后续事件</button>
    </template>
  </section>
</template>
<style scoped>
.live-detail { padding: 24px; } table { width: 100%; border-collapse: collapse; } th, td { text-align: left; padding: 8px; border-bottom: 1px solid #ddd; } [role=alert] { color: #a52a2a; }
.approval-content { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 540px; overflow: auto; padding: 16px; background: #f5f7fa; }
.trace-list { padding-left: 24px; } .trace-list li { margin: 12px 0; } .trace-list button { text-align: left; }
</style>
