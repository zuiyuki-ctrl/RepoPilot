<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon, { type IconName } from './components/AppIcon.vue'
import logoUrl from '../../assets/repopilot-logo.png'
const route = useRoute()
const collapsed = ref(false)
const mobileOpen = ref(false)
const media = window.matchMedia('(max-width: 1023px)')
const narrow = ref(media.matches)
const navToggle = ref<HTMLButtonElement | null>(null)
const navClose = ref<HTMLButtonElement | null>(null)
function updateViewport() { narrow.value = media.matches; mobileOpen.value = false }
onMounted(() => media.addEventListener('change', updateViewport))
onBeforeUnmount(() => media.removeEventListener('change', updateViewport))
watch(mobileOpen, async (open) => { await nextTick(); (open ? navClose.value : navToggle.value)?.focus() })
const groups: { label: string; items: { path: string; label: string; icon: IconName }[] }[] = [
  { label: '实验工作', items: [
    { path: '/live/dashboard', label: '工作台', icon: 'dashboard' },
    { path: '/live/experiments', label: '实验批次', icon: 'experiment' },
    { path: '/live/runs', label: '运行记录', icon: 'run' },
  ] },
  { label: '资源管理', items: [
    { path: '/live/agents', label: 'Agent 版本', icon: 'agent' },
    { path: '/live/benchmarks', label: 'Benchmark', icon: 'benchmark' },
    { path: '/live/reports', label: '报告文件', icon: 'report' },
  ] },
  { label: '历史归档', items: [
    { path: '/experiments', label: '历史快照', icon: 'archive' },
    { path: '/comparisons', label: '策略对比', icon: 'compare' },
  ] },
]
function active(path: string) {
  return route.path === path || (path === '/live/runs' && route.path.startsWith('/live/runs/')) || (path === '/experiments' && route.path.startsWith('/runs/'))
}
const currentGroup = computed(() => groups.find(group => group.items.some(item => active(item.path))))
const currentPage = computed(() => route.path.startsWith('/live/runs/') ? '运行详情' : route.path.startsWith('/runs/') ? '历史运行详情' : groups.flatMap(group => group.items).find(item => active(item.path))?.label ?? '工作台')
const mode = computed(() => route.path === '/live/reports' ? '报告文件 · 只读核验' : route.path.startsWith('/live/') ? '实时数据' : '历史快照 · 只读')
function toggleSidebar() {
  if (narrow.value) mobileOpen.value = !mobileOpen.value
  else collapsed.value = !collapsed.value
}
watch(() => route.fullPath, () => { mobileOpen.value = false })
</script>
<template>
  <div class="app-shell" :class="{ 'sidebar-collapsed': collapsed, 'mobile-nav-open': mobileOpen }" @keydown.esc="mobileOpen = false">
    <button v-if="mobileOpen" class="sidebar-backdrop" aria-label="关闭导航" @click="mobileOpen = false" />
    <aside id="app-navigation" class="app-sidebar">
      <RouterLink to="/live/dashboard" class="app-brand" aria-label="RepoPilot 工作台"><span class="app-logo"><img :src="logoUrl" alt="RepoPilot" /></span><span class="app-brand-caption">实验与评测平台</span></RouterLink>
      <button ref="navClose" class="mobile-nav-close icon-button" aria-label="关闭导航" @click="mobileOpen = false"><AppIcon name="close" /></button>
      <nav class="app-nav" aria-label="主导航"><div v-for="group in groups" :key="group.label" class="nav-group"><p class="nav-group-label">{{ group.label }}</p><RouterLink v-for="item in group.items" :key="item.path" :to="item.path" :title="item.label" class="app-nav-link" :class="{ active: active(item.path) }" :aria-current="active(item.path) ? 'page' : undefined"><AppIcon :name="item.icon" /><span class="app-nav-label">{{ item.label }}</span><span class="active-indicator" /></RouterLink></div></nav>
      <div class="app-sidebar-footer"><span class="sidebar-footer-mark">R</span><div><strong>RepoPilot</strong><span>让改进有据可查</span></div></div>
    </aside>
    <div class="app-workspace" :inert="mobileOpen">
      <header class="workspace-header"><div class="header-location"><button ref="navToggle" class="icon-button" aria-label="切换侧栏" aria-controls="app-navigation" :aria-expanded="narrow ? mobileOpen : !collapsed" @click="toggleSidebar"><AppIcon name="menu" /></button><span class="breadcrumb-parent">{{ currentGroup?.label ?? '实验工作' }}</span><AppIcon name="chevron" :size="13" /><span class="breadcrumb-current">{{ currentPage }}</span></div><span class="data-mode"><span />{{ mode }}</span></header>
      <main class="page-content"><RouterView /></main>
    </div>
  </div>
</template>
