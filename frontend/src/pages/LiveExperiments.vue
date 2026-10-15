<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
type Version = { id: string; name: string; version: string; status: string }
type Member = { id: string; sequence: number; case_index: number; repetition: number; arm: string; status: string; error_code: string | null;
  run_id: string | null; lifecycle: string | null; execution_status: string | null; evaluation_outcome: string | null }
type Detail = { id: string; status: string; manifest_sha256: string; manifest: Record<string, unknown>; members: Member[]; cancel_requested: boolean }
const agents=ref<Version[]>([]), suites=ref<Version[]>([])
const experiments=ref<{id:string;name:string}[]>([])
const detail=ref<Detail|null>(null), error=ref(''), busy=ref(false)
const draft=ref({name:'Demo 对比',suite_id:'',baseline_agent_id:'',candidate_agent_id:'',mode:'benchmark',changed_fields:[] as string[],repetitions:1,timeout_seconds:60,order:'baseline_first',intervention:'adapter_default'})
const fields=ref(''), confirm=ref(false), paid=ref(false)
const preview=ref<{manifest:Record<string,unknown>;preview_sha256:string}|null>(null)
let frozenDraft: typeof draft.value | null=null
let requestKey=''
let timer:ReturnType<typeof setInterval>|undefined
async function api<T>(path:string,body?:unknown):Promise<T> {
  const response=await fetch('/api/v2/'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(20000)})
  const data=await response.json()
  if(!response.ok) throw new Error(`${response.status}: ${typeof data.detail==='string'?data.detail:JSON.stringify(data.detail)}`)
  return data as T
}
async function load() {
  try {
    const [a,s,e]=await Promise.all([api<Version[]>('agents'),api<Version[]>('benchmarks'),api<{id:string;name:string}[]>('experiments')])
    agents.value=a.filter(v=>v.status==='ready'); suites.value=s.filter(v=>v.status==='ready');experiments.value=e
    error.value=''
  } catch(e) {error.value=String(e)}
}
async function inspect() {
  busy.value=true;error.value='';confirm.value=false;preview.value=null
  try {
    const body={...draft.value,changed_fields:fields.value.split(',').map(s=>s.trim()).filter(Boolean)}
    preview.value=await api('experiments/preview',body)
    frozenDraft=structuredClone(body);requestKey=crypto.randomUUID()
  } catch(e){error.value=String(e)}finally{busy.value=false}
}
async function start() {
  if(!preview.value||!frozenDraft)return
  busy.value=true;error.value=''
  try {
    const result=await api<{id:string}>('experiments',{...frozenDraft,request_key:requestKey,preview_sha256:preview.value.preview_sha256,confirm_start:true,allow_model:paid.value})
    await open(result.id);await load();confirm.value=false
  }catch(e){error.value=String(e)}finally{busy.value=false}
}
async function open(id:string){
  try{detail.value=await api<Detail>('experiments/'+id);error.value=''}catch(e){error.value=String(e)}
}
async function cancel(){
  if(!detail.value)return
  busy.value=true
  try{await api('experiments/'+detail.value.id+'/cancel',{});await open(detail.value.id)}catch(e){error.value=String(e)}finally{busy.value=false}
}
onMounted(()=>{void load();timer=setInterval(()=>{if(detail.value&&!busy.value)void open(detail.value.id)},5000)})
onUnmounted(()=>clearInterval(timer))
</script>
<template>
  <section class="experiments-live">
    <h1>实验创建与批次运行</h1>
    <p>选择已校验的固定版本。预览不会执行；确认启动只入队。需要独立 platform_worker，Native 还需 worker 显式启用 --allow-model。</p>
    <p v-if="error" role="alert" class="error">{{error}}</p>
    <div class="form">
      <label>实验名称 <input v-model="draft.name" maxlength="100" /></label>
      <label>Benchmark Suite <select v-model="draft.suite_id"><option value="">请选择</option><option v-for="s in suites" :key="s.id" :value="s.id">{{s.name}} / {{s.version}}</option></select></label>
      <label>Baseline <select v-model="draft.baseline_agent_id"><option value="">请选择</option><option v-for="a in agents" :key="a.id" :value="a.id">{{a.name}} / {{a.version}}</option></select></label>
      <label>Candidate <select v-model="draft.candidate_agent_id"><option value="">请选择</option><option v-for="a in agents" :key="a.id" :value="a.id">{{a.name}} / {{a.version}}</option></select></label>
      <label>模式 <select v-model="draft.mode"><option value="benchmark">Benchmark · 可有多变量</option><option value="controlled">Controlled · 严格声明差异</option></select></label>
      <label>声明变化字段（逗号分隔）<input v-model="fields" placeholder="如 native.retrieval_policy；先用 benchmark 预览查看实际差异" /></label>
      <label>重复次数 <input v-model.number="draft.repetitions" type="number" min="1" max="5" /></label>
      <label>Agent 秒数预算 <input v-model.number="draft.timeout_seconds" type="number" min="1" max="3600" /></label>
      <label>计划顺序 <select v-model="draft.order"><option value="baseline_first">每个 Case 先 Baseline</option><option value="candidate_first">每个 Case 先 Candidate</option></select></label>
      <p>干预策略：Native 计划及每个候选人工审批；Process 无人工修改。审批等待可能改变实际开始顺序。每批最多 40 个 Run。</p>
      <button :disabled="busy" @click="inspect">生成冻结预览</button>
    </div>
    <article v-if="preview">
      <h2>启动前核对</h2>
      <p>预计 {{preview.manifest.run_count}} 个 Run；{{preview.manifest.needs_model?'包含可能付费的 Native 阶段':'无平台模型调用的 Process 运行'}}。</p>
      <p>实际配置差异：{{preview.manifest.changed_fields}}</p>
      <details><summary>完整冻结清单（启动使用此预览，修改表单后需重新预览）</summary><pre>{{JSON.stringify(preview.manifest,null,2)}}</pre></details>
      <label><input v-model="paid" type="checkbox" />明确允许此批 Native 模型/检索请求可能产生费用</label>
      <label><input v-model="confirm" type="checkbox" />已核对本次预览，确认入队执行</label>
      <button :disabled="busy||!confirm||(!!preview.manifest.needs_model&&!paid)" @click="start">确认启动预览中的实验</button>
    </article>
    <h2>已保存实验</h2><button :disabled="busy" @click="load">刷新列表</button>
    <p v-if="!experiments.length">暂无实验</p>
    <button v-for="e in experiments" :key="e.id" @click="open(e.id)">{{e.name}} · {{e.id.slice(0,8)}}</button>
    <article v-if="detail"><h2>实验 {{detail.id}}</h2>
      <p>状态：{{detail.status}}；取消已请求：{{detail.cancel_requested}}。每五秒刷新当前实验。</p>
      <p>清单 SHA256：{{detail.manifest_sha256}}</p>
      <button :disabled="busy||detail.cancel_requested||detail.status==='settled'" @click="cancel">取消整个实验的剩余执行</button>
      <table><thead><tr><th>顺序 / Case / 重复</th><th>分组</th><th>准备 / 生命周期</th><th>执行 / 验收</th><th>操作 / 错误</th></tr></thead>
        <tbody><tr v-for="m in detail.members" :key="m.id"><td>{{m.sequence}} / {{m.case_index+1}} / {{m.repetition}}</td><td>{{m.arm}}</td>
          <td>{{m.status}} / {{m.lifecycle??'尚未创建 Run'}}</td><td>{{m.execution_status??'未启动'}} / {{m.evaluation_outcome??'未评测'}}</td>
          <td><RouterLink v-if="m.run_id" :to="'/live/runs/'+m.run_id">详情 · 审批 · 单次取消</RouterLink>{{m.error_code}}</td></tr></tbody></table>
      <details><summary>历史冻结清单</summary><pre>{{JSON.stringify(detail.manifest,null,2)}}</pre></details>
    </article>
  </section>
</template>
<style scoped>
.experiments-live{max-width:1200px;margin:auto;padding:24px}.form{display:grid;gap:12px}label{display:block}input,select,button{padding:8px;margin:4px}select{max-width:90%}article{border:1px solid #ccd5df;padding:20px;margin:20px 0;border-radius:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:420px;overflow:auto}p{line-height:1.6;overflow-wrap:anywhere}table{width:100%;text-align:left}th,td{padding:10px;border-bottom:1px solid #ddd}.error{color:#a32722}button:disabled{opacity:.5}
</style>
