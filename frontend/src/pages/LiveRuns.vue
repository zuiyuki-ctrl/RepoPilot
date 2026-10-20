<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { readLive, type PlatformRun } from '../data/platform-runs'
import { ElButton, ElInput, ElTable, ElTableColumn, ElEmpty, ElSkeleton } from 'element-plus'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/skeleton/style/css'
import { statusLabel as baseStatusLabel } from '../data/dashboard'
const statusLabel = (value: string) => ({ awaiting_input: '等待审批', evaluating: '独立验收中', interrupted: '已中断' } as Record<string, string>)[value] ?? baseStatusLabel(value)
import { formatDate } from '../data/display'
import '../runs.css'
const search = ref('')
const filtered = computed(() => runs.value.filter(run => `${run.id} ${run.case_id} ${run.agent.name} ${run.agent.version}`.toLowerCase().includes(search.value.trim().toLowerCase())))
let generation = 0
const runs = ref<PlatformRun[]>([])
const loading = ref(false)
const error = ref('')
const connected = ref(false)
const offset = ref(0)
async function load(nextOffset = offset.value) {
  const current = ++generation
  loading.value = true; error.value = ''; connected.value = false
  try {
    const page = await readLive<{ source: string; items: PlatformRun[] }>(`?limit=20&offset=${nextOffset}`)
    if (page.source !== 'live' || !Array.isArray(page.items)) throw new Error('运行响应格式不符合 v2 协议。')
    if (current !== generation) return
    runs.value = page.items; offset.value = nextOffset; connected.value = true
  } catch (e) { if (current === generation) error.value = e instanceof Error ? e.message : '读取失败' }
  finally { if (current === generation) loading.value = false }
}
onMounted(() => load())
onUnmounted(() => { generation++ })
</script>
<template>
<div class="runs-page"><div class="ui-page-heading"><div><p class="ui-kicker">数据库记录 · v2</p><h1>运行记录</h1><p class="ui-page-description">按用例与 Agent 定位运行，分别核对执行、验收与证据。</p></div><ElButton :disabled="loading" :loading="loading" @click="load()">刷新列表</ElButton></div>
<section class="ui-card runs-list-card"><div class="runs-toolbar"><div><h2>已保存运行</h2><p role="status">{{ loading ? '正在读取' : connected ? '已读取当前数据库' : '连接尚未确认' }} · 每页最多 20 条 · 筛选仅作用于当前页</p></div><ElInput v-model="search" clearable placeholder="搜索用例、Agent 或 Run ID" aria-label="搜索当前页运行" /></div>
<p v-if="error" role="alert">{{ error }}{{ runs.length ? ' · 下方保留上次读取的列表。' : '' }}</p>
<ElSkeleton v-if="loading && !runs.length" :rows="4" />
<ElTable v-else-if="filtered.length" :data="filtered" row-key="id">
<ElTableColumn label="用例 / Agent" min-width="230"><template #default="{ row }"><RouterLink :to="`/live/runs/${row.id}`">{{ row.case_id }} / {{ row.case_version }}</RouterLink><p>{{ row.agent.name }} · {{ row.agent.version }}</p><span class="run-id">{{ row.id }}</span></template></ElTableColumn>
<ElTableColumn label="运行阶段" min-width="125"><template #default="{ row }">{{ statusLabel(row.lifecycle) }}</template></ElTableColumn>
<ElTableColumn label="执行结果" min-width="125"><template #default="{ row }">{{ statusLabel(row.execution_status) }}</template></ElTableColumn>
<ElTableColumn label="独立验收" min-width="125"><template #default="{ row }">{{ statusLabel(row.evaluation_outcome) }}</template></ElTableColumn>
<ElTableColumn label="观测证据" min-width="160"><template #default="{ row }">{{ row.observation.level }} / {{ row.observation.completeness }}</template></ElTableColumn>
<ElTableColumn label="创建时间（日本时间）" min-width="185"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></ElTableColumn>
<ElTableColumn label="操作" width="100"><template #default="{ row }"><RouterLink :to="`/live/runs/${row.id}`">查看详情 →</RouterLink></template></ElTableColumn>
</ElTable><ElEmpty v-else :description="search ? '当前页没有符合条件的运行' : error ? '连接后可读取运行记录' : '当前页没有 v2 运行记录'" :image-size="64" />
<p class="run-note">当前仅提供查询，Agent 启动入口尚未开放；旧任务不会自动转换为新协议数据。观测层级不代表任务能力评分。</p>
<div class="runs-pagination"><span>第 {{ Math.floor(offset / 20) + 1 }} 页{{ error && runs.length ? ' · 上次读取' : '' }}</span><ElButton :disabled="loading || offset === 0" @click="load(Math.max(0, offset - 20))">上一页</ElButton><ElButton :disabled="loading || !connected || runs.length < 20" @click="load(offset + 20)">下一页</ElButton></div>
</section></div></template>
