<script setup lang="ts">
import { computed } from 'vue'
import { ElButton, ElTable, ElTableColumn, ElEmpty, ElSkeleton } from 'element-plus'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/skeleton/style/css'
import AppIcon, { type IconName } from './AppIcon.vue'
import { totalRecords, statusLabel, type Dashboard } from '../data/dashboard'
import { formatDate } from '../data/display'

const props = defineProps<{ data: Dashboard | null; error: string; loading: boolean }>()
defineEmits<{ refresh: [] }>()
type RecentExperiment = Dashboard['recent_experiments'][number]
type RecentRun = Dashboard['recent_runs'][number]
const metrics = computed<{ label: string; value: number | null; note: string; icon: IconName; to: string }[]>(() => [
  { label: 'Agent 版本', value: props.data ? totalRecords(props.data.agents) : null, note: '已登记的版本记录', icon: 'agent', to: '/live/agents' },
  { label: 'Benchmark 版本', value: props.data ? totalRecords(props.data.benchmarks) : null, note: '已导入的版本记录', icon: 'benchmark', to: '/live/benchmarks' },
  { label: '实验批次', value: props.data?.experiments ?? null, note: '当前数据库中的实验', icon: 'experiment', to: '/live/experiments' },
  { label: '运行记录', value: props.data ? totalRecords(props.data.lifecycle) : null, note: '按生命周期分组的 Run', icon: 'run', to: '/live/runs' },
])
const statusGroups = computed(() => [
  { label: '准备状态', note: '实验成员', counts: props.data?.preparation },
  { label: '生命周期', note: '运行记录', counts: props.data?.lifecycle },
  { label: '执行结果', note: 'Agent 执行', counts: props.data?.execution },
  { label: '平台验收', note: '独立评价', counts: props.data?.evaluation },
])
const connection = computed(() => props.loading ? props.data ? '正在刷新' : '正在读取' : props.error ? props.data ? '上次读取' : '未连接' : props.data ? '已读取' : '未连接')
</script>
<template>
  <div class="dashboard-page">
    <div class="ui-page-heading"><div><p class="ui-kicker">评测工作台</p><h1>工作概览</h1><p class="ui-page-description">查看实验进展，从运行结果追溯执行与验收证据。</p></div><ElButton :loading="loading" type="primary" @click="$emit('refresh')"><AppIcon name="refresh" :size="16" />刷新总览</ElButton></div>
    <div class="dashboard-meta"><span class="connection-state" :class="{ 'is-unavailable': Boolean(error) }"><i />{{ connection }}</span><span v-if="data">{{ loading || error ? '上次读取时间' : '数据时间' }}：{{ formatDate(data.observed_at) }}（日本时间）</span><span v-else>实时数据库 · 尚无可展示的响应</span></div>
    <div v-if="error" class="dashboard-notice" role="alert"><AppIcon name="report" :size="20" /><div><strong>{{ data ? '刷新失败，下面保留上次读取的数据' : '暂时无法读取实时数据' }}</strong><p>{{ error }}<template v-if="data"> 当前展示的内容不代表最新状态。</template></p></div><RouterLink to="/experiments">查看历史快照 →</RouterLink></div>
    <div class="metric-grid"><RouterLink v-for="metric in metrics" :key="metric.label" :to="metric.to" class="ui-card metric-card"><div class="metric-top"><span class="metric-icon"><AppIcon :name="metric.icon" :size="24" /></span><span class="metric-label">{{ metric.label }}</span></div><ElSkeleton v-if="loading && !data" :rows="0" class="metric-skeleton" /><strong v-else class="metric-value" :class="{ 'is-missing': metric.value === null }">{{ metric.value === null ? '未连接' : metric.value.toLocaleString('zh-CN') }}</strong><div class="metric-footer"><span>{{ metric.note }}</span><AppIcon name="arrow" :size="15" /></div></RouterLink></div>
    <p class="dashboard-scope">统计范围为当前数据库记录，包含协议 fixture；历史归档不计入，也不合并不同任务集的成功率。</p>
    <div class="dashboard-recent-grid">
      <section class="ui-card dashboard-list-card">
        <div class="ui-card-heading"><div><h2>最近实验</h2><p>从批次进入运行与配对比较</p></div><RouterLink to="/live/experiments" class="ui-text-link">查看全部 <AppIcon name="arrow" :size="15" /></RouterLink></div>
        <ElSkeleton v-if="loading && !data" :rows="3" class="dashboard-list-loading" />
        <template v-else-if="data"><ElTable v-if="data.recent_experiments.length" :data="data.recent_experiments" class="dashboard-table" row-key="id">
          <!-- @vue-generic {RecentExperiment} -->
          <ElTableColumn label="实验" min-width="180"><template #default="{ row }"><RouterLink :to="{ path: '/live/experiments', query: { id: row.id } }" class="record-title">{{ row.name }}</RouterLink><span class="record-id mono" :title="row.id">{{ row.id }}</span></template></ElTableColumn>
          <!-- @vue-generic {RecentExperiment} -->
          <ElTableColumn label="创建时间" min-width="160"><template #default="{ row }"><span class="record-date">{{ row.created_at ? formatDate(row.created_at) : '未记录' }}</span></template></ElTableColumn>
        </ElTable><ElEmpty v-else description="尚无实验记录" :image-size="62"><RouterLink to="/live/experiments" class="ui-text-link">前往实验批次 →</RouterLink></ElEmpty></template><ElEmpty v-else description="连接后显示最近实验" :image-size="62" />
      </section>
      <section class="ui-card dashboard-list-card">
        <div class="ui-card-heading"><div><h2>最近运行</h2><p>执行结果与平台验收分别保留</p></div><RouterLink to="/live/runs" class="ui-text-link">查看全部 <AppIcon name="arrow" :size="15" /></RouterLink></div>
        <ElSkeleton v-if="loading && !data" :rows="3" class="dashboard-list-loading" />
        <template v-else-if="data"><ElTable v-if="data.recent_runs.length" :data="data.recent_runs" class="dashboard-table" row-key="id">
          <!-- @vue-generic {RecentRun} -->
          <ElTableColumn label="运行 / 生命周期" min-width="160"><template #default="{ row }"><RouterLink :to="`/live/runs/${row.id}`" class="record-title mono" :title="row.id">{{ row.id.slice(0, 8) }}…</RouterLink><span class="record-id" :title="row.lifecycle">{{ statusLabel(row.lifecycle) }}</span></template></ElTableColumn>
          <!-- @vue-generic {RecentRun} -->
          <ElTableColumn label="执行" min-width="90"><template #default="{ row }"><span class="dashboard-state-label" :title="row.execution">{{ statusLabel(row.execution) }}</span></template></ElTableColumn>
          <!-- @vue-generic {RecentRun} -->
          <ElTableColumn label="验收" min-width="90"><template #default="{ row }"><span class="dashboard-state-label" :title="row.evaluation">{{ statusLabel(row.evaluation) }}</span></template></ElTableColumn>
        </ElTable><ElEmpty v-else description="尚无运行记录" :image-size="62" /></template><ElEmpty v-else description="连接后显示最近运行" :image-size="62" />
      </section>
    </div>
    <section class="ui-card dashboard-status-card"><div class="ui-card-heading"><div><h2>状态分布</h2><p>四个独立维度，数量不跨维度相加</p></div><span class="ui-muted">数据库记录数</span></div><div class="dashboard-status-grid"><div v-for="group in statusGroups" :key="group.label" class="dashboard-status-group"><h3>{{ group.label }}<span>{{ group.note }}</span></h3><ElSkeleton v-if="loading && !data" :rows="2" /><template v-else-if="group.counts"><dl v-if="Object.keys(group.counts).length"><div v-for="(count, status) in group.counts" :key="status"><dt :title="String(status)">{{ statusLabel(String(status)) }}</dt><dd>{{ count.toLocaleString('zh-CN') }}</dd></div></dl><p v-else class="ui-muted">暂无记录</p></template><p v-else class="ui-muted">未连接</p></div></div></section>
    <div class="dashboard-bottom-grid"><section class="ui-card dashboard-guide"><div class="ui-card-heading"><div><h2>开始一次有据可查的比较</h2><p>按固定版本组织输入，再核对结果和证据</p></div></div><ol><li><span>01</span><RouterLink to="/live/agents">登记 Agent 版本</RouterLink></li><li><span>02</span><RouterLink to="/live/benchmarks">准备 Benchmark</RouterLink></li><li><span>03</span><RouterLink to="/live/experiments">创建实验与比较</RouterLink></li></ol></section><section class="ui-card dashboard-archive"><AppIcon name="archive" :size="25" /><h2>复查已有证据</h2><p>历史快照与报告文件独立查看，保留各自来源和统计口径。</p><div><RouterLink to="/experiments" class="ui-text-link">历史快照 →</RouterLink><RouterLink to="/live/reports" class="ui-text-link">打开报告文件 →</RouterLink></div></section></div>
    <footer class="dashboard-footer">RepoPilot <span>可观测 · 可评测 · 可实验</span></footer>
  </div>
</template>
