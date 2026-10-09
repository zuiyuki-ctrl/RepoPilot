import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import Overview from './pages/Overview.vue'
import RunDetail from './pages/RunDetail.vue'
import Comparison from './pages/Comparison.vue'
import './style.css'
import './detail.css'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/experiments' },
    { path: '/experiments', component: Overview },
    { path: '/comparisons', component: Comparison },
    { path: '/runs/:experimentId', component: RunDetail },
    { path: '/:pathMatch(.*)*', redirect: '/experiments' },
  ],
})
createApp(App).use(router).mount('#app')
