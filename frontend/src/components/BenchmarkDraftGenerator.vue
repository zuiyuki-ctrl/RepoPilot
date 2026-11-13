<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { ElButton, ElDrawer, ElInput } from 'element-plus'
import { catalogRequest as request, type CatalogRepository } from '../data/catalog'
import { activeDraft, canConfirmDraft, buildDraftSelection, draftLabels, parseTestItems, testKey,
  type CaseDraft, type DraftText, type DraftPreview, type DraftSelection } from '../data/caseDrafts'

const emit = defineEmits<{ confirmed: [id: string] }>()
const open = ref(false), busy = ref(false), error = ref(''), notice = ref('')
const repositories = ref<CatalogRepository[]>([]), history = ref<Pick<CaseDraft,'id'|'status'|'text'>[]>([])
const repositoryId = ref(''), commit = ref(''), files = ref<{path:string;bytes:number}[]>([])
const sourceFiles = ref<string[]>([]), testFiles = ref<string[]>([]), image = ref(''), background = ref('')
const tests = ref(''), failed = ref<string[]>([]), consentModel = ref(false), consentTests = ref(false)
const preview = ref<DraftPreview | null>(null), selection = ref<DraftSelection | null>(null)
const draft = ref<CaseDraft | null>(null), text = ref<DraftText>({title:'',user_request:'',editable_files:[]})
const suiteName = ref(''), suiteVersion = ref('v1'), caseId = ref(''), caseVersion = ref('v1')
const parsedTests = computed(() => { try { return parseTestItems(tests.value) } catch { return [] } })
const dirty = computed(() => !!draft.value?.text && JSON.stringify(text.value) !== JSON.stringify(draft.value.text))
const confirmable = computed(() => canConfirmDraft(draft.value,dirty.value,busy.value))
const message = (e: unknown) => e instanceof Error ? e.message : String(e)
let epoch = 0, timer: ReturnType<typeof setTimeout> | undefined, requestKey = ''

function stopPoll() { if (timer) clearTimeout(timer); timer = undefined }
function accept(row: CaseDraft) {
  draft.value = row
  if (row.text) text.value = { ...row.text, editable_files: [...row.text.editable_files] }
  if (!caseId.value) caseId.value = `generated-${row.id.slice(0,8)}`
  if (!suiteName.value && row.text) suiteName.value = row.text.title
  schedulePoll()
}
function schedulePoll() {
  stopPoll()
  if (!open.value || !activeDraft(draft.value)) return
  const current = epoch, id = draft.value!.id
  timer = setTimeout(async () => {
    try {
      const row = await request<CaseDraft>(`case-drafts/${id}`)
      if (current !== epoch || draft.value?.id !== id) return
      accept(row)
    } catch (e) { if (current === epoch) error.value = message(e) + '；自动刷新已暂停，可手动刷新。' }
  }, 2000)
}
async function action(work: (current: number) => Promise<void>) {
  if (busy.value) return
  const current = epoch; busy.value = true; error.value = ''; notice.value = ''
  try { await work(current) } catch (e) { if (current === epoch) error.value = message(e) }
  finally { if (current === epoch) busy.value = false }
}
async function load() {
  await action(async current => {
    const [repos, rows] = await Promise.all([request<CatalogRepository[]>('catalog-repositories'),request<Pick<CaseDraft,'id'|'status'|'text'>[]>('case-drafts')])
    if (current !== epoch) return
    repositories.value = repos; history.value = rows
  })
}
async function browse() {
  commit.value = ''; files.value = []; sourceFiles.value = []; testFiles.value = []; failed.value = []
  if (!repositoryId.value) return
  await action(async current => {
    const data = await request<{repository_commit:string;files:{path:string;bytes:number}[]}>(`case-drafts/repositories/${repositoryId.value}`)
    if (current !== epoch) return
    commit.value = data.repository_commit; files.value = data.files
  })
}
async function showPreview() {
  await action(async current => {
    const chosen = buildDraftSelection({repositoryId:repositoryId.value,commit:commit.value,sourceFiles:sourceFiles.value,
      testFiles:testFiles.value,image:image.value,background:background.value,tests:tests.value,failed:failed.value})
    const data = await request<DraftPreview>('case-drafts/preview',chosen)
    if (current !== epoch) return
    selection.value = chosen; preview.value = data; consentModel.value = false; consentTests.value = false
    requestKey = crypto.randomUUID()
  })
}
async function generate() {
  if (!preview.value || !selection.value || !consentModel.value || !consentTests.value) return
  await action(async current => {
    const row = await request<CaseDraft>('case-drafts', {selection:selection.value,preview_sha256:preview.value!.preview_sha256,
      request_key:requestKey,allow_model:true,allow_baseline_tests:true})
    if (current === epoch) { accept(row); notice.value = '已排队；不会启动 Agent。未开启 --allow-model 的 worker 不会调用模型。' }
  })
}
async function selectDraft(id: string) {
  if (busy.value) return
  stopPoll(); epoch++; suiteName.value = ''; caseId.value = ''
  await action(async current => { const row = await request<CaseDraft>(`case-drafts/${id}`); if (current === epoch) accept(row) })
}
async function saveText() {
  if (!draft.value) return
  await action(async current => {
    const row = await request<CaseDraft>(`case-drafts/${draft.value!.id}/edit`,{revision:draft.value!.revision,text:text.value})
    if (current === epoch) { accept(row); notice.value = '修改已保存为草稿，尚未注册正式 Case。' }
  })
}
async function confirm() {
  if (!confirmable.value) return
  await action(async current => {
    const row = await request<CaseDraft>(`case-drafts/${draft.value!.id}/confirm`,{revision:draft.value!.revision,
      suite_name:suiteName.value,suite_version:suiteVersion.value,case_id:caseId.value,case_version:caseVersion.value})
    if (current !== epoch) return
    accept(row); notice.value = '已注册到现有 Benchmark 并排队环境校验；校验通过后才可用于实验。未启动 Agent。'
    if (row.confirmed_benchmark_id) emit('confirmed',row.confirmed_benchmark_id)
  })
}
async function discard() {
  if (!draft.value) return
  await action(async current => {
    const row = await request<CaseDraft>(`case-drafts/${draft.value!.id}/discard`,{revision:draft.value!.revision})
    if (current === epoch) accept(row)
  })
}
function newDraft() { stopPoll(); epoch++; draft.value = null; preview.value = null; selection.value = null; error.value = ''; notice.value = ''; suiteName.value = ''; caseId.value = '' }
watch([repositoryId,commit,sourceFiles,testFiles,image,background,tests,failed],()=>{
  preview.value = null; selection.value = null; consentModel.value = false; consentTests.value = false; requestKey = ''
},{deep:true,flush:'sync'})
watch(open, value => { epoch++; stopPoll(); if (value) { void load(); schedulePoll() } else busy.value = false })
onUnmounted(()=>{epoch++;stopPoll()})
</script>

<template>
  <ElButton @click="open=true">生成评测题</ElButton>
  <ElDrawer v-model="open" title="生成评测题 · 人工确认后注册" size="min(880px, 100vw)" class="resource-drawer" :close-on-click-modal="!busy" :show-close="!busy" :close-on-press-escape="!busy">
    <p>仅支持 python-basic / bug_fix。平台先复现原始失败，再生成题面；生成、编辑和保存都不会启动 Agent Run。</p>
    <p v-if="error" role="alert" class="resource-alert">{{ error }}</p><p v-if="notice" role="status" class="resource-notice">{{ notice }}</p>
    <div class="resource-actions"><ElButton :disabled="busy" @click="newDraft">新建草稿</ElButton><ElButton :disabled="busy" @click="load">刷新草稿列表</ElButton></div>
    <details class="draft-history"><summary>最近 30 份草稿（关闭页面后仍保留）</summary><ul><li v-for="row in history" :key="row.id"><ElButton link :disabled="busy" @click="selectDraft(row.id)">{{ row.text?.title ?? row.id.slice(0,8) }} · {{ draftLabels[row.status] ?? row.status }}</ElButton></li></ul></details>
    <template v-if="!draft">
      <fieldset :disabled="busy" class="draft-fieldset">
        <label>已登记仓库 / 固定提交<select v-model="repositoryId" @change="browse"><option value="">请选择仓库</option><option v-for="repo in repositories" :key="repo.id" :value="repo.id">{{ repo.name }} · {{ repo.commit_hash?.slice(0,12) }} · {{ repo.id.slice(0,8) }}</option></select></label>
        <p class="resource-id">起始提交：{{ commit || '未选择' }}</p><p>使用登记副本的提交，不会 checkout 或修改仓库。需要其他提交时请先登记该提交的独立仓库副本。</p>
        <div class="draft-files"><section><h3>发送给模型的源码（最多 30 个）</h3><label v-for="file in files" :key="file.path"><input v-model="sourceFiles" type="checkbox" :value="file.path" :disabled="testFiles.includes(file.path)" />{{ file.path }} ({{ file.bytes }} B)</label></section><section><h3>受保护验收测试（最多 20 个）</h3><label v-for="file in files" :key="file.path"><input v-model="testFiles" type="checkbox" :value="file.path" :disabled="sourceFiles.includes(file.path)" />{{ file.path }}</label></section></div>
        <label>验收测试项（每行 classname::name，名称须与 JUnit 一致）<ElInput v-model="tests" type="textarea" :rows="5" placeholder="tests.test_task_list::test_filter[open]" /></label>
        <p>参数化测试需要完整名称；不执行源码来猜测测试项。可从已有 pytest JUnit 报告复制 classname 与 name。</p>
        <section><h3>预期失败项（至少选择一个）</h3><label v-for="item in parsedTests" :key="testKey(item)" class="draft-check"><input v-model="failed" type="checkbox" :value="testKey(item)" />{{ testKey(item) }}</label></section>
        <label>本地 python-basic 测试镜像完整 ID<ElInput v-model="image" placeholder="sha256:…（64 位）" /></label>
        <p>沿用现有 Suite 镜像配置，可运行 <code>docker image inspect repopilot-pytest:py311</code> 查询 Id；平台不会拉取或执行模型提供的镜像。</p>
        <label>业务背景（可选，也会发送给模型）<ElInput v-model="background" type="textarea" :rows="3" :maxlength="1000" /></label>
      </fieldset>
      <ElButton :disabled="busy" @click="showPreview">预览将发送的文件</ElButton>
      <section v-if="preview" class="draft-preview">
        <h3>发送前确认</h3><p>模型：{{ preview.model.model }} · 目标：{{ preview.model.destination }}</p>
        <p>仅发送以下文件全文、业务背景和所声明的验收项。不会发送其他仓库文件或基线日志。请确认不含敏感信息。</p>
        <details v-for="file in preview.files" :key="file.path"><summary>{{ file.path }} · {{ file.bytes }} B</summary><p class="resource-id">SHA256：{{ file.sha256 }}</p><pre class="resource-json">{{ preview.contents[file.path] }}</pre></details>
        <label class="draft-check"><input v-model="consentModel" type="checkbox" :disabled="busy" />我授权将上述内容发送给此模型（可能产生费用）</label>
        <label class="draft-check"><input v-model="consentTests" type="checkbox" :disabled="busy" />我授权在固定镜像的隔离容器中运行所选测试（最多 120 秒）</label>
        <ElButton type="primary" :disabled="busy || !consentModel || !consentTests" @click="generate">授权并生成草稿</ElButton>
      </section>
    </template>
    <template v-else>
      <h2>{{ draftLabels[draft.status] ?? draft.status }}</h2><p class="resource-id">草稿：{{ draft.id }} · 版本 {{ draft.revision }}</p>
      <ElButton :disabled="busy" @click="selectDraft(draft.id)">刷新此草稿（丢弃未保存编辑）</ElButton>
      <p v-if="draft.error" role="alert" class="resource-alert">{{ draft.error.message }}（{{ draft.error.reason }}）</p>
      <p class="resource-id">起始提交：{{ draft.selection.repository_commit }}</p>
      <p>受保护测试：{{ draft.selection.protected_test_files.join('、') }}</p>
      <p>预期失败项：{{ draft.selection.acceptance.baseline_failure_tests.map(testKey).join('、') }}</p>
      <details v-if="draft.baseline"><summary>基线证据与校验原因：{{ draft.baseline.reason }}</summary><pre class="resource-json">{{ JSON.stringify(draft.baseline,null,2) }}</pre></details>
      <fieldset v-if="draft.text" :disabled="busy || draft.status !== 'ready'" class="draft-fieldset">
        <label>题目名称<ElInput v-model="text.title" :maxlength="100" /></label>
        <label>题面（现象、预期行为与约束，不提供修复答案）<ElInput v-model="text.user_request" type="textarea" :rows="10" :maxlength="850" /></label>
        <section><h3>允许修改范围（只能在已授权源码中调整）</h3><label v-for="path in draft.selection.source_files" :key="path" class="draft-check"><input v-model="text.editable_files" type="checkbox" :value="path" />{{ path }}</label></section>
        <ElButton :disabled="!dirty || busy" @click="saveText">保存草稿编辑</ElButton>
        <p v-if="dirty">尚有未保存编辑；保存后才能确认注册。</p>
      </fieldset>
      <fieldset v-if="draft.status === 'ready'" :disabled="busy" class="draft-fieldset">
        <h3>确认后保存为单 Case 的 Benchmark / Suite 版本</h3>
        <div class="resource-form"><label>Suite 名称<ElInput v-model="suiteName" :maxlength="100" /></label><label>Suite 版本<ElInput v-model="suiteVersion" :maxlength="100" /></label><label>Case ID<ElInput v-model="caseId" :maxlength="100" /></label><label>Case 版本<ElInput v-model="caseVersion" :maxlength="100" /></label></div>
        <ElButton type="primary" :disabled="!confirmable || !suiteName.trim() || !suiteVersion.trim() || !caseId.trim() || !caseVersion.trim()" @click="confirm">确认保存并校验 Benchmark</ElButton>
      </fieldset>
      <p v-if="draft.confirmed_benchmark_id" class="resource-id">已登记 Benchmark：{{ draft.confirmed_benchmark_id }}。关闭抽屉后刷新版本列表查看校验结果；此处“已确认”不等于校验通过。</p>
      <ElButton v-if="!['confirmed','discarded'].includes(draft.status)" :disabled="busy || ['validating','generating','interrupted'].includes(draft.status)" @click="discard">丢弃草稿（不注册 Case）</ElButton>
    </template>
  </ElDrawer>
</template>

<style scoped>
.draft-fieldset { border: 0; padding: 0; margin: 20px 0; display: grid; gap: 16px; min-width: 0; }
.draft-fieldset > label { display: grid; gap: 8px; }
select { padding: 10px; max-width: 100%; background: var(--el-fill-color-blank); color: var(--el-text-color-primary); border: 1px solid var(--el-border-color); border-radius: 6px; }
.draft-files { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 16px; }
.draft-files section { max-height: 280px; overflow: auto; }
.draft-files label, .draft-check { display: flex; align-items: flex-start; gap: 8px; overflow-wrap: anywhere; margin: 10px 0; }
.draft-history, .draft-preview { margin: 20px 0; }
.draft-preview details { margin: 12px 0; }
.resource-json { max-height: 350px; overflow: auto; white-space: pre-wrap; }
@media (max-width: 600px) { .draft-files { grid-template-columns: 1fr; } }
</style>
