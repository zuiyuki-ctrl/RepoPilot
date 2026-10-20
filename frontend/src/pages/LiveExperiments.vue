<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElButton, ElDrawer, ElForm, ElFormItem, ElInput, ElInputNumber, ElSelect, ElOption, ElCheckbox, ElTable, ElTableColumn, ElTabs, ElTabPane, ElEmpty, ElSkeleton } from 'element-plus'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/drawer/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/input-number/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/checkbox/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import 'element-plus/es/components/tabs/style/css'
import 'element-plus/es/components/tab-pane/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/skeleton/style/css'
import AppIcon from '../components/AppIcon.vue'
import ExperimentComparisonPanel from '../components/ExperimentComparisonPanel.vue'
import ExperimentReviewPanel from '../components/ExperimentReviewPanel.vue'
import { type ExperimentComparison, type ExperimentReview } from '../data/platform-comparison'
import { experimentApi as api, draftBody, validDraft, previewMatches, canStartExperiment, canSaveExperimentReview, canCancelExperiment,
  type CatalogVersion, type ExperimentListItem, type ExperimentMember, type ExperimentDetail, type ExperimentDraft, type QualityPolicy, type ExperimentPreview, type ReviewForm } from '../data/platform-experiments'
import { statusLabel } from '../data/dashboard'
import { formatDate } from '../data/display'
import '../experiments.css'

const route = useRoute()
const router = useRouter()
const agents = shallowRef<CatalogVersion[]>([])
const suites = shallowRef<CatalogVersion[]>([])
const experiments = shallowRef<ExperimentListItem[]>([])
const detail = shallowRef<ExperimentDetail | null>(null)
const comparison = shallowRef<ExperimentComparison | null>(null)
const reviews = shallowRef<ExperimentReview[]>([])
const listLoading = ref(true), detailLoading = ref(false), catalogConnected = ref(false)
const listError = ref(''), detailError = ref(''), comparisonError = ref(''), reviewError = ref(''), operationError = ref('')
const busy = ref(false), busyAction = ref(''), search = ref('')
const creationOpen = ref(false), createStep = ref('config'), activeTab = ref('runs')
const draft = ref<ExperimentDraft>({ name: 'Demo 对比', suite_id: '', baseline_agent_id: '', candidate_agent_id: '', mode: 'benchmark', changed_fields: [], repetitions: 1, timeout_seconds: 60, order: 'baseline_first', intervention: 'adapter_default', decision_policy: null })
const fields = ref(''), policyEnabled = ref(false)
const policy = ref<QualityPolicy>({ version: 1, min_pairs: 1, min_cases: 1, max_regressions: 0, min_pass_delta_pp: 0 })
const preview = shallowRef<ExperimentPreview | null>(null)
const frozenDraft = shallowRef<ExperimentDraft | null>(null)
const confirmed = ref(false), allowModel = ref(false)
const reviewTarget = shallowRef<ExperimentComparison | null>(null)
const reviewConfirmed = ref(false)
const reviewForm = ref<ReviewForm>({ reviewer: '', action: 'continue_experiment', rationale: '' })
let requestKey = '', reviewKey = '', selectionGeneration = 0, disposed = false
let timer: ReturnType<typeof setInterval> | undefined
const selectedId = computed(() => typeof route.query.id === 'string' ? route.query.id : '')
const filteredExperiments = computed(() => experiments.value.filter(item => `${item.name} ${item.id}`.toLowerCase().includes(search.value.trim().toLowerCase())))
const selectedName = computed(() => experiments.value.find(item => item.id === detail.value?.id)?.name ?? '实验详情')
const currentDraft = computed(() => draftBody(draft.value, fields.value, policyEnabled.value, policy.value))
const currentPreview = computed(() => previewMatches(frozenDraft.value, currentDraft.value))
const canPreview = computed(() => catalogConnected.value && !busy.value && validDraft(currentDraft.value)
  && suites.value.some(suite => suite.id === draft.value.suite_id) && agents.value.some(agent => agent.id === draft.value.baseline_agent_id) && agents.value.some(agent => agent.id === draft.value.candidate_agent_id))
const canStart = computed(() => canStartExperiment({ busy: busy.value, connected: catalogConnected.value, current: currentPreview.value, confirmed: confirmed.value, allowModel: allowModel.value, preview: preview.value }))
const currentComparison = computed(() => comparison.value?.experiment_id === detail.value?.id ? comparison.value : null)
const canSaveReview = computed(() => canSaveExperimentReview({ busy: busy.value, loading: detailLoading.value, confirmed: reviewConfirmed.value,
  targetHash: reviewTarget.value?.comparison_sha256 ?? null, currentHash: currentComparison.value?.comparison_sha256 ?? null, form: reviewForm.value }))
const canCancel = computed(() => !detailError.value && canCancelExperiment(detail.value, busy.value, detailLoading.value))
const errorText = (cause: unknown) => cause instanceof Error ? cause.message : String(cause)
watch(currentDraft, () => { confirmed.value = false; allowModel.value = false }, { deep: true })

async function load() {
  listLoading.value = true
  catalogConnected.value = false
  listError.value = ''
  try {
    const [a, s, e] = await Promise.all([api<CatalogVersion[]>('agents'), api<CatalogVersion[]>('benchmarks'), api<ExperimentListItem[]>('experiments')])
    if (disposed) return
    if (![a, s, e].every(Array.isArray)) throw new Error('实验或版本列表格式不符合约定。')
    agents.value = a.filter(version => version.status === 'ready')
    suites.value = s.filter(version => version.status === 'ready')
    experiments.value = e
    catalogConnected.value = true
  } catch (cause) { if (!disposed) listError.value = errorText(cause) }
  finally { if (!disposed) listLoading.value = false }
}
async function inspect() {
  if (!canPreview.value) return
  busy.value = true; busyAction.value = 'preview'; operationError.value = ''; confirmed.value = false; allowModel.value = false; preview.value = null
  const body = structuredClone(currentDraft.value)
  try {
    const result = await api<ExperimentPreview>('experiments/preview', body)
    if (typeof result.manifest?.needs_model !== 'boolean' || !Number.isInteger(result.manifest.run_count) || result.manifest.run_count < 1 || result.manifest.run_count > 40
      || !Array.isArray(result.manifest.changed_fields) || !/^[a-f0-9]{64}$/.test(result.preview_sha256)) throw new Error('冻结预览格式不符合约定，不能启动。')
    preview.value = result; frozenDraft.value = body; requestKey = crypto.randomUUID(); createStep.value = 'preview'
  } catch (cause) { operationError.value = errorText(cause) }
  finally { busy.value = false; busyAction.value = '' }
}
async function start() {
  if (!canStart.value || !preview.value || !frozenDraft.value) return
  busy.value = true; busyAction.value = 'start'; operationError.value = ''
  try {
    const result = await api<{ id: string }>('experiments', { ...frozenDraft.value, request_key: requestKey, preview_sha256: preview.value.preview_sha256, confirm_start: true, allow_model: allowModel.value })
    if (disposed) return
    if (!result.id) throw new Error('未返回实验 ID，请核对后端记录；不要盲目重复创建。')
    if (selectedId.value === result.id) await open(result.id)
    else await router.replace({ query: { id: result.id } })
    creationOpen.value = false; confirmed.value = false; allowModel.value = false; preview.value = null; frozenDraft.value = null; createStep.value = 'config'
    await load()
  } catch (cause) { operationError.value = errorText(cause) }
  finally { busy.value = false; busyAction.value = '' }
}
function select(id: string) {
  if (busy.value) return
  if (id === selectedId.value) void open(id)
  else void router.replace({ query: { id } })
}
async function open(id: string) {
  const generation = ++selectionGeneration
  detailLoading.value = true; detailError.value = ''
  if (detail.value?.id !== id) { detail.value = null; comparison.value = null; reviews.value = []; reviewTarget.value = null; reviewConfirmed.value = false }
  comparisonError.value = ''
  const key = encodeURIComponent(id)
  const [record, compared, decisions] = await Promise.allSettled([
    api<ExperimentDetail>(`experiments/${key}`), api<ExperimentComparison>(`experiments/${key}/comparison`), api<ExperimentReview[]>(`experiments/${key}/reviews`),
  ])
  if (generation !== selectionGeneration || disposed) return
  if (record.status === 'fulfilled' && record.value.id === id) detail.value = record.value
  else detailError.value = record.status === 'rejected' ? errorText(record.reason) : '实验关联不一致，未展示新结果。'
  if (compared.status === 'fulfilled' && compared.value.experiment_id === id) comparison.value = compared.value
  else { comparison.value = null; comparisonError.value = compared.status === 'rejected' ? errorText(compared.reason) : '比较结果不属于当前实验。' }
  if (decisions.status === 'fulfilled' && Array.isArray(decisions.value)) { reviews.value = decisions.value; reviewError.value = '' }
  else { reviews.value = []; reviewError.value = decisions.status === 'rejected' ? errorText(decisions.reason) : '人工记录格式不符合约定。' }
  detailLoading.value = false
}
function beginReview() {
  if (!currentComparison.value || busy.value || detailLoading.value) return
  reviewTarget.value = structuredClone(currentComparison.value); reviewKey = crypto.randomUUID(); reviewConfirmed.value = false
}
async function saveReview() {
  const target = reviewTarget.value
  if (!target || !canSaveReview.value) return
  busy.value = true; busyAction.value = 'review'; operationError.value = ''
  try {
    await api(`experiments/${encodeURIComponent(target.experiment_id)}/reviews`, { ...reviewForm.value, request_key: reviewKey, comparison_sha256: target.comparison_sha256 })
    if (disposed) return
    reviewTarget.value = null; reviewConfirmed.value = false
    if (selectedId.value === target.experiment_id) await open(target.experiment_id)
  } catch (cause) { operationError.value = errorText(cause) }
  finally { busy.value = false; busyAction.value = '' }
}
async function cancel() {
  if (!detail.value || !canCancel.value) return
  const id = detail.value.id
  busy.value = true; busyAction.value = 'cancel'; operationError.value = ''
  try { await api(`experiments/${encodeURIComponent(id)}/cancel`, {}); if (!disposed && selectedId.value === id) await open(id) }
  catch (cause) { operationError.value = errorText(cause) }
  finally { busy.value = false; busyAction.value = '' }
}
async function download(format: 'json' | 'markdown') {
  if (!detail.value || !currentComparison.value || busy.value || detailLoading.value) return
  const id = detail.value.id
  busy.value = true; busyAction.value = `export-${format}`; operationError.value = ''
  try {
    const response = await fetch(`/api/v2/experiments/${encodeURIComponent(id)}/export?format=${format}`, { cache: 'no-store', signal: AbortSignal.timeout(30000) })
    if (!response.ok) throw new Error(`导出失败：HTTP ${response.status}`)
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a'); link.href = url
    link.download = response.headers.get('content-disposition')?.match(/filename="([^"]+)"/)?.[1] ?? `experiment-${id}.${format === 'json' ? 'json' : 'md'}`
    document.body.appendChild(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (cause) { operationError.value = errorText(cause) }
  finally { busy.value = false; busyAction.value = '' }
}
watch(selectedId, id => {
  activeTab.value = 'runs'
  if (id) void open(id)
  else { selectionGeneration++; detail.value = null; comparison.value = null; reviewTarget.value = null; reviews.value = []; detailLoading.value = false; detailError.value = '' }
}, { immediate: true })
onMounted(() => {
  void load()
  timer = setInterval(() => { if (detail.value && !busy.value && !detailLoading.value) void open(detail.value.id) }, 5000)
})
onUnmounted(() => { disposed = true; clearInterval(timer); selectionGeneration++ })
</script>

<template>
  <div class="experiments-page">
    <div class="ui-page-heading"><div><p class="ui-kicker">固定版本 · 可核查比较</p><h1>实验批次</h1><p class="ui-page-description">组织 Baseline 与 Candidate，按同一用例核对运行、验收与决定。</p></div><div class="experiment-heading-actions"><ElButton :disabled="busy" :loading="listLoading" @click="load"><AppIcon name="refresh" :size="16" />刷新列表</ElButton><ElButton type="primary" :disabled="busy" @click="creationOpen = true"><AppIcon name="experiment" :size="16" />新建实验</ElButton></div></div>
    <div v-if="operationError && !creationOpen" role="alert" class="experiment-alert">{{ operationError }}</div>
    <section class="ui-card experiment-list-card">
      <div class="ui-card-heading"><div><h2>已保存实验</h2><p>{{ listLoading ? '正在读取列表' : catalogConnected ? `已加载 ${experiments.length} 条 · 当前数据库` : listError ? '列表连接未确认' : '尚未读取' }} · 最多展示最近 50 条</p></div><ElInput v-model="search" clearable aria-label="搜索实验名称或 ID" placeholder="搜索名称或 ID" class="experiment-search" /></div>
      <p v-if="listError" role="alert" class="experiment-alert">列表读取失败：{{ listError }}<span v-if="experiments.length"> · 当前保留上次读取的列表。</span></p>
      <ElSkeleton v-if="listLoading && !experiments.length" :rows="3" class="experiment-loading" />
      <ElTable v-else-if="filteredExperiments.length" :data="filteredExperiments" class="experiment-table" row-key="id" :row-class-name="({ row }: { row: ExperimentListItem }) => row.id === selectedId ? 'selected-experiment-row' : ''">
        <!-- @vue-generic {ExperimentListItem} -->
        <ElTableColumn label="实验名称 / ID" min-width="260"><template #default="{ row }"><button class="experiment-name-button" :disabled="busy" @click="select(row.id)">{{ row.name }}</button><span class="experiment-cell-id mono">{{ row.id }}</span></template></ElTableColumn>
        <!-- @vue-generic {ExperimentListItem} -->
        <ElTableColumn label="创建时间（日本时间）" min-width="190"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></ElTableColumn>
        <!-- @vue-generic {ExperimentListItem} -->
        <ElTableColumn label="取消请求" min-width="130"><template #default="{ row }">{{ row.cancel_requested === undefined ? '未记录' : row.cancel_requested ? '已请求' : '未请求' }}</template></ElTableColumn>
        <!-- @vue-generic {ExperimentListItem} -->
        <ElTableColumn label="操作" width="120"><template #default="{ row }"><ElButton link type="primary" :disabled="busy" @click="select(row.id)">{{ row.id === selectedId ? '当前批次' : '查看批次 →' }}</ElButton></template></ElTableColumn>
      </ElTable>
      <ElEmpty v-else :description="search ? '没有符合条件的实验' : listError ? '连接后可读取已保存实验' : '还没有保存的实验批次'" :image-size="64"><ElButton v-if="!search && !listError" :disabled="busy" @click="creationOpen = true">创建第一个实验</ElButton></ElEmpty>
    </section>
    <div v-if="detailError" role="alert" class="experiment-alert">批次读取失败：{{ detailError }}<span v-if="detail"> · 下面保留上次读取的批次记录，当前不能取消执行。</span><ElButton v-if="selectedId" link type="primary" :disabled="busy || detailLoading" @click="open(selectedId)">重新读取</ElButton></div>
    <section v-if="detailLoading && !detail" class="ui-card experiment-loading"><ElSkeleton :rows="6" /></section>
    <section v-else-if="detail" class="ui-card experiment-detail-card">
      <div class="ui-card-heading"><div><p class="ui-kicker">当前批次</p><h2>{{ selectedName }}</h2><p><span class="experiment-badge">{{ detail.status === 'settled' ? '已收尾' : detail.status === 'active' ? '进行中' : statusLabel(detail.status) }}</span><span class="experiment-muted">{{ detailLoading ? ' · 正在更新' : ' · 每 5 秒读取当前批次' }}</span></p></div><ElButton :disabled="busy || detailLoading" @click="open(detail.id)">刷新批次</ElButton></div>
      <details class="experiment-details experiment-detail-identity"><summary>完整 ID、指纹与冻结清单</summary><dl class="metadata"><dt>实验 ID</dt><dd class="mono">{{ detail.id }}</dd><dt>清单 SHA256</dt><dd class="mono">{{ detail.manifest_sha256 }}</dd><dt>创建时间</dt><dd>{{ formatDate(detail.created_at) }}</dd><dt>取消已请求</dt><dd>{{ detail.cancel_requested ? '是' : '否' }}</dd></dl><pre>{{ JSON.stringify(detail.manifest, null, 2) }}</pre></details>
      <ElTabs v-model="activeTab" class="experiment-tabs">
        <ElTabPane label="运行与配对" name="runs">
          <div class="experiment-tab-body"><div class="experiment-section-heading"><div><h3>批次成员</h3><p>准备、生命周期、执行结果和平台验收分别展示。</p></div><ElButton plain type="danger" :disabled="!canCancel" :loading="busyAction === 'cancel'" @click="cancel">取消剩余执行</ElButton></div><p class="experiment-note">取消向当前批次剩余执行发出请求，不改写已有结果；已收尾或已请求取消的批次不可重复取消。</p>
            <ElTable :data="detail.members" class="experiment-table" row-key="id" empty-text="该批次未返回成员记录">
              <!-- @vue-generic {ExperimentMember} -->
              <ElTableColumn label="顺序 / Case / 重复" min-width="170"><template #default="{ row }">{{ row.sequence }} / {{ row.case_index + 1 }} / {{ row.repetition }}</template></ElTableColumn>
              <!-- @vue-generic {ExperimentMember} -->
              <ElTableColumn label="分组" width="115"><template #default="{ row }">{{ row.arm === 'baseline' ? 'Baseline' : row.arm === 'candidate' ? 'Candidate' : row.arm }}</template></ElTableColumn>
              <!-- @vue-generic {ExperimentMember} -->
              <ElTableColumn label="准备 / 生命周期" min-width="185"><template #default="{ row }">{{ statusLabel(row.status) }}<p class="experiment-cell-note">{{ row.lifecycle ? statusLabel(row.lifecycle) : '尚未创建 Run' }}</p></template></ElTableColumn>
              <!-- @vue-generic {ExperimentMember} -->
              <ElTableColumn label="执行 / 验收" min-width="160"><template #default="{ row }">{{ row.execution_status ? statusLabel(row.execution_status) : '未启动' }}<p class="experiment-cell-note">{{ row.evaluation_outcome ? statusLabel(row.evaluation_outcome) : '未评测' }}</p></template></ElTableColumn>
              <!-- @vue-generic {ExperimentMember} -->
              <ElTableColumn label="证据 / 错误" min-width="210"><template #default="{ row }"><RouterLink v-if="row.run_id" :to="`/live/runs/${row.run_id}`" class="ui-text-link">详情 · 审批 · 单次取消 →</RouterLink><span v-else class="experiment-muted">Run 未创建</span><p v-if="row.error_code" class="experiment-cell-note mono">{{ row.error_code }}</p></template></ElTableColumn>
            </ElTable>
          </div>
        </ElTabPane>
        <ElTabPane label="比较结果" name="comparison"><div class="experiment-tab-body"><p v-if="comparisonError" role="alert" class="experiment-alert">比较读取失败：{{ comparisonError }}</p><ExperimentComparisonPanel v-if="currentComparison" :comparison="currentComparison" /><ElEmpty v-else description="当前没有可展示的比较结果" :image-size="58"><ElButton :disabled="busy || detailLoading" @click="open(detail.id)">重新读取批次</ElButton></ElEmpty></div></ElTabPane>
        <ElTabPane label="门槛与人工决定" name="decision"><div class="experiment-tab-body"><p v-if="comparisonError" role="alert" class="experiment-alert">比较读取失败，不能核对或提交人工决定：{{ comparisonError }}</p><ExperimentReviewPanel v-if="currentComparison" v-model:form="reviewForm" v-model:confirmed="reviewConfirmed" :comparison="currentComparison" :target="reviewTarget" :reviews="reviews" :review-error="reviewError" :busy="busy" :loading="detailLoading" :can-save="canSaveReview" :saving="busyAction === 'review'" @begin="beginReview" @save="saveReview" /><ElEmpty v-else description="读取当前比较后，才能核对门槛与记录决定" :image-size="58" /></div></ElTabPane>
        <ElTabPane label="报告导出" name="export"><div class="experiment-tab-body"><div class="experiment-section-heading"><div><h3>保存本次比较报告</h3><p>从同一数据库快照读取清单、比较、资源和人工历史，不读取当前源码工作区。</p></div></div><div class="experiment-export-grid"><section><AppIcon name="report" :size="26" /><h4>结构化 JSON</h4><p>适合保存、机器读取和后续核验。</p><ElButton :disabled="busy || detailLoading || !currentComparison" :loading="busyAction === 'export-json'" @click="download('json')">下载 JSON</ElButton></section><section><AppIcon name="report" :size="26" /><h4>可读 Markdown</h4><p>适合复查、讨论与整理展示材料。</p><ElButton :disabled="busy || detailLoading || !currentComparison" :loading="busyAction === 'export-markdown'" @click="download('markdown')">下载 Markdown</ElButton></section></div><p v-if="!currentComparison" class="experiment-alert">比较尚未读取成功，当前不能导出。</p><p class="experiment-note">每次下载是独立时点，请保存文件。此报告不包含完整原始 Trace、Diff 或源码包。</p><RouterLink to="/live/reports" class="ui-text-link">查看已下载报告的独立核验入口 →</RouterLink></div></ElTabPane>
      </ElTabs>
    </section>
    <div v-else-if="!selectedId && experiments.length" class="experiment-selection-hint"><AppIcon name="experiment" :size="24" /><p>从上方选择一个批次，查看运行、配对比较和人工决定。</p></div>
    <p class="experiment-page-footnote">实时实验与历史归档独立。页面切换和自动刷新只读取记录，不启动实验、不自动提交人工决定。</p>

    <ElDrawer v-model="creationOpen" title="新建实验" size="min(760px, 100vw)" class="experiment-create-drawer" :close-on-click-modal="!busy" :close-on-press-escape="!busy" :show-close="!busy">
      <p class="experiment-note">先选择已校验的固定版本，再核对冻结预览。预览不执行；确认启动只入队，需要独立 platform_worker；Native 还需 worker 显式启用 --allow-model。</p>
      <p v-if="operationError" role="alert" class="experiment-alert">{{ operationError }}</p>
      <p v-if="!catalogConnected" class="experiment-alert">版本列表连接未确认，不能生成预览或启动。请关闭抽屉并刷新列表。</p>
      <p v-else-if="!agents.length || !suites.length" class="experiment-info">尚无足够的 ready 固定版本。先登记 <RouterLink to="/live/agents">Agent</RouterLink> 和导入 <RouterLink to="/live/benchmarks">Benchmark</RouterLink>，完成校验后刷新列表。</p>
      <ElTabs v-model="createStep" class="experiment-create-tabs">
        <ElTabPane label="01 配置条件" name="config">
          <ElForm label-position="top" class="experiment-form-grid" @submit.prevent="inspect">
            <ElFormItem label="实验名称" label-for="experiment-name" class="full-width"><ElInput id="experiment-name" v-model="draft.name" maxlength="100" :disabled="busy" /></ElFormItem>
            <ElFormItem label="Benchmark Suite" label-for="experiment-suite" class="full-width"><ElSelect id="experiment-suite" v-model="draft.suite_id" :disabled="busy" placeholder="选择已校验的 Suite" aria-label="Benchmark Suite"><ElOption v-for="suite in suites" :key="suite.id" :value="suite.id" :label="`${suite.name} / ${suite.version}`" /></ElSelect></ElFormItem>
            <ElFormItem label="Baseline" label-for="experiment-baseline"><ElSelect id="experiment-baseline" v-model="draft.baseline_agent_id" :disabled="busy" placeholder="选择固定版本" aria-label="Baseline"><ElOption v-for="agent in agents" :key="agent.id" :value="agent.id" :label="`${agent.name} / ${agent.version}`" /></ElSelect></ElFormItem>
            <ElFormItem label="Candidate" label-for="experiment-candidate"><ElSelect id="experiment-candidate" v-model="draft.candidate_agent_id" :disabled="busy" placeholder="选择固定版本" aria-label="Candidate"><ElOption v-for="agent in agents" :key="agent.id" :value="agent.id" :label="`${agent.name} / ${agent.version}`" /></ElSelect></ElFormItem>
            <ElFormItem label="实验模式" label-for="experiment-mode"><ElSelect id="experiment-mode" v-model="draft.mode" :disabled="busy" aria-label="实验模式"><ElOption value="benchmark" label="Benchmark · 可有多变量" /><ElOption value="controlled" label="Controlled · 严格声明差异" /></ElSelect></ElFormItem>
            <ElFormItem label="计划顺序" label-for="experiment-order"><ElSelect id="experiment-order" v-model="draft.order" :disabled="busy" aria-label="计划顺序"><ElOption value="baseline_first" label="每个 Case 先 Baseline" /><ElOption value="candidate_first" label="每个 Case 先 Candidate" /></ElSelect></ElFormItem>
            <ElFormItem label="声明变化字段（逗号分隔）" label-for="experiment-fields" class="full-width"><ElInput id="experiment-fields" v-model="fields" :disabled="busy" placeholder="如 native.retrieval_policy" /><p class="experiment-field-help">可先用 Benchmark 预览核对实际差异；重复字段或超过 20 项时不能预览。</p></ElFormItem>
            <ElFormItem label="重复次数（1–5）" label-for="experiment-repetitions"><ElInputNumber id="experiment-repetitions" v-model="draft.repetitions" :disabled="busy" :min="1" :max="5" :step="1" step-strictly controls-position="right" /></ElFormItem>
            <ElFormItem label="Agent 秒数预算（1–3600）" label-for="experiment-budget"><ElInputNumber id="experiment-budget" v-model="draft.timeout_seconds" :disabled="busy" :min="1" :max="3600" :step="1" step-strictly controls-position="right" /></ElFormItem>
            <div class="full-width"><ElCheckbox v-model="policyEnabled" :disabled="busy">在启动前冻结本批质量门槛</ElCheckbox></div>
            <template v-if="policyEnabled"><ElFormItem label="最少可比对子（1–20）" label-for="policy-pairs"><ElInputNumber id="policy-pairs" v-model="policy.min_pairs" :disabled="busy" :min="1" :max="20" :step="1" step-strictly controls-position="right" /></ElFormItem><ElFormItem label="最少不同 Case（1–20）" label-for="policy-cases"><ElInputNumber id="policy-cases" v-model="policy.min_cases" :disabled="busy" :min="1" :max="20" :step="1" step-strictly controls-position="right" /></ElFormItem><ElFormItem label="最多退化数（0–20）" label-for="policy-regressions"><ElInputNumber id="policy-regressions" v-model="policy.max_regressions" :disabled="busy" :min="0" :max="20" :step="1" step-strictly controls-position="right" /></ElFormItem><ElFormItem label="最低通过率差（百分点）" label-for="policy-delta"><ElInputNumber id="policy-delta" v-model="policy.min_pass_delta_pp" :disabled="busy" :min="-100" :max="100" :step="0.1" controls-position="right" /></ElFormItem><p class="experiment-note full-width">全部计划对子可比后才能判定达到门槛。默认数值仅为填写起点，不是发布标准；当前只判断自动测试质量，不含成本、Token 或延迟门槛。</p></template>
            <p class="experiment-note full-width">干预规则：Native 计划及每个候选人工审批；Process 无人工修改。审批等待可能改变实际开始顺序。每批最多 40 个 Run。</p>
          </ElForm>
        </ElTabPane>
        <ElTabPane label="02 冻结预览" name="preview">
          <template v-if="preview"><div class="experiment-preview-summary"><div><span>预计运行</span><strong>{{ preview.manifest.run_count }} <small>Run</small></strong></div><div><span>模型请求</span><strong>{{ preview.manifest.needs_model ? '需要授权' : '无平台调用' }}</strong></div></div><p v-if="!currentPreview" role="alert" class="experiment-alert">配置已变化，下面是旧预览。请返回配置条件重新生成预览，当前不能启动。</p><p class="experiment-note">实际配置差异：<code>{{ preview.manifest.changed_fields.join('、') || '已记录：无' }}</code></p><details class="experiment-details"><summary>完整冻结清单与预览指纹</summary><code>{{ preview.preview_sha256 }}</code><pre>{{ JSON.stringify(preview.manifest, null, 2) }}</pre></details><div class="experiment-confirmations"><ElCheckbox v-model="allowModel" :disabled="busy || !currentPreview">明确允许此批实验的模型请求（含 Native 检索请求）可能产生费用；worker 仍需单独授权</ElCheckbox><ElCheckbox v-model="confirmed" :disabled="busy || !currentPreview">已核对本次预览，确认入队执行</ElCheckbox></div></template>
          <ElEmpty v-else description="填写配置后，先生成冻结预览" :image-size="64" />
        </ElTabPane>
      </ElTabs>
      <template #footer><div class="experiment-drawer-footer"><span>{{ createStep === 'preview' ? '只启动冻结预览中的配置' : '预览只核对，不执行实验' }}</span><ElButton :disabled="busy" @click="creationOpen = false">关闭</ElButton><ElButton v-if="createStep === 'config'" type="primary" :disabled="!canPreview" :loading="busyAction === 'preview'" @click="inspect">生成冻结预览</ElButton><ElButton v-else type="primary" :disabled="!canStart" :loading="busyAction === 'start'" @click="start">确认启动预览中的实验</ElButton></div></template>
    </ElDrawer>
  </div>
</template>
