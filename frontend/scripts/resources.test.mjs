import assert from 'node:assert/strict'
import test from 'node:test'
import { canValidateCatalog, makeAgentConfiguration, parseCatalogConfiguration, catalogRequest } from '../src/data/catalog.ts'
import { inspectSavedReport } from '../src/data/saved-report.ts'
const entry={status:'registered',validation:null}
test('断连、忙碌、校验中与中断校验不可重跑',()=>{
 assert.equal(canValidateCatalog(entry,false,true),true)
 for(const [row,busy,connected] of [[entry,false,false],[entry,true,true],[{...entry,status:'validating'},false,true],[{...entry,validation:{status:'interrupted'}},false,true]]) assert.equal(canValidateCatalog(row,busy,connected),false)
})
test('辅助配置保持 process/native 独立，拒绝非字符串参数数组',()=>{
 const process=JSON.parse(makeAgentConfiguration('demo','v1','process','sha256:saved','["python","-I"]'))
 assert.deepEqual(process.process.argv,['python','-I']);assert.equal(process.native,undefined);assert.equal(process.process.trace,false)
 const native=JSON.parse(makeAgentConfiguration('demo','v1','native','','not-json'))
 assert.equal(native.process,undefined);assert.deepEqual(native.native,{retrieval_policy:'vector',max_tool_calls:4})
 for(const argv of ['{}','[1]','bad'])assert.throws(()=>makeAgentConfiguration('demo','v1','process','',argv),/字符串数组/)
})
test('配置大小按 UTF-8 字节计算，不截断或改写版本配置',()=>{
 const source='{"name":"中文","version":"v9","cases":[{"saved":true}]}'
 assert.deepEqual(parseCatalogConfiguration(source),JSON.parse(source))
 assert.throws(()=>parseCatalogConfiguration('中'.repeat(333334)),/1 MB/)
 assert.throws(()=>parseCatalogConfiguration('bad'),/JSON/)
})
test('校验保留 request_key 且失败不自动重试',async()=>{
 const original=globalThis.fetch;let calls=0
 globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/api/v2/agents/a1/validate');assert.equal(init.method,'POST');assert.deepEqual(JSON.parse(init.body),{request_key:'stable'});return new Response('{"detail":"conflict"}',{status:409,headers:{'content-type':'application/json'}})}
 try{await assert.rejects(catalogRequest('agents/a1/validate',{request_key:'stable'}),/409/);assert.equal(calls,1)}finally{globalThis.fetch=original}
})
test('报告保留原始字节；过大、错误来源与 hash 失败不可展示为通过',async()=>{
 const original=globalThis.fetch;const file=new Blob(['{"duplicate":1,"duplicate":2}']);let calls=0
 globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/api/v2/reports/inspect');assert.equal(init.body,file);assert.equal(init.method,'POST');return new Response('{"source":"uploaded_report_only","integrity":"hashes_consistent","report":{"experiment_id":"saved"}}',{headers:{'content-type':'application/json'}})}
 try{
 assert.equal((await inspectSavedReport(file)).report.experiment_id,'saved')
 await assert.rejects(inspectSavedReport(new Blob(['x'.repeat(10_000_001)])),/10 MB/);assert.equal(calls,1)
 globalThis.fetch=async()=>new Response('{"source":"live","integrity":"hashes_consistent","report":{}}',{headers:{'content-type':'application/json'}})
 await assert.rejects(inspectSavedReport(file),/来源或状态/)
 globalThis.fetch=async()=>new Response('{}',{status:422})
 await assert.rejects(inspectSavedReport(file),/hash 校验失败/)
 }finally{globalThis.fetch=original}
})
