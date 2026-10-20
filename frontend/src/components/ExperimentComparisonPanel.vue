<script setup lang="ts">
import { computed } from 'vue'
import { ElTable, ElTableColumn } from 'element-plus'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import { comparisonLabels, type ExperimentComparison } from '../data/platform-comparison'
import { formatDate } from '../data/display'
import { statusLabel } from '../data/dashboard'
const props = defineProps<{ comparison: ExperimentComparison }>()
type Pair = ExperimentComparison['pairs'][number]
type Group = ExperimentComparison['groups'][string] & { arm: string }
type Metric = ExperimentComparison['resource_comparison']['metrics'][string] & { name: string }
const groups = computed<Group[]>(() => Object.entries(props.comparison.groups).map(([arm, group]) => ({ arm, ...group })))
const metrics = computed<Metric[]>(() => Object.entries(props.comparison.resource_comparison.metrics).map(([name, metric]) => ({ name, ...metric })))
</script>
<template>
  <div class="experiment-comparison">
    <div class="experiment-section-heading"><div><h3>固定实验的成对比较</h3><p>同 Case、同重复序号配对；按平台独立验收结果比较，执行完成不等于验收通过。</p></div><span class="experiment-badge">{{ comparison.mode }}</span></div>
    <p class="experiment-note">实际变化：<code>{{ comparison.changed_fields.join(', ') || '已记录：无' }}</code></p>
    <div v-if="comparison.integrity_issues.length" role="alert" class="experiment-alert">冻结证据存在问题，停止正向比较：{{ comparison.integrity_issues.join('、') }}</div>
    <div class="comparison-summary-grid"><div><span>可比 / 计划对子</span><strong>{{ comparison.summary.comparable_pairs }} <small>/ {{ comparison.summary.planned_pairs }}</small></strong></div><div><span>可比对子通过率差</span><strong>{{ comparison.summary.paired_pass_delta_percentage_points === null ? '未知' : comparison.summary.paired_pass_delta_percentage_points.toFixed(1) }}<small v-if="comparison.summary.paired_pass_delta_percentage_points !== null"> 个百分点</small></strong></div></div>
    <div class="comparison-classifications"><span v-for="(count, name) in comparison.summary.counts" :key="name">{{ comparisonLabels[name] ?? name }} <strong>{{ count }}</strong></span></div>
    <h4>分组与启动口径</h4>
    <ElTable :data="groups" class="experiment-table" row-key="arm">
      <!-- @vue-generic {Group} -->
      <ElTableColumn label="组别" width="115"><template #default="{ row }">{{ row.arm === 'baseline' ? 'Baseline' : row.arm === 'candidate' ? 'Candidate' : row.arm }}</template></ElTableColumn>
      <!-- @vue-generic {Group} -->
      <ElTableColumn label="计划 / 成员 / 已启动" min-width="180"><template #default="{ row }">{{ row.planned }} / {{ row.members }} / {{ row.started }}</template></ElTableColumn>
      <!-- @vue-generic {Group} -->
      <ElTableColumn label="未启动 / 准备失败" min-width="170"><template #default="{ row }">{{ row.not_started }} / {{ row.preparation_failed }}</template></ElTableColumn>
      <!-- @vue-generic {Group} -->
      <ElTableColumn label="已核验通过 / 已启动待定" min-width="200"><template #default="{ row }">{{ row.verified_passed ?? '未知' }} / {{ row.unresolved_started }}</template></ElTableColumn>
    </ElTable>
    <p class="experiment-note">准备失败是未启动的子集。缺证据或未完成的已启动 Run 保留在分母中；上面的百分点差只针对可比对子。</p>
    <h4>逐例证据与变化</h4>
    <ElTable :data="comparison.pairs" class="experiment-table" :row-key="(row: Pair) => `${row.case_index}-${row.repetition}`">
      <!-- @vue-generic {Pair} -->
      <ElTableColumn label="Case / 重复" min-width="170"><template #default="{ row }"><span class="mono">{{ row.case_id }}</span><p class="experiment-cell-note">重复 {{ row.repetition }}</p></template></ElTableColumn>
      <!-- @vue-generic {Pair} -->
      <ElTableColumn v-for="arm in (['baseline', 'candidate'] as const)" :key="arm" :label="arm === 'baseline' ? 'Baseline' : 'Candidate'" min-width="210"><template #default="{ row }"><template v-if="row[arm]"><RouterLink v-if="row[arm]?.run_id" :to="`/live/runs/${row[arm]?.run_id}`" class="ui-text-link">查看 Run 证据 →</RouterLink><p>{{ row[arm]?.verified_outcome ? statusLabel(row[arm]!.verified_outcome!) : '未核验' }} · {{ row[arm]?.evidence_status }}</p><p v-if="row[arm]?.issues.length" class="experiment-cell-note">{{ row[arm]?.issues.join('、') }}</p></template><span v-else class="experiment-muted">缺失或重复成员</span></template></ElTableColumn>
      <!-- @vue-generic {Pair} -->
      <ElTableColumn label="结论 / 原因" min-width="220"><template #default="{ row }"><span class="experiment-badge">{{ comparisonLabels[row.classification] ?? row.classification }}</span><p v-if="row.reasons.length" class="experiment-cell-note">{{ row.reasons.join('、') }}</p></template></ElTableColumn>
    </ElTable>
    <p class="experiment-note">这是本批固定自动测试的描述性结果。Benchmark 可以改变多个变量，不能把变化直接归因于检索策略；重复 fixture 不是独立泛化证据，也不自动产生发布或采纳建议。</p>
    <div class="experiment-section-heading section-separated"><div><h3>资源比较</h3><p>仅使用质量可比、且两边该指标都已知的相同完整对子。</p></div></div>
    <ElTable :data="metrics" class="experiment-table" row-key="name">
      <!-- @vue-generic {Metric} -->
      <ElTableColumn label="指标" min-width="170"><template #default="{ row }">{{ row.name === 'total_tokens' ? '总 Token' : row.name === 'wall_clock_ms' ? '墙钟时间（毫秒）' : row.name }}</template></ElTableColumn>
      <!-- @vue-generic {Metric} -->
      <ElTableColumn label="Baseline 均值" min-width="135"><template #default="{ row }">{{ row.baseline_mean ?? '未知' }}</template></ElTableColumn>
      <!-- @vue-generic {Metric} -->
      <ElTableColumn label="Candidate 均值" min-width="135"><template #default="{ row }">{{ row.candidate_mean ?? '未知' }}</template></ElTableColumn>
      <!-- @vue-generic {Metric} -->
      <ElTableColumn label="差值" min-width="100"><template #default="{ row }">{{ row.delta ?? '未知' }}</template></ElTableColumn>
      <!-- @vue-generic {Metric} -->
      <ElTableColumn label="完整 / 可比 / 计划对子" min-width="200"><template #default="{ row }">{{ row.valid_pairs }} / {{ row.eligible_pairs }} / {{ row.planned_pairs }}</template></ElTableColumn>
    </ElTable>
    <p class="experiment-note">差值 = Candidate − Baseline。Token 小计不等于运行总量；调用范围未确认完整时总量未知。墙钟时间含人工等待和平台验收，不是纯模型延迟；人工等待未单独计量。</p>
    <p class="experiment-note">费用未知：未保存历史价格快照，不使用当前价格补算。资源指标暂不参与质量门槛。</p>
    <details class="experiment-details"><summary>各 Run 用量小计、覆盖情况及事件引用</summary><pre>{{ JSON.stringify(comparison.resource_comparison.runs, null, 2) }}</pre></details>
    <details class="experiment-details"><summary>比较证据引用（Evaluation / TestRun ID）</summary><pre>{{ JSON.stringify(comparison.pairs, null, 2) }}</pre></details>
    <p class="experiment-provenance">比较快照 hash：<code>{{ comparison.comparison_sha256 }}</code><br />读取时间：{{ formatDate(comparison.observed_at) }}（日本时间）</p>
  </div>
</template>
