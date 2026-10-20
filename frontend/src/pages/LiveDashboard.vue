<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, shallowRef } from 'vue'
import DashboardView from '../components/DashboardView.vue'
import { readDashboard, type Dashboard } from '../data/dashboard'
const data = shallowRef<Dashboard | null>(null)
const error = ref('')
const loading = ref(true)
let controller: AbortController | undefined
async function load() {
  controller?.abort()
  const request = new AbortController()
  controller = request
  loading.value = true
  error.value = ''
  try {
    const response = await readDashboard(request.signal)
    if (!request.signal.aborted) data.value = response
  } catch (cause) {
    if (!request.signal.aborted) error.value = cause instanceof Error ? cause.message : '总览读取失败。'
  } finally { if (!request.signal.aborted) loading.value = false }
}
onMounted(load)
onBeforeUnmount(() => controller?.abort())
</script>
<template>
  <DashboardView :data="data" :error="error" :loading="loading" @refresh="load" />
</template>
