<script setup lang="ts">
import type { FailureAnalysis } from '../data/assessment'
import { label, display } from '../data/assessment'
defineProps<{ analysis: FailureAnalysis | null; experimentId: string }>()
const anchor = (experiment: string, id: string) => `evidence-${experiment}-${encodeURIComponent(id)}`
function focusEvidence(id: string) {
  const element = document.getElementById(id)
  element?.scrollIntoView({ block: 'center' })
  element?.focus({ preventScroll: true })
}
</script>
<template>
  <details class="failure-evidence">
    <summary>失败事实与证据复核</summary>
    <p v-if="!analysis">旧报告未生成本模块分析，不能推断没有失败。</p>
    <template v-else>
      <p>{{ analysis.status }} · 终止阶段 {{ analysis.termination_stage }} · 观察阶段 {{ analysis.observedStages.join('、') || '未记录' }}</p>
      <p>主要类别 {{ analysis.primary_category }} · 根因 {{ analysis.root_cause_status }} · {{ label(analysis.review_status) }}</p>
      <ul><li v-for="(fact, index) in analysis.facts" :key="index">{{ fact.kind }} <a v-for="id in fact.evidenceIds" :key="id" :href="`#${anchor(experimentId, id)}`" @click.prevent="focusEvidence(anchor(experimentId, id))">[{{ id }}]</a></li></ul>
      <p v-for="(hypothesis, index) in analysis.hypotheses" :key="index">假设（{{ hypothesis.source }} / {{ label(hypothesis.review_status) }}）：{{ hypothesis.statement }}</p>
      <p>缺失：{{ analysis.missing.join('、') || '当前列出的检查项无缺失；不代表完整根因证明' }}</p>
      <div v-for="evidence in analysis.evidence" :id="anchor(experimentId, evidence.id)" :key="evidence.id" class="evidence-ref" tabindex="-1">
        <strong>{{ evidence.id }}</strong> · {{ evidence.source }}
        <p v-for="(item, key) in evidence.reference" v-show="item != null" :key="key">{{ key }}: {{ display(item) }}</p>
        <p v-if="evidence.sequences.length">事件 #{{ evidence.sequences.join('、#') }}</p>
        <p v-for="(test, index) in evidence.testCases" :key="index">{{ test.classname }} / {{ test.name }} · {{ test.outcome }}</p>
      </div>
      <p v-if="analysis.review">复核人 {{ analysis.review.reviewer }} · {{ analysis.review.recorded_at }}<br />{{ analysis.review.rationale }}</p>
      <p>测试断言失败／超时不是根因证明；未保存的 Diff 不读取当前工作区补齐。</p><code>{{ analysis.analysis_sha256 }}</code>
    </template>
  </details>
</template>
<style scoped>
.failure-evidence { margin-top: 18px; border-top: 1px solid #e2e7ee; padding-top: 14px; font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }
summary { cursor: pointer; font-weight: 600; } .evidence-ref { background: #f8fafc; border: 1px solid #e2e7ee; border-radius: 6px; padding: 10px; margin: 12px 0; } .evidence-ref p { margin: 4px 0; }
</style>
