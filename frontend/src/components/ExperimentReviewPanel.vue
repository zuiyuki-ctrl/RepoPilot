<script setup lang="ts">
import { ElButton, ElForm, ElFormItem, ElInput, ElSelect, ElOption, ElCheckbox, ElTable, ElTableColumn, ElEmpty } from 'element-plus'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/checkbox/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import 'element-plus/es/components/empty/style/css'
import { decisionLabels, type ExperimentComparison, type ExperimentReview, type QualityDecision } from '../data/platform-comparison'
import { reviewActions, type ReviewForm } from '../data/platform-experiments'
import { formatDate } from '../data/display'
defineProps<{ comparison: ExperimentComparison; target: ExperimentComparison | null; reviews: ExperimentReview[]; reviewError: string; busy: boolean; loading: boolean; canSave: boolean; saving: boolean }>()
const form = defineModel<ReviewForm>('form', { required: true })
const confirmed = defineModel<boolean>('confirmed', { required: true })
defineEmits<{ begin: []; save: [] }>()
type Check = QualityDecision['checks'][number]
</script>
<template>
  <div class="experiment-review-panel">
    <div class="experiment-section-heading"><div><h3>系统门槛判定</h3><p>仅评价本批自动测试质量是否符合预先声明的规则。</p></div><span class="experiment-badge">{{ decisionLabels[comparison.decision.status] ?? comparison.decision.status }}</span></div>
    <p class="experiment-body-text">{{ comparison.decision.reason }}</p>
    <p class="experiment-note">该判定不代表可以直接发布。旧实验没有冻结门槛时保持未评估，人工决定不会改变 Run 成绩。</p>
    <ElTable v-if="comparison.decision.checks.length" :data="comparison.decision.checks" class="experiment-table" row-key="name">
      <!-- @vue-generic {Check} -->
      <ElTableColumn prop="name" label="检查项" min-width="190" />
      <!-- @vue-generic {Check} -->
      <ElTableColumn label="实际 / 门槛" min-width="160"><template #default="{ row }">{{ row.actual }} / {{ row.required }}</template></ElTableColumn>
      <!-- @vue-generic {Check} -->
      <ElTableColumn label="满足" width="100"><template #default="{ row }">{{ row.passed ? '是' : '否' }}</template></ElTableColumn>
    </ElTable>
    <div class="experiment-section-heading section-separated"><div><h3>独立人工决定</h3><p>本地操作者自填身份，不是登录认证；与原计划审批独立。</p></div><ElButton :disabled="busy || loading" @click="$emit('begin')">核对比较并填写决定</ElButton></div>
    <p class="experiment-note">人工决定可以与系统判定不同，但必须记录理由；每次保存追加一条历史记录，不覆盖原成绩。</p>
    <section v-if="target" class="experiment-review-form-area">
      <div class="experiment-info"><strong>本次依据：{{ decisionLabels[target.decision.status] ?? target.decision.status }}</strong><code>{{ target.comparison_sha256 }}</code></div>
      <p v-if="target.comparison_sha256 !== comparison.comparison_sha256" role="alert" class="experiment-alert">比较已变化，请重新核对；旧表单不能覆盖新证据。</p>
      <ElForm label-position="top" class="experiment-form-grid" @submit.prevent="$emit('save')">
        <ElFormItem label="操作者" label-for="reviewer-name"><ElInput id="reviewer-name" v-model="form.reviewer" maxlength="100" :disabled="busy" placeholder="实际复核人" /></ElFormItem>
        <ElFormItem label="决定" label-for="review-action"><ElSelect id="review-action" v-model="form.action" :disabled="busy" aria-label="决定"><ElOption v-for="(label, value) in reviewActions" :key="value" :label="label" :value="value" /></ElSelect></ElFormItem>
        <ElFormItem label="理由" label-for="review-rationale" class="full-width"><ElInput id="review-rationale" v-model="form.rationale" type="textarea" :rows="4" maxlength="2000" show-word-limit :disabled="busy" placeholder="记录依据、权衡与尚未确认的部分" /></ElFormItem>
        <div class="full-width"><ElCheckbox v-model="confirmed" :disabled="busy">已核对上述比较与局限，确认记录我的决定</ElCheckbox></div>
        <div class="full-width"><ElButton type="primary" :disabled="!canSave" :loading="saving" native-type="submit">保存独立人工决定</ElButton></div>
      </ElForm>
    </section>
    <div class="experiment-section-heading section-separated"><div><h3>历史人工记录</h3><p>最近 20 条，每条保留当时快照；当前证据变化不会改写旧记录。</p></div></div>
    <p v-if="reviewError" role="alert" class="experiment-alert">人工记录读取失败：{{ reviewError }}</p>
    <ElEmpty v-else-if="!reviews.length" description="尚无独立人工决定" :image-size="54" />
    <details v-for="review in reviews" :key="review.id" class="experiment-details review-history-item"><summary><span>{{ reviewActions[review.action] ?? review.action }} · {{ review.reviewer }}</span><span>{{ formatDate(review.created_at) }}</span></summary><p class="experiment-body-text">{{ review.rationale }}</p><p class="experiment-note">{{ review.comparison_sha256 === comparison.comparison_sha256 ? '对应当前比较' : '历史比较' }} · 当时系统判定：{{ decisionLabels[review.machine_decision.status] ?? review.machine_decision.status }}</p><pre>{{ JSON.stringify(review.snapshot, null, 2) }}</pre></details>
  </div>
</template>
