<script setup lang="ts">
import { display, label, type Decision } from '../data/assessment'
import ResourceDelta from './ResourceDelta.vue'
defineProps<{ decision: Decision | null; counts: Record<string, number | null> | null }>()
</script>
<template>
  <section class="decision-panel">
    <p class="eyebrow">BATCH DECISION · 不执行采用或发布</p>
    <h2>{{ decision ? label(decision.verdict) : '决策证据未记录' }}</h2>
    <p>{{ decision ? label(decision.policy_source) : '这是旧版报告，请使用现有离线脚本重新导出。' }}<span v-if="decision?.policy"> · 版本 {{ decision.policy.version }}</span></p>
    <div v-if="counts" class="count-grid"><div v-for="(count, key) in counts" :key="key"><strong>{{ display(count) }}</strong><span>{{ label(key) }}</span></div></div>
    <template v-if="decision">
      <p>已分类且有启动证据 {{ display(decision.quality.classified_started_pairs) }} / 所选配对 {{ display(decision.quality.selected_pairs) }} · 覆盖率 {{ display(decision.quality.coverage) }} · 质量变化 {{ display(decision.quality.delta_pp) }} 个百分点</p>
      <p class="quiet">质量变化只针对可比、验收已定且有启动证据的配对，不是未决样本被剔除后的“全批成功率”。资源均值同样显示有效样本覆盖率。</p>
      <ul><li v-for="reason in decision.missingReasons" :key="reason">{{ label(reason) }}</li></ul>
      <div class="check-table" v-if="decision.checks.length"><table><thead><tr><th>检查项</th><th>观测值</th><th>门槛</th><th>结果</th></tr></thead><tbody>
        <tr v-for="check in decision.checks" :key="String(check.name)"><td>{{ label(check.name) }}</td><td>{{ display(check.observed) }}</td><td>{{ display(check.threshold) }}</td><td>{{ label(check.status) }}</td></tr>
      </tbody></table></div>
      <ResourceDelta :resources="decision.resources" />
      <details><summary>预声明范围与门槛</summary><p v-if="!decision.policy">没有配置门槛，不使用默认数值代替用户决策。</p>
        <dl v-else><template v-for="(item, key) in decision.policy" :key="key"><dt>{{ key }}</dt><dd>{{ display(item) }}</dd></template></dl>
        <ul><li v-for="pair in decision.expectedPairs" :key="`${pair.case_id}/${pair.case_version}/${pair.repeat_index}`">{{ pair.case_id }} / {{ pair.case_version }} / repeat {{ pair.repeat_index }}</li></ul>
      </details>
      <h3>下一步需要验证什么</h3><ul><li v-for="step in decision.nextSteps" :key="step">{{ step }}</li></ul>
      <h3>人工采用记录</h3>
      <p v-if="decision.review">{{ label(decision.review.action) }} · {{ decision.review.reviewer }} · {{ decision.review.recorded_at }}<br />{{ decision.review.rationale }}</p>
      <p v-else>尚未记录。由实际复核人通过 decision_review 文件导入，不能用计划审批代替。当前页面只展示，不提交审批。</p>
      <details><summary>绑定指纹与解释边界</summary><code>{{ decision.decision_sha256 }}</code><ul><li v-for="note in decision.limitations" :key="note">{{ note }}</li></ul></details>
    </template>
  </section>
</template>
<style scoped>
.decision-panel { padding: 24px; background: white; border: 0; border-radius: var(--ui-radius); box-shadow: var(--ui-shadow); line-height: 1.7; font-size: 13px; }
h2 { margin: 4px 0 12px; } .count-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin: 20px 0; }
.count-grid div { display: flex; flex-direction: column; padding: 14px; background: #f7f8fa; border: 0; border-radius: 6px; } .count-grid strong { font-size: 23px; }
.check-table { overflow-x: auto; } table { border-collapse: collapse; width: 100%; text-align: left; } td, th { padding: 10px; border-bottom: 1px solid #e2e7ee; }
summary { cursor: pointer; font-weight: 600; } details { margin: 16px 0; } code { overflow-wrap: anywhere; } dl { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } dd { margin: 0; overflow-wrap: anywhere; }
.quiet { color: #64748b; } @media (max-width: 700px) { .count-grid { grid-template-columns: repeat(2, 1fr); } .decision-panel { padding: 14px; } }
</style>
