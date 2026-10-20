import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
const Overview = () => import('./pages/Overview.vue')
const RunDetail = () => import('./pages/RunDetail.vue')
const Comparison = () => import('./pages/Comparison.vue')
const LiveRuns = () => import('./pages/LiveRuns.vue')
const LiveRunDetail = () => import('./pages/LiveRunDetail.vue')
const LiveCatalog = () => import('./pages/LiveCatalog.vue')
import LiveDashboard from './pages/LiveDashboard.vue'
const SavedReport = () => import('./pages/SavedReport.vue')
import './style.css'
import './detail.css'
import './workbench.css'

// 批次表单和比较组件按路由加载，避免增加工作台首屏体积。
const LiveExperiments = () => import('./pages/LiveExperiments.vue')

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/live/dashboard', component: LiveDashboard },
    { path: '/live/reports', component: SavedReport },
    { path: '/live/experiments', component: LiveExperiments },
    { path: '/live/agents', component: LiveCatalog },
    { path: '/live/benchmarks', component: LiveCatalog },
    { path: '/live/runs', component: LiveRuns },
    { path: '/live/runs/:runId', component: LiveRunDetail },
    { path: '/', redirect: '/live/dashboard' },
    { path: '/experiments', component: Overview },
    { path: '/comparisons', component: Comparison },
    { path: '/runs/:experimentId', component: RunDetail },
    { path: '/:pathMatch(.*)*', redirect: '/live/dashboard' },
  ],
})
createApp(App).use(router).mount('#app')
