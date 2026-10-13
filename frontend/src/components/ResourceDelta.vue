<script setup lang="ts">
import { display, type Resources } from '../data/assessment'
defineProps<{ resources: Resources | null }>()
const names = { tokens: 'Token', estimated_cost: '估算成本', wall_time_ms: '墙钟时长 (ms)' }
</script>
<template>
  <p v-if="!resources" class="quiet">资源差额未记录，不以 0 替代。</p>
  <div v-else class="resource-table">
    <table><thead><tr><th>指标</th><th>Baseline</th><th>Candidate</th><th>差额</th><th>变化 %</th><th>有效配对／覆盖率</th></tr></thead>
      <tbody><tr v-for="(name, key) in names" :key="key"><th>{{ name }} {{ resources[key].currency ?? '' }}</th>
        <td>{{ display(resources[key].baseline) }}</td><td>{{ display(resources[key].candidate) }}</td>
        <td>{{ display(resources[key].absolute) }}</td><td>{{ resources[key].status === 'baseline_zero' ? '基线为 0，不可计算' : display(resources[key].relative_percent) }}</td>
        <td>{{ display(resources[key].valid_pairs) }} / {{ display(resources[key].coverage) }}</td></tr></tbody>
    </table>
    <p class="quiet">差额 = Candidate − Baseline；仅使用同对完整数据。成本为估算，墙钟包含人工等待，准备期向量化不计入此处。未决／不可比配对的数值只作描述。</p>
  </div>
</template>
<style scoped>
.resource-table { overflow-x: auto; font-size: 12px; margin: 16px 0; }
table { width: 100%; border-collapse: collapse; text-align: left; } th, td { padding: 10px; border-bottom: 1px solid #e2e7ee; min-width: 85px; vertical-align: top; overflow-wrap: anywhere; }
.quiet { font-size: 12px; line-height: 1.7; color: #64748b; }
</style>
