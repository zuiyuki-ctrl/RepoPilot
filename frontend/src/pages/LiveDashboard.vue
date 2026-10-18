<script setup lang="ts">
import { onMounted, ref } from 'vue'
type Dashboard={source:string;observed_at:string;agents:Record<string,number>;benchmarks:Record<string,number>;experiments:number
  preparation:Record<string,number>;lifecycle:Record<string,number>;execution:Record<string,number>;evaluation:Record<string,number>
  recent_experiments:{id:string;name:string}[];recent_runs:{id:string;lifecycle:string;execution:string;evaluation:string}[]}
const data=ref<Dashboard|null>(null),error=ref(''),loading=ref(false)
async function load(){
  loading.value=true;error.value=''
  try{
    const response=await fetch('/api/v2/dashboard',{cache:'no-store',signal:AbortSignal.timeout(15000)})
    if(!response.ok)throw new Error(`总览读取失败 HTTP ${response.status}，请检查 API 与数据库迁移。`)
    data.value=await response.json()
  }catch(e){error.value=String(e)}finally{loading.value=false}
}
onMounted(load)
</script>
<template>
  <section class="dashboard">
    <h1>RepoPilot · 实时评测工作台</h1>
    <p>让 Coding Agent 的每一次改进，都有证据支持。</p>
    <p>登记 Agent → 导入 Benchmark → 启动实验 → 查看独立验收与 Trace → 比较并记录决定 → 导出报告。</p>
    <div class="links"><RouterLink to="/live/agents">Agent 版本</RouterLink><RouterLink to="/live/benchmarks">Benchmark</RouterLink>
      <RouterLink to="/live/experiments">实验与决策</RouterLink><RouterLink to="/live/runs">Run / Trace</RouterLink><RouterLink to="/live/reports">打开已下载报告</RouterLink></div>
    <button :disabled="loading" @click="load">刷新总览</button><p v-if="error" role="alert">{{error}}</p>
    <template v-if="data">
      <p>数据时间：{{data.observed_at}} · 已登记实验：{{data.experiments}}</p>
      <p>以下是当前数据库记录数，包含协议 fixture；不混入 archived 文件，不把不同任务集混算成一个成功率。</p>
      <div class="cards"><article v-for="(counts,name) in {Agent:data.agents,Benchmark:data.benchmarks,准备状态:data.preparation,生命周期:data.lifecycle,执行结果:data.execution,平台验收:data.evaluation}" :key="name">
        <h2>{{name}}</h2><p v-if="!Object.keys(counts).length">暂无记录</p><p v-for="(count,status) in counts" :key="status">{{status}}：{{count}}</p>
      </article></div>
      <h2>最近实验</h2><p v-if="!data.recent_experiments.length">尚无实验，请先登记 Agent 与 Benchmark。</p>
      <p v-for="item in data.recent_experiments" :key="item.id"><RouterLink :to="{path:'/live/experiments',query:{id:item.id}}">{{item.name}} · {{item.id}}</RouterLink></p>
      <h2>最近运行</h2><p v-for="item in data.recent_runs" :key="item.id"><RouterLink :to="'/live/runs/'+item.id">{{item.id}}</RouterLink> · {{item.lifecycle}} · 执行 {{item.execution}} / 验收 {{item.evaluation}}</p>
    </template>
  </section>
</template>
<style scoped>
.dashboard{padding:24px;max-width:1200px;margin:auto}p{line-height:1.7;overflow-wrap:anywhere}.links,.cards{display:flex;gap:16px;flex-wrap:wrap}.cards article{border:1px solid #ccd5df;border-radius:8px;padding:16px;min-width:160px}button{margin-top:16px;padding:8px}[role=alert]{color:#a32722}
</style>
