import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import Overview from './pages/Overview.vue'
import RunDetail from './pages/RunDetail.vue'
import Comparison from './pages/Comparison.vue'
import LiveRuns from './pages/LiveRuns.vue'
import LiveRunDetail from './pages/LiveRunDetail.vue'
import './style.css'
import './detail.css'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/live/runs', component: LiveRuns },
    { path: '/live/runs/:runId', component: LiveRunDetail },
    { path: '/', redirect: '/experiments' },
    { path: '/experiments', component: Overview },
    { path: '/comparisons', component: Comparison },
    { path: '/runs/:experimentId', component: RunDetail },
    { path: '/:pathMatch(.*)*', redirect: '/experiments' },
  ],
})
createApp(App).use(router).mount('#app')
