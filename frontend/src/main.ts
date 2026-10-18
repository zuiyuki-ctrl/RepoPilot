import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import Overview from './pages/Overview.vue'
import RunDetail from './pages/RunDetail.vue'
import Comparison from './pages/Comparison.vue'
import LiveRuns from './pages/LiveRuns.vue'
import LiveRunDetail from './pages/LiveRunDetail.vue'
import LiveCatalog from './pages/LiveCatalog.vue'
import LiveExperiments from './pages/LiveExperiments.vue'
import LiveDashboard from './pages/LiveDashboard.vue'
import SavedReport from './pages/SavedReport.vue'
import './style.css'
import './detail.css'

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
