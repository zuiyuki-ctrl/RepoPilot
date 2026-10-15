<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

type Entry = { id: string; name: string; version: string; status: string; content_sha256: string;
  descriptor: Record<string, unknown>; validation: Record<string, unknown> | null }
const route = useRoute()
const kind = computed(() => route.path.endsWith('/agents') ? 'agents' : 'benchmarks')
const entries = ref<Entry[]>([])
const error = ref('')
const notice = ref('')
const busy = ref(false)
const json = ref('')
const selected = ref<Entry | null>(null)
const agentName = ref('Protocol Demo')
const version = ref('v1')
const adapter = ref('process')
const image = ref('')
const argv = ref('["python", "-I", "/agent/demo.py", "--mode", "noop"]')
const repositories = ref<{ id: string; name: string; commit_hash: string }[]>([])
const keys = new Map<string, string>()
const labels: Record<string, string> = { registered: '已登记 · 未校验', validating: '校验排队或执行中', ready: '校验通过', invalid: '校验失败或中断' }

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch('/api/v2/' + path, { method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(15000) })
  const data = await response.json()
  if (!response.ok) throw new Error(`${response.status}: ${typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)}`)
  return data as T
}

async function refresh() {
  const current = kind.value
  busy.value = true; error.value = ''
  try {
    const rows = await request<Entry[]>(current)
    if (current !== kind.value) return
    entries.value = rows
    if (selected.value) selected.value = rows.find(row => row.id === selected.value?.id) ?? null
    if (current === 'benchmarks') repositories.value = await request('catalog-repositories')
  } catch (e) { error.value = String(e) }
  finally { busy.value = false }
}

function makeAgent() {
  try {
    json.value = JSON.stringify({ protocol_version: 1, name: agentName.value, version: version.value,
      adapter: adapter.value, declared_capabilities: ['execution'],
      ...(adapter.value === 'process' ? { process: { protocol_version: 1, image: image.value,
        argv: JSON.parse(argv.value), trace: false } } : { native: { retrieval_policy: 'vector', max_tool_calls: 4 } }) }, null, 2)
    error.value = ''
  } catch { error.value = '启动参数必须是 JSON 字符串数组。' }
}

async function importFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (file.size > 1000000) { error.value = '配置文件不能超过 1 MB。'; return }
  json.value = await file.text()
}

async function register() {
  busy.value = true; error.value = ''; notice.value = ''
  try {
    if (new TextEncoder().encode(json.value).length > 1000000) throw new Error('配置不能超过 1 MB。')
    const result = await request<Entry>(kind.value, JSON.parse(json.value))
    selected.value = result
    notice.value = '已持久保存版本。登记不会自动执行 Agent；请检查配置后显式校验。'
    await refresh()
  } catch (e) { error.value = String(e) }
  finally { busy.value = false }
}

async function validate(entry: Entry) {
  busy.value = true; error.value = ''; notice.value = ''
  const key = keys.get(entry.id) ?? crypto.randomUUID()
  keys.set(entry.id, key)
  try {
    const job = await request<{ id: string; status: string }>(`${kind.value}/${entry.id}/validate`, { request_key: key })
    keys.delete(entry.id)
    notice.value = `校验任务 ${job.id} 已受理（${job.status}）。启动 platform_worker 后点击刷新查看结果。`
    await refresh()
  } catch (e) { error.value = String(e) }
  finally { busy.value = false }
}

watch(kind, () => { entries.value = []; selected.value = null; json.value = ''; notice.value = ''; void refresh() })
onMounted(refresh)
</script>

<template>
  <section class="catalog">
    <h1>{{ kind === 'agents' ? 'Agent 版本登记' : 'Benchmark 版本导入' }}</h1>
    <p>实时数据库记录。同名同版本不可覆盖；配置改变请创建新版本。此页面不启动正式实验。</p>
    <p v-if="kind === 'agents'">Process 校验运行无网络、十秒预算的协议样例，不调用平台模型；Native 仅检查本地实现版本。校验通过不代表任务成功，声明的观测能力仍需实际运行证据。</p>
    <p v-else>导入有序 Case、注册仓库 ID、commit、编辑范围、保护测试、验收规则和本地测试镜像。环境校验不运行基线测试，正式运行仍重新检查并执行基线。</p>
    <p v-if="error" role="alert" class="catalog-error">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <details open>
      <summary>登记新版本</summary>
      <div v-if="kind === 'agents'" class="catalog-form">
        <label>名称 <input v-model="agentName" maxlength="100" /></label>
        <label>版本 <input v-model="version" maxlength="100" /></label>
        <label>适配器 <select v-model="adapter"><option value="process">Process · 外部程序</option><option value="native">Native · 内置 Agent</option></select></label>
        <template v-if="adapter === 'process'">
          <label>已有本地镜像完整 ID <input v-model="image" placeholder="sha256:…（64 位）" /></label>
          <label>参数数组 <input v-model="argv" /></label>
        </template>
        <button @click="makeAgent">生成下方配置</button>
      </div>
      <label>导入 JSON 文件 <input type="file" accept=".json,application/json" @change="importFile" /></label>
      <label class="catalog-json">完整配置（不要填 API Key 或其他秘密）<textarea v-model="json" rows="14" spellcheck="false" /></label>
      <button :disabled="busy || !json.trim()" @click="register">保存不可变版本</button>
    </details>
    <details v-if="kind === 'benchmarks'">
      <summary>已注册仓库（最近 100 条；完整清单可用 API 分页查询）</summary>
      <p v-for="repo in repositories" :key="repo.id">{{ repo.name }} · {{ repo.id }} · {{ repo.commit_hash }}</p>
    </details>
    <h2>已登记版本</h2>
    <button :disabled="busy" @click="refresh">{{ busy ? '处理中…' : '刷新真实状态' }}</button>
    <p v-if="!entries.length && !error">尚无版本记录。</p>
    <table v-else><thead><tr><th>名称 / 版本</th><th>状态</th><th>操作</th></tr></thead>
      <tbody><tr v-for="entry in entries" :key="entry.id">
        <td>{{ entry.name }} / {{ entry.version }}</td><td>{{ labels[entry.status] ?? entry.status }}</td>
        <td><button @click="selected = entry">详情</button>
          <button :disabled="busy || entry.status === 'validating' || entry.validation?.status === 'interrupted'" @click="validate(entry)">显式校验</button></td>
      </tr></tbody></table>
    <p>列表显示最近 100 个版本。中断校验需操作者确认容器停止并恢复所有权，不能直接重跑。</p>
    <article v-if="selected"><h2>{{ selected.name }} / {{ selected.version }}</h2>
      <p>ID：{{ selected.id }}</p><p>内容 SHA256：{{ selected.content_sha256 }}</p>
      <h3>已保存配置</h3><pre>{{ JSON.stringify(selected.descriptor, null, 2) }}</pre>
      <h3>最近校验（声明与实际校验分别记录）</h3><pre>{{ selected.validation ? JSON.stringify(selected.validation, null, 2) : '未校验' }}</pre>
    </article>
  </section>
</template>

<style scoped>
.catalog { max-width: 1100px; margin: auto; padding: 24px; }
.catalog p { line-height: 1.7; overflow-wrap: anywhere; }
.catalog details, .catalog article { margin: 20px 0; padding: 20px; border: 1px solid #d7dfe8; border-radius: 8px; }
.catalog-form { display: grid; gap: 12px; margin: 18px 0; }
.catalog label { display: block; }
.catalog input, .catalog select, .catalog textarea { max-width: 100%; padding: 8px; }
.catalog-form input { width: 70%; }
.catalog-json { margin: 16px 0; }
.catalog textarea { display: block; width: 100%; font-family: monospace; }
.catalog button { margin: 4px; padding: 8px 12px; cursor: pointer; }
.catalog button:disabled { cursor: default; opacity: .5; }
.catalog table { width: 100%; text-align: left; border-collapse: collapse; margin: 14px 0; }
.catalog td, .catalog th { padding: 12px; border-bottom: 1px solid #d7dfe8; }
.catalog pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 500px; overflow: auto; }
.catalog-error { color: #a42a24; }
</style>
