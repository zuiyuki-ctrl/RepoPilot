<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElButton, ElDrawer, ElTable, ElTableColumn, ElSelect, ElOption, ElSkeleton, ElEmpty } from 'element-plus'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/drawer/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/skeleton/style/css'
import 'element-plus/es/components/empty/style/css'
import { snapshotReader, type HistorySnapshot, type HistoricalRun } from '../data/history'

const snapshot = ref<HistorySnapshot | null>(null)
const loading = ref(true)
const error = ref('')
const filter = ref('all')
const route = useRoute()
const router = useRouter()
const selected = computed(() => snapshot.value?.runs.find(run => run.experimentId === route.query.record) ?? null)
const drawerOpen = computed({ get: () => Boolean(selected.value), set: value => { if (!value) void router.replace({ query: {} }) } })
const runs = computed(() => snapshot.value?.runs.filter(run => run.taskId) ?? [])
const groups = computed(() => {
  const result = new Map<string, HistoricalRun[]>()
  for (const run of runs.value) {
    if (filter.value === 'completed' && run.taskStatus !== 'completed') continue
    if (filter.value === 'incomplete' && run.reportSource) continue
    const key = `${run.caseId} / ${run.caseVersion}`
    result.set(key, [...result.get(key) ?? [], run])
  }
  return [...result].map(([name, items]) => ({ name, items: items.sort((a, b) => a.strategy === b.strategy ? a.createdAt.localeCompare(b.createdAt) : a.strategy === 'vector' ? -1 : 1) }))
})
const preparations = computed(() => snapshot.value?.runs.filter(run => !run.taskId) ?? [])
const statusText: Record<string, string> = { completed: '任务已完成', approved: '计划已批准', awaiting_review: '等待审批', executing: '执行中', failed: '任务失败', rejected: '已拒绝' }
const strategyText = (strategy: string) => ({ vector: 'Vector', hybrid: 'Hybrid', auto: '自由模式' })[strategy] ?? strategy
const evidenceText = (run: HistoricalRun) => ({ recorded: '规划证据可关联', not_recorded: '未记录新版证据', partial: '部分记录 / 有缺口' })[run.evidence?.status ?? ''] ?? '未记录'
const progressText = (run: HistoricalRun) => ({ candidate_saved: '已保存候选，未记录应用与测试', tested: '已记录测试，未记录终态报告', applied: '已应用，未记录终态报告', plan_snapshot: '已保存计划快照', preparation: '准备记录', terminal_report: '已保存终态报告' })[run.progress]
const formatDate = (value: string | null | undefined) => value ? new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Tokyo', dateStyle: 'medium', timeStyle: 'medium', hour12: false }).format(new Date(value)) : '未记录'
async function load() {
  loading.value = true
  error.value = ''
  try { snapshot.value = await snapshotReader.read() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '读取历史快照失败' }
  finally { loading.value = false }
}
function open(run: HistoricalRun) { void router.push({ query: { record: run.experimentId } }) }
onMounted(load)
</script>

<template>
  <div class="page-heading"><div><p class="eyebrow">EXPERIMENTS</p><h1>实验总览</h1><p class="subtitle">同一个代码任务，两种检索策略。先看结果，再核对过程中的证据。</p></div></div>
  <div class="snapshot-note"><strong>历史快照</strong><span>来自已保存的 JSON 报告，不反映当前任务状态。生成、应用、测试与审批操作均不可用。</span></div>
  <ElSkeleton v-if="loading" :rows="8" animated class="loading" />
  <div v-else-if="error" role="alert" class="error-state"><h2>无法读取历史快照</h2><p>{{ error }}</p><ElButton @click="load">重新读取</ElButton></div>
  <template v-else-if="snapshot">
    <div class="table-toolbar"><div><strong>逐例运行</strong><span class="quiet">{{ runs.length }} 条任务记录 · 按用例版本分组</span></div><ElSelect v-model="filter" aria-label="筛选运行" style="width: 155px"><ElOption label="全部运行" value="all" /><ElOption label="任务已完成" value="completed" /><ElOption label="未记录终态报告" value="incomplete" /></ElSelect></div>
    <p class="mobile-table-note">横向滚动表格，可查看测试、证据与来源。</p>
    <ElEmpty v-if="!groups.length" description="没有符合条件的历史运行" />
    <section v-for="group in groups" :key="group.name" class="case-group">
      <h2 class="case-title"><span class="mono">{{ group.name }}</span><span>{{ group.items.length }} 条记录</span></h2>
      <ElTable :data="group.items" row-key="experimentId" class="run-table">
        <!-- @vue-generic {HistoricalRun} -->
        <ElTableColumn label="策略" width="105"><template #default="{ row }"><strong>{{ strategyText(row.strategy) }}</strong></template></ElTableColumn>
        <!-- @vue-generic {HistoricalRun} -->
        <ElTableColumn label="任务结果" min-width="235"><template #default="{ row }"><span class="status" :class="{ success: row.taskStatus === 'completed' }">{{ row.taskStatus ? (statusText[row.taskStatus] ?? row.taskStatus) : '未记录' }}</span><p class="cell-note">{{ progressText(row) }}</p></template></ElTableColumn>
        <!-- @vue-generic {HistoricalRun} -->
        <ElTableColumn label="测试结果" min-width="200"><template #default="{ row }"><span v-if="row.test">{{ row.test.passed ? 'pytest 执行通过' : 'pytest 未通过' }}</span><span v-else class="quiet">未记录</span><p class="cell-note mono">{{ row.test?.summary ?? '测试汇总未记录' }}</p></template></ElTableColumn>
        <!-- @vue-generic {HistoricalRun} -->
        <ElTableColumn label="证据状态" min-width="210"><template #default="{ row }"><span :class="{ quiet: row.evidence?.status !== 'recorded' }">{{ evidenceText(row) }}</span><p class="cell-note">全流程事件未完整导出</p><p v-if="row.issues.length" class="issue-note">关联需复核</p></template></ElTableColumn>
        <!-- @vue-generic {HistoricalRun} -->
        <ElTableColumn label="详情 / 来源" width="138"><template #default="{ row }"><RouterLink :to="`/runs/${row.experimentId}`" class="detail-link">运行详情 →</RouterLink><br /><ElButton link type="primary" @click="open(row)">查看来源</ElButton></template></ElTableColumn>
      </ElTable>
    </section>
    <p class="interpretation">测试通过与证据完整是独立维度。pytest 汇总中的耗时仅属于 pytest；这些逐例记录尚不足以证明 Hybrid 整体更优，也未验证 Reflection 恢复路径。</p>
    <details v-if="preparations.length" class="preparations"><summary>其他准备记录 <span class="quiet">{{ preparations.length }} 条 · 尚未创建任务</span></summary><div v-for="run in preparations" :key="run.experimentId" class="preparation-row"><div><strong>{{ run.caseId }} / {{ strategyText(run.strategy) }}</strong><p class="cell-note">{{ run.preparationStatus === 'error' ? '准备失败' : '准备阶段快照' }} · {{ run.preparationStage }}<span v-if="run.preparationError"> · {{ run.preparationError }}</span></p></div><ElButton link type="primary" @click="open(run)">查看来源</ElButton></div></details>
    <footer class="data-footer">整理时间 {{ formatDate(snapshot.generatedAt) }}（日本时间） · 来源 <code>{{ snapshot.sourceRoot }}</code><span>重新启动开发服务或构建时更新快照</span></footer>
  </template>

  <ElDrawer v-model="drawerOpen" title="历史记录与数据来源" size="min(640px, 100vw)">
    <template v-if="selected">
      <p class="eyebrow">历史快照 · 只读</p><h2>{{ selected.caseId }} / {{ strategyText(selected.strategy) }}</h2><p class="drawer-goal">{{ selected.goal }}</p>
      <dl class="metadata"><dt>用例版本</dt><dd>{{ selected.caseVersion }}</dd><dt>实验 ID</dt><dd class="mono">{{ selected.experimentId }}</dd><dt>任务 ID</dt><dd class="mono">{{ selected.taskId ?? '未记录' }}</dd><dt>仓库 ID</dt><dd class="mono">{{ selected.repositoryId ?? '未记录' }}</dd><dt>初始 commit</dt><dd class="mono">{{ selected.commit }}</dd><dt>任务状态</dt><dd>{{ selected.taskStatus ? `${statusText[selected.taskStatus] ?? selected.taskStatus}（${selected.taskStatus}）` : '未记录' }}<p class="cell-note">状态来自保存文件，非实时查询</p></dd><dt>最后记录阶段</dt><dd>{{ progressText(selected) }}</dd><dt>TestRun ID</dt><dd class="mono">{{ selected.test?.id ?? '未记录' }}</dd><dt>测试镜像</dt><dd class="mono">{{ selected.test?.image ?? '未记录' }}</dd><dt>测试快照 hash</dt><dd class="mono">{{ selected.test?.snapshotHash ?? '未记录' }}</dd><dt>工具调用预算</dt><dd>{{ selected.config.maxToolCalls ?? '未记录' }}</dd><dt>重试次数 / 上限</dt><dd>{{ selected.retryCount ?? '未记录' }} / {{ selected.config.maxRetries ?? '未记录' }}</dd></dl>
      <h3>证据覆盖</h3><p>{{ evidenceText(selected) }}</p><p class="drawer-note">{{ selected.evidence ? `导出时任务状态：${selected.evidence.taskStatusAtExport ?? '未记录'}；读取至事件序号 ${selected.evidence.lastSequence}，实际保留 ${selected.evidence.savedEventCount ?? '未记录'} 条相关事件。` : '未发现检索证据导出。' }} 记录可关联不代表模型语义上采纳了全部证据，终态报告也不能替代完整事件流。</p>
      <p v-for="warning in selected.evidence?.warnings" :key="warning" class="issue-note">{{ warning }}</p><p v-for="issue in selected.issues" :key="issue" class="issue-note">{{ issue }}</p>
      <h3>来源文件</h3><p class="drawer-note">“用于汇总”标注参与当前展示的文件；重复导出仍保留。时间取文件内导出、检查、创建或完成时间，无记录则显示“未记录”，不使用磁盘修改时间。</p><ol class="source-list"><li v-for="source in selected.sources" :key="source.path"><code>{{ source.path }}</code><p>{{ formatDate(source.timestamp) }} <span v-if="source.selected">· 用于汇总</span></p></li></ol>
    </template>
  </ElDrawer>
</template>

