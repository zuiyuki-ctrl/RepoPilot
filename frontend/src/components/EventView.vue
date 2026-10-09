<script setup lang="ts">
import { computed } from 'vue'
import type { EventPayload, ContextLink, Hit } from '../data/run-detail'
import CodeBlock from './CodeBlock.vue'
const props = defineProps<{ payload: EventPayload; eventType: string; links: ContextLink[] }>()
const linked = computed(() => props.links.find(link => link.callId === props.payload.call_id))
const disposition = computed(() => ({ accepted: '正常结果已加入准备的工具消息', discarded: '结果超预算，准备的是预算错误消息', skipped: '预算耗尽，工具未执行', tool_error: '可恢复工具错误已加入准备消息' })[props.payload.disposition ?? ''] ?? props.payload.disposition ?? '未记录')
const scoreKeys = ['distance', 'score', 'vector_distance', 'keyword_score', 'rrf_score'] as const
const hasScore = (hit: Hit) => scoreKeys.some(key => hit[key] !== undefined && hit[key] !== null)
</script>
<template>
  <dl class="metadata">
    <dt>工具 / 模型</dt><dd class="mono">{{ payload.tool_name ?? payload.model ?? '未记录' }}</dd>
    <dt>该事件记录耗时</dt><dd>{{ payload.duration_ms === undefined ? '未记录' : `${payload.duration_ms} ms` }}</dd>
  </dl>
  <template v-if="eventType === 'RETRIEVAL_COMPLETED'">
    <h3>查询与返回排名</h3><p class="query-text mono">{{ payload.query ?? '未记录' }}</p>
    <p class="drawer-note">实际查询：{{ payload.effective_query ?? '未记录' }} · 请求策略：{{ payload.requested_strategy ?? '未记录' }} · 生效策略：{{ payload.retrieval_strategy ?? '未记录' }} · Top-K：{{ payload.top_k ?? '未记录' }}</p>
    <p class="drawer-note">排名是本次返回顺序。distance、keyword_score、rrf_score 保留各自含义，不换算为正确率；Hybrid 展示融合后的 Top-K。</p>
    <div v-if="payload.hits?.length" class="evidence-table-scroll"><table class="evidence-table"><thead><tr><th>排名</th><th>位置 / 符号</th><th>策略评分</th></tr></thead><tbody><tr v-for="(hit, index) in payload.hits" :key="index"><td>{{ hit.rank ?? '未记录' }}</td><td><code>{{ hit.file_path ?? '未记录' }}:{{ hit.start_line ?? '未记录' }}–{{ hit.end_line ?? '未记录' }}</code><p>{{ hit.symbol_name ?? '符号未记录' }}</p></td><td class="mono"><template v-for="score in scoreKeys" :key="score"><div v-if="hit[score] !== undefined && hit[score] !== null">{{ score }}: {{ hit[score] }}</div></template><span v-if="!hasScore(hit)">未记录</span></td></tr></tbody></table></div>
    <p v-else class="quiet">{{ payload.hits ? '已记录：本次检索零命中' : '有序检索结果未记录' }}</p>
  </template>
  <template v-if="eventType === 'TOOL_CONTEXT_PREPARED'">
    <h3>预算处理与实际准备内容</h3><p>{{ disposition }}</p>
    <dl class="metadata"><dt>工具消息字符数</dt><dd>{{ payload.content_chars ?? '未记录' }}</dd><dt>预算前 / 后</dt><dd>{{ payload.remaining_chars_before ?? '未记录' }} / {{ payload.remaining_chars_after ?? '未记录' }} 字符</dd><dt>消息内容 hash</dt><dd class="mono">{{ payload.content_sha256 ?? '未记录' }}</dd></dl>
    <p class="drawer-note">字符数不是 Token 数。已准备工具消息不代表模型收到它，更不能证明模型语义上采纳了证据。</p>
    <ul v-if="payload.sources?.length" class="context-sources"><li v-for="(source, index) in payload.sources" :key="index"><code>{{ source.source_id ?? '编号未记录' }} · {{ source.file_path ?? '未记录' }}:{{ source.start_line ?? '未记录' }}–{{ source.end_line ?? '未记录' }}</code></li></ul><p v-else class="quiet">{{ payload.sources ? '已记录：准备消息中没有代码来源' : '代码来源未记录' }}</p>
  </template>
  <template v-if="linked && (eventType === 'RETRIEVAL_COMPLETED' || eventType === 'TOOL_CONTEXT_PREPARED')">
    <h3>后续模型调用关联</h3><p class="drawer-note">通过工具消息索引、tool_call_id 与内容 hash 关联；这里只表示调用尝试包含该消息。</p>
    <ul v-if="linked.models.length" class="model-links"><li v-for="model in linked.models" :key="model.callId"><code>{{ model.callId }}</code><p>事件 #{{ model.startedSequence }} → {{ model.finishedSequence ? `#${model.finishedSequence}` : '结束事件未记录' }} · {{ model.outcome }}</p></li></ul><p v-else class="quiet">未记录可关联的后续模型调用</p>
  </template>
  <template v-if="eventType === 'MODEL_CALL_STARTED'"><h3>本次请求的工具消息清单</h3><CodeBlock :text="payload.tool_context === undefined ? null : JSON.stringify(payload.tool_context, null, 2)" /><p class="drawer-note">调用开始记录不证明供应商收到请求；成功响应也不证明模型使用了全部上下文。</p></template>
  <details class="inline-details"><summary>协议字段与完整调用 ID</summary><CodeBlock :text="JSON.stringify(payload, null, 2)" /></details>
</template>
