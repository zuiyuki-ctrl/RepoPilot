<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { readLive, type PlatformRun } from '../data/platform-runs'
const runs = ref<PlatformRun[]>([])
const loading = ref(false)
const error = ref('')
const connected = ref(false)
const offset = ref(0)
async function load(nextOffset = offset.value) {
  loading.value = true; error.value = ''; connected.value = false; runs.value = []
  try {
    const page = await readLive<{ source: string; items: PlatformRun[] }>(`?limit=20&offset=${nextOffset}`)
    if (page.source !== 'live' || !Array.isArray(page.items)) throw new Error('运行响应格式不符合 v2 协议。')
    runs.value = page.items; offset.value = nextOffset; connected.value = true
  } catch (e) { error.value = e instanceof Error ? e.message : '读取失败' }
  finally { loading.value = false }
}
onMounted(() => load())
</script>
<template>
  <section class="live-panel">
    <h1>实时运行 · v2</h1>
    <p>来自后端数据库，与历史快照分开。当前仅提供查询，Agent 启动和审批入口尚未开放。</p>
    <p role="status">{{ loading ? '正在连接…' : connected ? '后端已连接，运行存储可读取' : '连接尚未确认' }}</p>
    <button :disabled="loading" @click="load()">刷新</button>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-else-if="connected && !runs.length">当前页没有 v2 运行。旧任务不会自动转换为新协议数据。</p>
    <table v-if="runs.length">
      <thead><tr><th>任务 / Agent</th><th>运行阶段</th><th>执行结果</th><th>平台验收</th><th>观测摘要</th></tr></thead>
      <tbody><tr v-for="run in runs" :key="run.id">
        <td><RouterLink :to="`/live/runs/${run.id}`">{{ run.case_id }} / {{ run.case_version }}</RouterLink><br>{{ run.agent.name }} · {{ run.agent.version }}</td>
        <td>{{ run.lifecycle }}</td><td>{{ run.execution_status }}</td><td>{{ run.evaluation_outcome }}</td>
        <td>{{ run.observation.level }} / {{ run.observation.completeness }}</td>
      </tr></tbody>
    </table>
    <p><button :disabled="loading || offset === 0" @click="load(Math.max(0, offset - 20))">上一页</button>
      <button :disabled="loading || !connected || runs.length < 20" @click="load(offset + 20)">下一页</button></p>
  </section>
</template>
<style scoped>
.live-panel { padding: 24px; } table { width: 100%; border-collapse: collapse; } th, td { text-align: left; padding: 12px; border-bottom: 1px solid #ddd; } button { margin-right: 12px; padding: 6px 12px; } [role=alert] { color: #a52a2a; }
</style>
