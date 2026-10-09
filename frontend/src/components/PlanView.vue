<script setup lang="ts">
import type { Plan } from '../data/run-detail'
defineProps<{ plan: Plan | null }>()
</script>
<template>
  <template v-if="plan">
    <p class="evidence-prose">{{ plan.summary }}</p>
    <ol class="plan-steps">
      <li v-for="step in plan.steps" :key="step.id">
        <h3>步骤 {{ step.id }}</h3><p>{{ step.description }}</p>
        <p class="quiet">涉及文件：<code>{{ step.files.join('、') }}</code></p>
        <p class="quiet">引用证据：<code>{{ step.sourceIds.join('、') }}</code></p>
        <p><span class="quiet">验证要求：</span>{{ step.verification }}</p>
      </li>
    </ol>
  </template>
  <p v-else class="quiet">计划未记录</p>
</template>
