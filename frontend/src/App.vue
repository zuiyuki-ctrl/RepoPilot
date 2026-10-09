<script setup lang="ts">
import { useRoute } from 'vue-router'
import logoUrl from '../../assets/repopilot-logo.png'
const route = useRoute()
</script>
<template>
  <div class="workbench">
    <aside class="sidebar">
      <a class="brand" href="#/experiments"><span class="brand-logo"><img :src="logoUrl" alt="RepoPilot" /></span><span class="brand-caption">实验工作台</span></a>
      <nav aria-label="主导航">
        <RouterLink to="/experiments" :class="route.path === '/experiments' ? 'nav-item' : 'nav-plain'">实验总览</RouterLink>
        <span :class="route.path.startsWith('/runs/') ? 'nav-item' : 'nav-pending'">运行详情 <small v-if="!route.path.startsWith('/runs/')">从总览选择运行</small></span>
        <RouterLink to="/comparisons" :class="route.path === '/comparisons' ? 'nav-item' : 'nav-plain'">策略对比</RouterLink>
      </nav>
      <div class="sidebar-note">从结果追溯证据<br />从证据理解差异</div>
    </aside>
    <div class="workspace">
      <header class="topbar"><span>可观测 · 可评测 · 可实验</span><span class="snapshot-label">历史快照 <span class="quiet">/ 只读 · 未连接后端</span></span></header>
      <main><RouterView /></main>
    </div>
  </div>
</template>
