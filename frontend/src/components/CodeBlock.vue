<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ text: string | null; diff?: boolean }>()
const lines = computed(() => props.text?.split('\n') ?? [])
function lineClass(line: string) {
  if (!props.diff) return ''
  if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff ') || line.startsWith('@@')) return 'diff-header'
  if (line.startsWith('+')) return 'diff-added'
  if (line.startsWith('-')) return 'diff-removed'
  return ''
}
</script>
<template>
  <p v-if="text === null" class="quiet">未记录</p>
  <p v-else-if="text === ''" class="quiet">已记录，内容为空</p>
  <pre v-else class="code-block" tabindex="0" aria-label="只读文本内容"><code><span v-for="(line, index) in lines" :key="index" :class="lineClass(line)">{{ line }}{{ index < lines.length - 1 ? '\n' : '' }}</span></code></pre>
</template>
