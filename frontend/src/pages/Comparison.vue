<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { readComparison, type ComparisonSnapshot } from '../data/comparison'

const snapshot = ref<ComparisonSnapshot | null>(null)
const error = ref('')
const loading = ref(false)
const value = (item: unknown) => item === null || item === undefined ? '未记录' : String(item)
const traceLabel = (status: string | null) => ({ recorded: '已记录', not_recorded: '未记录', partial: '部分记录' }[status ?? ''] ?? '未记录')
async function load() {
  loading.value = true
  error.value = ''
  try { snapshot.value = await readComparison() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '读取失败' }
  finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <div class="page-heading"><div><p class="eyebrow">RETRIEVAL COMPARISON</p><h1>策略对比</h1><p class="subtitle">按固定用例并排查看 Vector 与 Hybrid 的历史结果和检索证据。</p></div></div>
  <p v-if="loading" role="status">正在读取历史快照…</p>
  <div v-else-if="error" role="alert" class="error-state">{{ error }} <button @click="load">重新读取</button></div>
  <template v-else-if="snapshot">
    <div class="snapshot-note">{{ snapshot.pairs.length }} 组用例 · 每种策略每组仅一次主运行。结果不能证明 Hybrid 整体优于 Vector；证据快照也不等于完整任务轨迹。</div>
    <section v-for="pair in snapshot.pairs" :key="`${pair.caseId}/${pair.caseVersion}`" class="comparison-group">
      <div class="case-title"><h2>{{ pair.caseId }} <small>{{ pair.caseVersion }}</small></h2><span>{{ pair.complete ? '配对齐全' : '配对缺失' }}</span></div>
      <p class="condition-note">{{ pair.differences.length ? `已记录条件存在差异：${pair.differences.join('、')}` : '已记录的对照条件一致；未记录的条件不作一致性保证。' }}</p>
      <div class="comparison-columns">
        <article v-for="(run, index) in pair.runs" :key="index" class="strategy-card">
          <h3>{{ index === 0 ? 'Vector' : 'Hybrid' }}</h3>
          <p v-if="!run">没有指定该策略的主运行。</p>
          <template v-else>
            <div class="run-outcome"><strong>{{ run.status }}</strong><span>重试 {{ value(run.retryCount) }}</span></div>
            <dl class="comparison-metrics">
              <dt>测试进程</dt><dd>{{ run.test ? (run.test.passed ? '通过' : '未通过') : '未记录' }} · exit {{ value(run.test?.exitCode) }}</dd>
              <dt>完成事件</dt><dd>{{ value(run.completionSequence) }}</dd>
              <dt>检索证据</dt><dd>{{ traceLabel(run.traceStatus) }} · 快照截止 {{ value(run.traceLastSequence) }}</dd>
            </dl>
            <p class="run-id">实验 {{ run.experimentId }}</p>
            <RouterLink v-if="run.detailMatches" :to="`/runs/${run.experimentId}`">查看运行详情 →</RouterLink>
            <p v-else class="condition-note">现有详情与本次选定报告不一致，暂不跳转。</p>
            <p v-if="run.detailMatches && !run.detailEvidenceMatches" class="condition-note">详情页选用了另一份证据导出；本页仍使用对照清单指定的证据。</p>
            <p v-for="warning in run.warnings" :key="warning" class="condition-note">{{ warning }}</p>
            <details class="comparison-details">
              <summary>查询与命中 {{ run.traceStatus === 'not_recorded' || !run.traceStatus ? '（未记录）' : `（${run.queries.length} 次）` }}</summary>
              <p v-if="!run.queries.length">此快照没有可展示的查询，不能据此推断未执行检索。</p>
              <section v-for="query in run.queries" :key="query.sequence" class="query-record">
                <h4>#{{ query.sequence }} · {{ query.query }}</h4>
                <p v-if="query.diagnostics" class="condition-note">候选：向量 {{ value(query.diagnostics.vector_candidate_count) }} / 关键词 {{ value(query.diagnostics.keyword_candidate_count) }} / 交集 {{ value(query.diagnostics.overlap_count) }} / 最终含关键词 {{ value(query.diagnostics.final_keyword_hit_count) }}</p>
                <p v-else class="condition-note">双路诊断未记录</p>
                <ol class="hit-list"><li v-for="hit in query.hits" :key="hit.rank"><code>{{ hit.symbol || hit.filePath }}</code><small>{{ hit.filePath }}</small><small>向量排名 {{ hit.vectorRank ?? '—' }} · 关键词排名 {{ hit.keywordRank ?? '—' }}</small></li></ol>
              </section>
            </details>
            <details class="comparison-details">
              <summary>工具上下文</summary>
              <p>accepted 表示工具结果进入消息历史；模型请求关联次数不代表模型实际采纳了内容。</p>
              <p v-if="!run.contexts.length">未记录可展示的上下文。</p>
              <ul><li v-for="context in run.contexts" :key="context.sequence">#{{ context.sequence }} {{ context.tool }} · {{ context.disposition }} · {{ value(context.chars) }} 字符 · 关联 {{ context.modelAttempts }} 次模型请求</li></ul>
            </details>
            <details class="comparison-details"><summary>原始文件指纹</summary><p v-for="artifact in run.artifactHashes" :key="artifact.name" class="artifact-hash">{{ artifact.name }}<code>{{ artifact.sha256 }}</code></p></details>
          </template>
        </article>
      </div>
    </section>
    <section class="comparison-group"><h2>额外准备记录</h2><p>单独保留，未混入主运行配对。准备未完成不代表进程仍在运行。</p><ul><li v-for="run in snapshot.additional" :key="run.experimentId" class="additional-run"><strong>{{ run.caseId }} / {{ run.strategy }}</strong> · {{ run.status }}<br />阶段 {{ run.stage }} · 错误 {{ run.errorType ?? '未记录' }}<br /><code>{{ run.experimentId }}</code></li></ul><p v-if="!snapshot.additional.length">无额外记录。</p></section>
    <details class="comparison-group"><summary>数据来源与解释边界</summary><p class="artifact-hash">{{ snapshot.source }}</p><p>报告生成时间：{{ snapshot.generatedAt }}</p><ul><li v-for="limitation in snapshot.limitations" :key="limitation">{{ limitation }}</li></ul></details>
  </template>
</template>

<style scoped>
.comparison-group { margin: 24px 0; padding: 24px; background: white; border: 1px solid #e2e7ee; border-radius: 12px; }
.comparison-columns { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; }
.strategy-card { min-width: 0; border: 1px solid #e2e7ee; border-radius: 8px; padding: 20px; }
.strategy-card h3 { margin: 0 0 16px; }
.run-outcome { display: flex; justify-content: space-between; gap: 8px; }
.comparison-metrics { display: grid; grid-template-columns: 90px 1fr; gap: 10px; font-size: 13px; }
dt, .condition-note, .run-id { color: #64748b; } dd { margin: 0; }
.condition-note, .run-id { font-size: 12px; line-height: 1.7; }
.comparison-details { margin-top: 18px; padding-top: 14px; border-top: 1px solid #e2e7ee; font-size: 13px; line-height: 1.7; }
summary { cursor: pointer; font-weight: 600; }
.query-record { margin-top: 20px; } .query-record h4 { margin-bottom: 8px; }
.hit-list { padding-left: 22px; } .hit-list li { margin: 12px 0; } .hit-list small, .artifact-hash code { display: block; }
.artifact-hash, .run-id, .query-record, .additional-run, dd { overflow-wrap: anywhere; }
.artifact-hash { font-size: 11px; } .additional-run { margin: 16px 0; font-size: 13px; line-height: 1.8; }
@media (max-width: 1050px) { .comparison-columns { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 620px) { .comparison-group { padding: 14px; } .strategy-card { padding: 14px; } }
</style>
