<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElButton, ElDrawer, ElInput, ElSelect, ElOption, ElTable, ElTableColumn, ElEmpty, ElSkeleton, ElTabs, ElTabPane } from 'element-plus'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/drawer/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/skeleton/style/css'
import 'element-plus/es/components/tabs/style/css'
import 'element-plus/es/components/tab-pane/style/css'
import { catalogRequest as request, catalogLabels as labels, canValidateCatalog, parseCatalogConfiguration, makeAgentConfiguration, type CatalogEntry as Entry, type CatalogRepository, type CatalogKind } from '../data/catalog'
import '../resources.css'
const message = (error: unknown) => error instanceof Error ? error.message : String(error)
const route = useRoute()
const kind = computed<CatalogKind>(() => route.path.endsWith('/agents') ? 'agents' : 'benchmarks')
const title = computed(() => kind.value === 'agents' ? 'Agent 版本' : 'Benchmark 版本')
const entries = ref<Entry[]>([]), selected = ref<Entry | null>(null)
const error = ref(''), notice = ref(''), busy = ref(false), connected = ref(false), json = ref(''), search = ref('')
const creationOpen = ref(false), detailTab = ref('descriptor')
const agentName = ref('Protocol Demo'), version = ref('v1'), adapter = ref('process'), image = ref('')
const argv = ref('["python", "-I", "/agent/demo.py", "--mode", "noop"]')
const repositories = ref<CatalogRepository[]>([]), repositoryError = ref('')
const keys = new Map<string, string>()
const filtered = computed(() => entries.value.filter(entry => `${entry.name} ${entry.version} ${entry.id}`.toLowerCase().includes(search.value.trim().toLowerCase())))
const detailOpen = computed({get:()=>!!selected.value,set:(value:boolean)=>{if(!value)selected.value=null}})
let generation = 0
async function refresh() {
  const current = ++generation, currentKind = kind.value
  busy.value = true; error.value = ''; connected.value = false; repositoryError.value = ''
  try {
    const rows = await request<Entry[]>(currentKind)
    if (!Array.isArray(rows)) throw new Error('版本列表响应格式不符合约定。')
    if (current !== generation) return
    entries.value = rows; connected.value = true
    if (selected.value) selected.value = rows.find(row=>row.id===selected.value?.id) ?? null
    if (currentKind === 'benchmarks') {
      try {
        const repos = await request<CatalogRepository[]>('catalog-repositories')
        if (!Array.isArray(repos)) throw new Error('仓库清单响应格式不符合约定。')
        if (current === generation) repositories.value = repos
      } catch (e) { if (current === generation) repositoryError.value = message(e) }
    }
  } catch (e) { if (current === generation) { error.value = message(e); connected.value = false } }
  finally { if (current === generation) busy.value = false }
}
function makeAgent() {
  try { json.value = makeAgentConfiguration(agentName.value,version.value,adapter.value,image.value,argv.value); error.value = '' }
  catch (e) { error.value = message(e) }
}
async function importFile(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0], current = generation
  if (!file) return
  input.value = ''
  if (file.size > 1_000_000) { error.value = '配置文件不能超过 1 MB。'; return }
  try { const text = await file.text(); if (current === generation) { json.value = text; error.value = '' } }
  catch { if (current === generation) error.value = '无法读取配置文件。' }
}
async function register() {
  if (busy.value || !connected.value || !json.value.trim()) return
  let body: unknown
  try { body = parseCatalogConfiguration(json.value) } catch (e) { error.value = message(e); return }
  const current = generation, currentKind = kind.value
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const result = await request<Entry>(currentKind,body)
    if (current !== generation) return
    creationOpen.value = false; selected.value = result; detailTab.value = 'descriptor'
    notice.value = '已持久保存版本。登记不会自动执行 Agent；请检查配置后显式校验。'
    await refresh()
  } catch (e) { if (current === generation) { error.value = message(e); connected.value = false } }
  finally { if (current === generation) busy.value = false }
}
async function validate(entry: Entry) {
  if (!canValidateCatalog(entry,busy.value,connected.value)) return
  const current = generation, currentKind = kind.value
  busy.value = true; error.value = ''; notice.value = ''
  const key = keys.get(entry.id) ?? crypto.randomUUID(); keys.set(entry.id,key)
  try {
    const job = await request<{id:string;status:string}>(`${currentKind}/${entry.id}/validate`,{request_key:key})
    keys.delete(entry.id)
    if (current !== generation) return
    notice.value = `校验任务 ${job.id} 已受理（${job.status}）。启动 platform_worker 后点击刷新查看结果。`
    await refresh()
  } catch (e) { if (current === generation) { error.value = message(e); connected.value = false } }
  finally { if (current === generation) busy.value = false }
}
function openEntry(entry: Entry) { selected.value = entry; detailTab.value = 'descriptor' }
watch(kind,()=>{ entries.value=[];selected.value=null;json.value='';notice.value='';search.value='';creationOpen.value=false;repositories.value=[];void refresh() },{immediate:true})
onUnmounted(()=>{generation++})
</script>
<template>
  <div class="resource-page">
    <div class="ui-page-heading"><div><p class="ui-kicker">固定版本 · 当前数据库</p><h1>{{ title }}</h1><p class="ui-page-description">登记不可变配置，显式校验后再用于实验。</p></div><div class="resource-actions"><ElButton :disabled="busy" @click="refresh">刷新状态</ElButton><ElButton type="primary" :disabled="busy" @click="creationOpen=true">{{ kind==='agents' ? '登记新版本' : '导入新版本' }}</ElButton></div></div>
    <p v-if="error && !creationOpen" role="alert" class="resource-alert">{{ error }}{{ entries.length && !connected ? ' · 列表保留上次读取；当前不可提交。' : '' }}</p>
    <p v-if="notice" role="status" class="resource-notice">{{ notice }}</p>
    <section class="ui-card resource-list"><div class="resource-toolbar"><div><h2>已登记版本</h2><p>{{ busy ? '正在处理' : connected ? '已读取当前数据库' : '连接未确认' }} · 最近 100 个版本</p></div><ElInput v-model="search" clearable aria-label="搜索版本名称或 ID" placeholder="搜索名称、版本或 ID" /></div>
      <ElSkeleton v-if="busy && !entries.length" :rows="4" />
      <ElTable v-else-if="filtered.length" :data="filtered" row-key="id">
        <!-- @vue-generic {Entry} -->
        <ElTableColumn label="名称 / 版本" min-width="220"><template #default="{row}"><ElButton link type="primary" @click="openEntry(row)">{{ row.name }} / {{ row.version }}</ElButton><p class="resource-id">{{ row.id }}</p></template></ElTableColumn>
        <!-- @vue-generic {Entry} -->
        <ElTableColumn label="校验状态" min-width="190"><template #default="{row}">{{ labels[row.status] ?? row.status }}</template></ElTableColumn>
        <!-- @vue-generic {Entry} -->
        <ElTableColumn label="操作" min-width="220"><template #default="{row}"><ElButton @click="openEntry(row)">查看详情</ElButton><ElButton :disabled="!canValidateCatalog(row,busy,connected)" @click="validate(row)">显式校验</ElButton></template></ElTableColumn>
      </ElTable>
      <ElEmpty v-else :description="search ? '没有符合条件的版本' : error ? '连接后可读取版本' : '尚无版本记录'" :image-size="64" />
      <p class="resource-note">同名同版本不可覆盖；配置改变请创建新版本。中断校验需操作者确认容器停止并恢复所有权，不能直接重跑。</p>
    </section>
    <section class="ui-card resource-guide"><h2>登记与校验的边界</h2><p v-if="kind==='agents'">Process 校验运行无网络、十秒预算的协议样例，不调用平台模型；Native 仅检查本地实现版本。校验通过不代表任务成功，声明的观测能力仍需实际运行证据。</p><p v-else>导入有序 Case、注册仓库 ID、commit、编辑范围、保护测试、验收规则和本地测试镜像。环境校验不运行基线测试，正式运行仍重新检查并执行基线。</p><p>此页面不启动正式实验，版本登记不会自动触发校验。</p>
      <details v-if="kind==='benchmarks'"><summary>已注册仓库（最近 100 条）</summary><p v-if="repositoryError" role="alert">{{ repositoryError }}</p><p v-else-if="!repositories.length">{{ connected ? '未读取到仓库记录。' : '连接未确认。' }}</p><p v-for="repo in repositories" :key="repo.id" class="resource-id">{{ repo.name }} · {{ repo.id }} · {{ repo.commit_hash }}</p><p>完整清单可用 API 分页查询。</p></details>
    </section>
    <ElDrawer v-model="creationOpen" :title="kind==='agents' ? '登记 Agent 版本' : '导入 Benchmark 版本'" size="min(740px, 100vw)" :close-on-click-modal="!busy" :close-on-press-escape="!busy" :show-close="!busy" class="resource-drawer">
      <p>保存不可变版本；不会执行正式实验。完整配置不要填写 API Key 或其他秘密。</p><p v-if="!connected" role="status">后端连接未确认，请先关闭抽屉并刷新列表，当前不可保存。</p><p v-if="error" role="alert">{{ error }}</p>
      <details v-if="kind==='agents'" open><summary>辅助生成 Agent 配置</summary><div class="resource-form"><label>名称<ElInput v-model="agentName" :maxlength="100" /></label><label>版本<ElInput v-model="version" :maxlength="100" /></label><label>适配器<ElSelect v-model="adapter"><ElOption label="Process · 外部程序" value="process" /><ElOption label="Native · 内置 Agent" value="native" /></ElSelect></label><template v-if="adapter==='process'"><label>已有本地镜像完整 ID<ElInput v-model="image" placeholder="sha256:…（64 位）" /></label><label class="resource-full">参数数组<ElInput v-model="argv" /></label></template><div><ElButton :disabled="busy" @click="makeAgent">生成下方配置</ElButton></div></div></details>
      <label class="resource-upload">导入 JSON 文件（最多 1 MB）<input type="file" accept=".json,application/json" :disabled="busy" @change="importFile" /></label>
      <label class="resource-config">完整配置<ElInput v-model="json" type="textarea" :rows="14" spellcheck="false" :disabled="busy" placeholder="粘贴或导入版本配置 JSON" /></label>
      <template #footer><ElButton :disabled="busy" @click="creationOpen=false">关闭</ElButton><ElButton type="primary" :disabled="busy || !connected || !json.trim()" :loading="busy" @click="register">保存不可变版本</ElButton></template>
    </ElDrawer>
    <ElDrawer v-model="detailOpen" title="版本详情 · 数据库记录" size="min(740px, 100vw)" class="resource-drawer"><template v-if="selected"><h2>{{ selected.name }} / {{ selected.version }}</h2><p>{{ labels[selected.status] ?? selected.status }}</p><details><summary>完整 ID 与内容指纹</summary><p class="resource-id">ID：{{ selected.id }}</p><p class="resource-id">SHA256：{{ selected.content_sha256 }}</p></details><ElTabs v-model="detailTab"><ElTabPane label="已保存配置" name="descriptor"><pre class="resource-json">{{ JSON.stringify(selected.descriptor,null,2) }}</pre></ElTabPane><ElTabPane label="最近校验" name="validation"><p>声明与实际校验分别记录，校验通过不代表任务成功。</p><pre class="resource-json">{{ selected.validation ? JSON.stringify(selected.validation,null,2) : '未校验' }}</pre></ElTabPane></ElTabs><ElButton :disabled="!canValidateCatalog(selected,busy,connected)" @click="validate(selected)">显式校验此版本</ElButton></template></ElDrawer>
  </div>
</template>
