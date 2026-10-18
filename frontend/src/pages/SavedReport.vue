<script setup lang="ts">
import { ref } from 'vue'
const inspected=ref<Record<string,unknown>|null>(null),error=ref(''),busy=ref(false)
async function select(event:Event){
  const file=(event.target as HTMLInputElement).files?.[0]
  if(!file)return
  inspected.value=null;error.value=''
  if(file.size>10_000_000){error.value='报告不能超过 10 MB';return}
  busy.value=true
  try{
    const response=await fetch('/api/v2/reports/inspect',{method:'POST',headers:{'Content-Type':'application/json'},body:file,signal:AbortSignal.timeout(15000)})
    if(!response.ok)throw new Error(`报告格式或 hash 校验失败（HTTP ${response.status}），请确认选择的是原始 JSON 导出文件。`)
    inspected.value=await response.json()
  }catch(e){error.value=String(e)}finally{busy.value=false}
}
</script>
<template>
  <section class="report"><h1>已下载报告 · 只读查看</h1>
    <p>选择 RepoPilot 导出的 JSON 比较报告（最多 10 MB）。文件会发送给当前 API 做结构与 hash 校验，不写入数据库、不启动 Agent，也不重新计算历史成绩。</p>
    <p>hash 一致只证明内容内部一致，不是可信签名，不能证明报告作者身份。这里的文件数据与实时 Dashboard 分开。</p>
    <input type="file" accept=".json,application/json" :disabled="busy" @change="select" />
    <p v-if="busy">正在核验…</p><p v-if="error" role="alert">{{error}}</p>
    <template v-if="inspected"><p>校验结果：{{inspected.integrity}} · 来源：{{inspected.source}}</p>
      <pre>{{JSON.stringify(inspected.report,null,2)}}</pre>
    </template>
  </section>
</template>
<style scoped>.report{padding:24px;max-width:1200px;margin:auto}p{line-height:1.7}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7fa;padding:20px;max-height:75vh;overflow:auto}[role=alert]{color:#a32722}</style>
