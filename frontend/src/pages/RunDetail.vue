<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElButton, ElSkeleton, ElEmpty, ElTabs, ElTabPane } from 'element-plus'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/skeleton/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/tabs/style/css'
import 'element-plus/es/components/tab-pane/style/css'
import { snapshotReader, type HistoricalRun } from '../data/history'
import { readRunDetail, type RunDetail } from '../data/run-detail'
import { eventTitle, formatDate, strategyText, taskStatusText } from '../data/display'
import PlanView from '../components/PlanView.vue'
import CodeBlock from '../components/CodeBlock.vue'
import TestView from '../components/TestView.vue'
import EventView from '../components/EventView.vue'

const route = useRoute()
const router = useRouter()
const run = ref<HistoricalRun | null>(null)
// 历史报告整体替换，不需要为递归 JSON 建立深层响应式代理。
const detail = shallowRef<RunDetail | null>(null)
const loading = ref(true)
const error = ref('')
const allRecords = ref(false)
const reportTab = ref('diff')
let loadVersion = 0
const selected = computed(() => {
  const entries = detail.value?.timeline ?? []
  return entries.find(e => e.id === route.query.entry) ?? entries.find(e => e.kind === 'report') ?? [...entries].reverse().find(e => e.kind === 'candidate') ?? [...entries].reverse().find(e => e.kind === 'plan') ?? entries[0]
})
const visibleTimeline = computed(() => (detail.value?.timeline ?? []).filter(entry => allRecords.value || entry.kind !== 'event' || ['RETRIEVAL_COMPLETED', 'TOOL_CONTEXT_PREPARED'].includes(entry.title)))
const dated = computed(() => visibleTimeline.value.filter(e => e.time))
const undated = computed(() => visibleTimeline.value.filter(e => !e.time))
const evidenceLabel = computed(() => ({ recorded: '规划检索证据可关联', not_recorded: '新版检索证据未记录', partial: '检索证据有缺口' })[run.value?.evidence?.status ?? ''] ?? '检索证据未记录')
const models = computed(() => [...new Set(detail.value?.timeline.flatMap(e => e.kind === 'event' && e.data.payload.model ? [e.data.payload.model] : []) ?? [])])
function choose(id: string) { void router.replace({ query: { entry: id } }) }
async function load() {
  const version = ++loadVersion
  loading.value = true
  error.value = ''
  run.value = null
  detail.value = null
  try {
    const snapshot = await snapshotReader.read()
    const found = snapshot.runs.find(r => r.experimentId === route.params.experimentId)
    if (!found) { if (version === loadVersion) error.value = '未找到这个实验的历史记录。'; return }
    const data = await readRunDetail(found.experimentId)
    if (data.taskId !== found.taskId) throw new Error('任务关联不一致，未展示详情。')
    if (version !== loadVersion) return
    run.value = found
    detail.value = data
  } catch (cause) {
    if (version === loadVersion) error.value = cause instanceof Error ? cause.message : '运行详情读取失败'
  } finally { if (version === loadVersion) loading.value = false }
}
watch(() => route.params.experimentId, load, { immediate: true })
watch(() => selected.value?.id, () => { reportTab.value = 'diff' })
</script>

<template>
  <RouterLink to="/experiments" class="back-link">← 实验总览</RouterLink>
  <ElSkeleton v-if="loading" :rows="10" class="loading" />
  <div v-else-if="error" class="error-state" role="alert"><ElEmpty :description="error" /><ElButton @click="load">重新读取</ElButton></div>
  <template v-else-if="run && detail">
    <div class="detail-heading"><div><p class="eyebrow">运行详情 · 历史快照</p><h1>{{ run.caseId }} <span class="heading-strategy">/ {{ strategyText(run.strategy) }}</span></h1></div><span class="quiet">{{ run.caseVersion }}</span></div>
    <p class="run-goal">{{ run.goal }}</p>
    <div class="run-status-strip"><span class="status" :class="{ success: run.taskStatus === 'completed' }">{{ taskStatusText(run.taskStatus) }}</span><span>测试：{{ run.test ? run.test.passed ? 'pytest 执行通过' : 'pytest 未通过' : '未记录' }}</span><span>{{ evidenceLabel }}</span><span class="quiet">全流程事件未完整导出</span></div>
    <p class="drawer-note">数据来源：<code>reports/experiments</code> · {{ run.reportSource ? '终态任务报告与关联快照' : '计划、候选等已有快照' }}。只读历史记录，不反映当前任务状态。</p>
    <details class="run-config inline-details"><summary>运行配置、完整 ID 与来源</summary>
      <dl class="metadata"><dt>实验 ID</dt><dd class="mono">{{ run.experimentId }}</dd><dt>任务 ID</dt><dd class="mono">{{ run.taskId ?? '未记录' }}</dd><dt>仓库 ID</dt><dd class="mono">{{ run.repositoryId ?? '未记录' }}</dd><dt>TestRun ID</dt><dd class="mono">{{ run.test?.id ?? '未记录' }}</dd><dt>初始 commit</dt><dd class="mono">{{ run.commit }}</dd><dt>模型</dt><dd>{{ models.length ? models.join('、') : '未记录' }}（已保存调用范围）</dd><dt>工具预算</dt><dd>{{ run.config.maxToolCalls ?? '未记录' }}</dd><dt>重试次数 / 上限</dt><dd>{{ run.retryCount ?? '未记录' }} / {{ run.config.maxRetries ?? '未记录' }}</dd><dt>Token / 成本</dt><dd>未记录 / 未记录</dd><dt>独立索引版本</dt><dd>未记录</dd></dl>
      <ul class="source-list"><li v-for="source in run.sources" :key="source.path"><code>{{ source.path }}</code><p>{{ formatDate(source.timestamp) }}（日本时间）</p></li></ul>
    </details>
    <p v-for="issue in run.issues" :key="issue" class="issue-note">{{ issue }}</p>
    <div class="detail-workspace">
      <aside class="trace-pane" aria-label="运行时间线">
        <div class="trace-heading"><h2>运行记录</h2><button class="text-control" @click="allRecords = !allRecords">{{ allRecords ? '只看关键记录' : '显示全部记录' }}</button></div>
        <p class="trace-explanation">事件保留原始序号，快照独立标注。显示时间均为日本时间。</p>
        <div class="trace-list">
          <ol>
            <li v-for="entry in dated" :key="entry.id"><button :class="{ selected: selected?.id === entry.id }" :aria-pressed="selected?.id === entry.id" @click="choose(entry.id)"><span class="trace-origin">{{ entry.origin === 'event' ? `事件 #${entry.sequence}` : '文件快照' }}</span><strong>{{ eventTitle(entry.title) }}</strong><time>{{ formatDate(entry.time) }}</time></button></li>
          </ol>
          <template v-if="undated.length"><p class="undated-label">时间未记录 · 不推断发生顺序</p><ol><li v-for="entry in undated" :key="entry.id"><button :class="{ selected: selected?.id === entry.id }" :aria-pressed="selected?.id === entry.id" @click="choose(entry.id)"><span class="trace-origin">{{ entry.origin === 'event' ? `事件 #${entry.sequence}` : '文件快照' }}</span><strong>{{ eventTitle(entry.title) }}</strong><time>时间未记录</time></button></li></ol></template>
        </div>
      </aside>
      <section v-if="selected" class="evidence-pane" aria-label="选中记录详情">
        <div class="record-heading"><p class="eyebrow">{{ selected.origin === 'event' ? `原始事件 #${selected.sequence}` : '文件快照 · 非原始事件' }}</p><h2>{{ eventTitle(selected.title) }}</h2><p class="quiet">{{ formatDate(selected.time) }}{{ selected.time ? '（日本时间）' : '' }} · {{ selected.timeBasis }}</p></div>
        <EventView v-if="selected.kind === 'event'" :payload="selected.data.payload" :event-type="selected.title" :links="detail.contextLinks" />
        <template v-else-if="selected.kind === 'preparation'"><dl class="metadata"><dt>准备状态</dt><dd>{{ selected.data.status }}</dd><dt>记录阶段</dt><dd>{{ selected.data.stage }}</dd><dt>异常类型</dt><dd>{{ selected.data.errorType ?? '未记录' }}</dd><dt>允许修改</dt><dd class="mono">{{ selected.data.editableFiles?.join('、') ?? '未记录' }}</dd><dt>受保护测试</dt><dd class="mono">{{ selected.data.protectedTestFiles?.join('、') ?? '未记录' }}</dd></dl></template>
        <template v-else-if="selected.kind === 'plan'"><p class="drawer-note">检查时任务状态：{{ taskStatusText(selected.data.status) }} · 范围检查：{{ selected.data.scopeStatus ?? '未记录' }}</p><PlanView :plan="selected.data.plan" /></template>
        <template v-else-if="selected.kind === 'review'"><p>{{ selected.data.decision === 'approved' ? '计划已批准' : selected.data.decision === 'rejected' ? '计划已拒绝' : selected.data.decision }}</p><p class="evidence-prose">{{ selected.data.comment ?? '审批意见未记录' }}</p><p class="drawer-note">来自任务快照中的历史审批字段，不提供审批操作，不代替原始审批事件。</p></template>
        <template v-else-if="selected.kind === 'candidate'"><h3 class="mono">{{ selected.data.filePath ?? '文件未记录' }}</h3><p class="evidence-prose">{{ selected.data.summary ?? '说明未记录' }}</p><p class="drawer-note">这是保存的修改候选正文，不能单凭候选证明文件已写入；历史最终 Diff 在终态报告中查看。</p><CodeBlock :text="selected.data.content" /><details class="inline-details"><summary>候选基线 hash</summary><code>{{ selected.data.baseFileHash ?? '未记录' }}</code></details></template>
        <template v-else-if="selected.kind === 'apply'"><dl class="metadata"><dt>文件</dt><dd class="mono">{{ selected.data.filePath ?? '未记录' }}</dd><dt>写入字节数</dt><dd>{{ selected.data.bytesWritten ?? '未记录' }}</dd><dt>新建文件</dt><dd>{{ selected.data.created === null ? '未记录' : selected.data.created ? '是' : '否' }}</dd><dt>候选来源</dt><dd class="mono">{{ selected.data.candidateSource ?? '未记录可关联候选' }}</dd></dl><p class="drawer-note">应用结果文件没有记录精确时间，不能用候选创建时间替代应用时间。</p></template>
        <template v-else-if="selected.kind === 'test'"><p class="drawer-note">{{ selected.data.usedForCompletion ? '该 TestRun 与保存的终态报告关联。' : '该 TestRun 未关联到保存的终态报告；测试通过不自动表示任务完成。' }}</p><TestView :test="selected.data.test" /></template>
        <template v-else-if="selected.kind === 'report'">
          <p class="drawer-note">报告中的任务状态：{{ taskStatusText(selected.data.status) }} · 关联完成事件序号：{{ selected.data.completionEventSequence ?? '未记录' }}。这里是报告引用，未补造该事件。</p>
          <p v-if="selected.data.failure" class="issue-note">终止依据：{{ selected.data.failure.reason }}（{{ selected.data.failure.eventType }} #{{ selected.data.failure.eventSequence }}）</p>
          <ElTabs v-model="reportTab"><ElTabPane label="历史 Diff" name="diff"><template v-if="selected.data.diff"><p class="drawer-note">保存范围：{{ selected.data.diff.scope }} · 修改文件：{{ selected.data.diff.changedFiles.join('、') || '已记录：无' }}。未读取当前工作区。</p><p v-if="selected.data.diff.truncated" class="issue-note">Diff 正文已截断</p><p v-if="selected.data.diff.untrackedFiles.length" class="issue-note">未跟踪文件只保存路径，不含正文：{{ selected.data.diff.untrackedFiles.join('、') }}</p><CodeBlock :text="selected.data.diff.text" diff /></template><p v-else class="quiet">历史 Diff 未记录</p></ElTabPane><ElTabPane label="关联测试" name="test"><TestView :test="selected.data.test" /></ElTabPane><ElTabPane label="最终计划" name="plan"><PlanView :plan="selected.data.plan" /></ElTabPane></ElTabs>
        </template>
        <div class="record-source"><strong>记录来源</strong><code>{{ selected.source }}</code><template v-if="selected.kind === 'event'"><p>事件 ID：<code>{{ selected.data.eventId }}</code> · 节点：{{ selected.data.node }}</p></template></div>
      </section>
    </div>
    <div class="detail-limitations"><p v-for="warning in detail.warnings" :key="warning">{{ warning }}</p><p>正文对常见凭据格式做展示脱敏，源报告保持原样。检索块 hash 无法重建历史源码；成功响应也不能证明模型采纳了全部证据。</p></div>
  </template>
</template>
