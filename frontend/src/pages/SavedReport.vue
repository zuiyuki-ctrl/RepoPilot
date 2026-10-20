<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { ElButton, ElTabs, ElTabPane, ElEmpty } from 'element-plus'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/tabs/style/css'
import 'element-plus/es/components/tab-pane/style/css'
import 'element-plus/es/components/empty/style/css'
import { inspectSavedReport, type InspectedReport } from '../data/saved-report'
import '../resources.css'
const inspected=ref<InspectedReport|null>(null),error=ref(''),busy=ref(false),filename=ref(''),tab=ref('comparison')
const fileInput=ref<HTMLInputElement|null>(null)
let generation=0
const value=(item:unknown)=>item===null||item===undefined?'未记录':String(item)
const json=(item:unknown)=>item===null||item===undefined?'未记录':JSON.stringify(item,null,2)
async function select(event:Event){
  const input=event.target as HTMLInputElement, file=input.files?.[0]
  if(!file||busy.value)return
  const current=++generation
  input.value='';inspected.value=null;error.value='';filename.value=file.name;tab.value='comparison';busy.value=true
  try{const data=await inspectSavedReport(file);if(current===generation)inspected.value=data}
  catch(e){if(current===generation)error.value=e instanceof Error ? e.message : String(e)}finally{if(current===generation)busy.value=false}
}
onUnmounted(()=>{generation++})
</script>
<template>
  <div class="resource-page">
    <div class="ui-page-heading"><div><p class="ui-kicker">报告文件 · 只读核验</p><h1>报告文件</h1><p class="ui-page-description">阅读已下载的比较报告，与实时数据库和历史归档分别展示。</p></div><ElButton type="primary" :disabled="busy" :loading="busy" @click="fileInput?.click()">{{ busy ? '正在核验' : '选择 JSON 报告' }}</ElButton></div>
    <input ref="fileInput" type="file" accept=".json,application/json" :disabled="busy" class="resource-file-input" aria-label="选择待核验报告" @change="select" />
    <section class="ui-card resource-guide"><h2>文件将发送至当前 API 核验</h2><p>仅支持 RepoPilot 导出的原始 JSON 比较报告，最多 10 MB。接口校验结构与 hash，不写入数据库、不启动 Agent，也不重新计算历史成绩。</p><p>hash 一致只证明内容内部一致，不是可信签名，不能证明报告作者身份。报告中的内容只以文本展示。</p></section>
    <p v-if="busy" role="status" class="resource-notice">正在核验 {{ filename }}…</p><p v-if="error" role="alert" class="resource-alert">{{ error }}</p>
    <section v-if="inspected" class="ui-card resource-report"><div class="resource-toolbar"><div><h2>内容 hash 一致</h2><p>已选文件：{{ filename }} · 来源：已上传报告文件（uploaded_report_only）</p></div></div><p>实验 ID：<code>{{ value(inspected.report.experiment_id) }}</code></p><details><summary>报告身份与生成信息</summary><dl class="metadata"><dt>报告类型</dt><dd>{{ value(inspected.report.report_type) }}</dd><dt>报告版本</dt><dd>{{ value(inspected.report.schema_version) }}</dd><dt>导出时间（原始值）</dt><dd>{{ value(inspected.report.exported_at) }}</dd><dt>报告 SHA256</dt><dd class="mono">{{ value(inspected.report.report_sha256) }}</dd><dt>Manifest SHA256</dt><dd class="mono">{{ value(inspected.report.manifest_sha256) }}</dd></dl></details>
      <ElTabs v-model="tab"><ElTabPane label="比较结果" name="comparison"><p class="resource-note">保留报告原值，不重新计算评分或填补缺失字段。</p><pre class="resource-json">{{ json(inspected.report.comparison) }}</pre></ElTabPane><ElTabPane label="冻结配置" name="manifest"><pre class="resource-json">{{ json(inspected.report.manifest) }}</pre></ElTabPane><ElTabPane label="人工记录" name="reviews"><pre class="resource-json">{{ json(inspected.report.reviews) }}</pre></ElTabPane><ElTabPane label="完整报告" name="raw"><pre class="resource-json">{{ json(inspected.report) }}</pre></ElTabPane></ElTabs>
    </section>
    <section v-else-if="!busy" class="ui-card resource-report"><ElEmpty :description="error ? '报告尚未通过核验' : '选择已下载的 JSON 报告开始查看'" :image-size="64" /></section>
  </div>
</template>
