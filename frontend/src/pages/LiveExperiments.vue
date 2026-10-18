<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { type ExperimentComparison, type ExperimentReview, comparisonLabels, decisionLabels } from '../data/platform-comparison'
type Version = { id: string; name: string; version: string; status: string }
type Member = { id: string; sequence: number; case_index: number; repetition: number; arm: string; status: string; error_code: string | null;
  run_id: string | null; lifecycle: string | null; execution_status: string | null; evaluation_outcome: string | null }
type Detail = { id: string; status: string; manifest_sha256: string; manifest: Record<string, unknown>; members: Member[]; cancel_requested: boolean }
const agents=ref<Version[]>([]), suites=ref<Version[]>([])
const experiments=ref<{id:string;name:string}[]>([])
const detail=ref<Detail|null>(null), error=ref(''), busy=ref(false)
const comparison=ref<ExperimentComparison|null>(null), comparisonError=ref('')
const detailLoading=ref(false)
let selectionGeneration=0
const route=useRoute()
const draft=ref({name:'Demo 对比',suite_id:'',baseline_agent_id:'',candidate_agent_id:'',mode:'benchmark',changed_fields:[] as string[],repetitions:1,timeout_seconds:60,order:'baseline_first',intervention:'adapter_default',decision_policy:null as null | {version:number;min_pairs:number;min_cases:number;max_regressions:number;min_pass_delta_pp:number}})
const policyEnabled=ref(false)
const policy=ref({version:1,min_pairs:1,min_cases:1,max_regressions:0,min_pass_delta_pp:0})
const reviews=ref<ExperimentReview[]>([]), reviewError=ref('')
const reviewTarget=ref<ExperimentComparison|null>(null), reviewConfirmed=ref(false)
const reviewForm=ref({reviewer:'',action:'continue_experiment',rationale:''})
let reviewKey=''
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
    const body={...draft.value,decision_policy:policyEnabled.value?{...policy.value}:null,changed_fields:fields.value.split(',').map(s=>s.trim()).filter(Boolean)}
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
  const generation=++selectionGeneration
  detailLoading.value=true
  if(detail.value?.id!==id){detail.value=null;comparison.value=null;reviews.value=[];reviewTarget.value=null;reviewConfirmed.value=false}
  comparisonError.value=''
  const [record, compared, decisions]=await Promise.allSettled([
    api<Detail>('experiments/'+id),api<ExperimentComparison>('experiments/'+id+'/comparison'),
    api<ExperimentReview[]>('experiments/'+id+'/reviews'),
  ])
  if(generation!==selectionGeneration)return
  if(record.status==='fulfilled'){detail.value=record.value;error.value=''}else{error.value=String(record.reason)}
  if(compared.status==='fulfilled')comparison.value=compared.value
  else{comparison.value=null;comparisonError.value=String(compared.reason)}
  if(decisions.status==='fulfilled'){reviews.value=decisions.value;reviewError.value=''}
  else{reviews.value=[];reviewError.value=String(decisions.reason)}
  detailLoading.value=false
}
function beginReview(){
  if(!comparison.value)return
  reviewTarget.value=JSON.parse(JSON.stringify(comparison.value));reviewKey=crypto.randomUUID();reviewConfirmed.value=false
}
async function saveReview(){
  const target=reviewTarget.value
  if(!target||!reviewConfirmed.value||busy.value)return
  busy.value=true;error.value=''
  try{
    await api('experiments/'+target.experiment_id+'/reviews',{
      ...reviewForm.value,request_key:reviewKey,comparison_sha256:target.comparison_sha256,
    })
    reviewTarget.value=null;reviewConfirmed.value=false
    await open(target.experiment_id)
  }catch(e){error.value=String(e)}finally{busy.value=false}
}
async function cancel(){
  if(!detail.value)return
  busy.value=true
  try{await api('experiments/'+detail.value.id+'/cancel',{});await open(detail.value.id)}catch(e){error.value=String(e)}finally{busy.value=false}
}
async function download(format:'json'|'markdown'){
  if(!detail.value||busy.value)return
  const id=detail.value.id
  busy.value=true;error.value=''
  try{
    const response=await fetch(`/api/v2/experiments/${id}/export?format=${format}`,{cache:'no-store',signal:AbortSignal.timeout(30000)})
    if(!response.ok)throw new Error(`导出失败：HTTP ${response.status}`)
    const blob=await response.blob(),url=URL.createObjectURL(blob)
    const link=document.createElement('a');link.href=url
    link.download=response.headers.get('content-disposition')?.match(/filename="([^"]+)"/)?.[1]??`experiment-${id}.${format==='json'?'json':'md'}`
    document.body.appendChild(link);link.click();link.remove()
    window.setTimeout(()=>URL.revokeObjectURL(url),1000)
  }catch(e){error.value=String(e)}finally{busy.value=false}
}
onMounted(()=>{void load();if(typeof route.query.id==='string')void open(route.query.id);timer=setInterval(()=>{if(detail.value&&!busy.value&&!detailLoading.value)void open(detail.value.id)},5000)})
onUnmounted(()=>{clearInterval(timer);selectionGeneration++})
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
      <label><input v-model="policyEnabled" type="checkbox" />在启动前冻结本批质量门槛</label>
      <div v-if="policyEnabled">
        <label>最少可比对子 <input v-model.number="policy.min_pairs" type="number" min="1" max="20" /></label>
        <label>最少不同 Case <input v-model.number="policy.min_cases" type="number" min="1" max="20" /></label>
        <label>最多退化数 <input v-model.number="policy.max_regressions" type="number" min="0" max="20" /></label>
        <label>最低通过率差（百分点）<input v-model.number="policy.min_pass_delta_pp" type="number" min="-100" max="100" step="0.1" /></label>
        <p>需要全部计划对子可比，才能判定达到门槛。默认数值仅为填写起点，并非发布标准；当前只判断自动测试质量，不包含成本、Token 或延迟门槛。</p>
      </div>
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
      <h2>固定实验 · 成对比较</h2>
      <p v-if="comparisonError" role="alert" class="error">比较读取失败：{{comparisonError}}</p>
      <template v-if="comparison && comparison.experiment_id===detail.id">
        <p>模式：{{comparison.mode}} · 实际变化：{{comparison.changed_fields.join(', ') || '无'}}。
          同 Case、同重复次数配对，按平台独立验收结果比较；执行 completed 不等于通过。</p>
        <p v-if="comparison.integrity_issues.length" class="error">冻结证据存在问题，停止正向比较：{{comparison.integrity_issues.join(', ')}}</p>
        <p>可比 {{comparison.summary.comparable_pairs}} / 计划 {{comparison.summary.planned_pairs}} 对；
          可比对子通过率差：{{comparison.summary.paired_pass_delta_percentage_points===null?'未知':comparison.summary.paired_pass_delta_percentage_points.toFixed(1)+' 个百分点'}}。</p>
        <p><span v-for="(count,name) in comparison.summary.counts" :key="name">{{comparisonLabels[name] ?? name}}：{{count}}　</span></p>
        <table><thead><tr><th>组别</th><th>计划 / 成员 / 已启动</th><th>未启动 / 准备失败</th><th>已核验通过 / 已启动待定</th></tr></thead>
          <tbody><tr v-for="(group,arm) in comparison.groups" :key="arm"><td>{{arm}}</td>
            <td>{{group.planned}} / {{group.members}} / {{group.started}}</td><td>{{group.not_started}} / {{group.preparation_failed}}</td>
            <td>{{group.verified_passed??'未知'}} / {{group.unresolved_started}}</td></tr></tbody></table>
        <p>准备失败是未启动的子集。未完成、缺证据的已启动 Run 仍保留，不能从成功率分母中静默删除；上述百分点差只针对可比对子。</p>
        <table><thead><tr><th>Case / 重复</th><th>Baseline</th><th>Candidate</th><th>结论 / 原因</th></tr></thead>
          <tbody><tr v-for="pair in comparison.pairs" :key="`${pair.case_index}-${pair.repetition}`">
            <td>{{pair.case_id}} / {{pair.repetition}}</td>
            <td v-for="arm in (['baseline','candidate'] as const)" :key="arm">
              <template v-if="pair[arm]">
                <RouterLink v-if="pair[arm]?.run_id" :to="'/live/runs/'+pair[arm]?.run_id">Run 证据</RouterLink>
                <p>{{pair[arm]?.verified_outcome??'未核验'}} · {{pair[arm]?.evidence_status}}</p>
                <p>{{pair[arm]?.issues.join(', ')}}</p>
              </template><span v-else>缺失或重复成员</span>
            </td>
            <td>{{comparisonLabels[pair.classification]??pair.classification}}<p>{{pair.reasons.join(', ')}}</p></td>
          </tr></tbody></table>
        <p>这是本批固定自动测试的描述性结果。Benchmark 可以同时改变多个变量，不能把变化直接归因于检索策略。
          重复 fixture 不是独立的泛化证据；不自动给出发布或采纳建议。</p>
        <h2>资源比较 · 相同完整对子</h2>
        <p>仅使用质量可比且两边该指标都已知的同一组对子。Token 小计不等于运行总量；调用范围未确认完整时总量保持未知。
          墙钟时间包含人工等待和平台验收，不是纯模型延迟；人工等待未单独计量。</p>
        <table><thead><tr><th>指标</th><th>Baseline 均值</th><th>Candidate 均值</th><th>差值</th><th>完整对子 / 可比对子 / 计划对子</th></tr></thead>
          <tbody><tr v-for="(metric,name) in comparison.resource_comparison.metrics" :key="name"><td>{{name==='total_tokens'?'总 Token':'墙钟时间（毫秒）'}}</td>
            <td>{{metric.baseline_mean??'未知'}}</td><td>{{metric.candidate_mean??'未知'}}</td><td>{{metric.delta??'未知'}}</td>
            <td>{{metric.valid_pairs}} / {{metric.eligible_pairs}} / {{metric.planned_pairs}}</td></tr></tbody></table>
        <p>费用：未知（未保存历史价格快照，不使用当前价格补算）。资源指标暂不参与质量门槛。</p>
        <details><summary>各 Run 已知用量小计、覆盖情况及事件引用</summary><pre>{{JSON.stringify(comparison.resource_comparison.runs,null,2)}}</pre></details>
        <h2>系统门槛判定</h2>
        <p>{{decisionLabels[comparison.decision.status]??comparison.decision.status}} · {{comparison.decision.reason}}</p>
        <p>仅表示本批自动测试质量是否符合预先声明的规则，不表示可以直接发布。旧实验没有冻结门槛时保持未评估。</p>
        <table v-if="comparison.decision.checks.length"><thead><tr><th>检查项</th><th>实际 / 门槛</th><th>满足</th></tr></thead>
          <tbody><tr v-for="check in comparison.decision.checks" :key="check.name"><td>{{check.name}}</td><td>{{check.actual}} / {{check.required}}</td><td>{{check.passed?'是':'否'}}</td></tr></tbody></table>
        <h2>独立人工决定</h2>
        <p>本地操作者自填身份，不是登录认证。人工决定不改变 Run 成绩；可以与系统判定不同，但必须记录理由。每次保存追加一条历史记录。</p>
        <button :disabled="busy||detailLoading" @click="beginReview">核对当前比较并填写决定</button>
        <section v-if="reviewTarget">
          <p>本次依据：{{reviewTarget.comparison_sha256}} · {{decisionLabels[reviewTarget.decision.status]}}</p>
          <p v-if="reviewTarget.comparison_sha256!==comparison.comparison_sha256" class="error">比较已变化，请重新核对；旧表单不能覆盖新证据。</p>
          <label>操作者 <input v-model="reviewForm.reviewer" maxlength="100" /></label>
          <label>决定 <select v-model="reviewForm.action"><option value="adopt_candidate">采用 Candidate</option><option value="keep_baseline">保留 Baseline</option><option value="continue_experiment">继续实验</option></select></label>
          <label>理由 <textarea v-model="reviewForm.rationale" maxlength="2000" /></label>
          <label><input v-model="reviewConfirmed" type="checkbox" />已核对上述比较与局限，确认记录我的决定</label>
          <button :disabled="busy||!reviewConfirmed||!reviewForm.reviewer.trim()||!reviewForm.rationale.trim()||reviewTarget.comparison_sha256!==comparison.comparison_sha256" @click="saveReview">保存独立人工决定</button>
        </section>
        <p v-if="reviewError" class="error">人工记录读取失败：{{reviewError}}</p>
        <p>最近 20 条人工决定；每条保留当时快照，当前证据变化不会改写旧记录。</p>
        <details v-for="review in reviews" :key="review.id"><summary>{{review.created_at}} · {{review.reviewer}} · {{review.action}} · {{review.comparison_sha256===comparison.comparison_sha256?'对应当前比较':'历史比较'}}</summary>
          <p>{{review.rationale}}</p><p>当时系统判定：{{decisionLabels[review.machine_decision.status]??review.machine_decision.status}}</p>
          <pre>{{JSON.stringify(review.snapshot,null,2)}}</pre>
        </details>
        <p>比较快照 hash：{{comparison.comparison_sha256}} · 读取时间：{{comparison.observed_at}}</p>
        <details><summary>比较证据引用（Evaluation / TestRun ID）</summary><pre>{{JSON.stringify(comparison.pairs,null,2)}}</pre></details>
        <h2>导出比较报告</h2>
        <p>导出时从同一数据库快照读取清单、比较、资源和人工历史；不重新读取源码工作区。
          每次下载是独立时点，请保存文件。此报告不包含完整原始 Trace、Diff 或源码包。</p>
        <button :disabled="busy" @click="download('json')">下载 JSON</button>
        <button :disabled="busy" @click="download('markdown')">下载 Markdown</button>
      </template>
    </article>
  </section>
</template>
<style scoped>
.experiments-live{max-width:1200px;margin:auto;padding:24px}.form{display:grid;gap:12px}label{display:block}input,select,button{padding:8px;margin:4px}select{max-width:90%}article{border:1px solid #ccd5df;padding:20px;margin:20px 0;border-radius:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:420px;overflow:auto}p{line-height:1.6;overflow-wrap:anywhere}table{width:100%;text-align:left}th,td{padding:10px;border-bottom:1px solid #ddd}.error{color:#a32722}button:disabled{opacity:.5}
</style>
