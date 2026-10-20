import assert from 'node:assert/strict'
import test from 'node:test'
import { canDecideRun, canCancelRun, readLive } from '../src/data/platform-runs.ts'
const run = { id:'r1', version:4, lifecycle:'awaiting_input' }
const control = { cancel_requested:false, checkpoint:{ run_id:'r1', run_version:4, decision:null } }
test('仅当前等待输入的未决定检查点可审批', () => {
 assert.equal(canDecideRun(run, control, false), true)
 for (const lifecycle of ['running','finished','interrupted','evaluating']) assert.equal(canDecideRun({...run,lifecycle},control,false),false)
 for (const checkpoint of [{...control.checkpoint, decision:'approved'},{...control.checkpoint,run_version:3},{...control.checkpoint,run_id:'other'}]) assert.equal(canDecideRun(run,{...control,checkpoint},false),false)
 assert.equal(canDecideRun(run,{...control,cancel_requested:true},false),false)
 assert.equal(canDecideRun(run,control,true),false)
 assert.equal(canDecideRun(run,null,false),false)
})
test('取消保留终态、验收中及重复请求约束', () => {
 assert.equal(canCancelRun(run,control,false),true)
 for (const lifecycle of ['finished','interrupted','evaluating']) assert.equal(canCancelRun({...run,lifecycle},control,false),false)
 assert.equal(canCancelRun(run,{...control,cancel_requested:true},false),false)
 assert.equal(canCancelRun(run,control,true),false)
 assert.equal(canCancelRun(null,control,false),false)
 assert.equal(canCancelRun(run,null,false),false)
})
test('读取与审批请求保留 GET/POST、版本和 hash，409 不自动重试',async () => {
 globalThis.window = {setTimeout,clearTimeout}
 const original = globalThis.fetch
 const calls=[]
 globalThis.fetch=async (url,init)=>{calls.push({url,init});return new Response('{}',{headers:{'content-type':'application/json'}})}
 try {
 await readLive('/r1/trace?after_sequence=50&through_sequence=100&limit=50')
 assert.equal(calls[0].init.method,undefined)
 assert.match(calls[0].url,/through_sequence=100/)
 const body={expected_version:4,payload_sha256:'saved-hash',decision:'approved',comment:'核对'}
 await readLive('/r1/checkpoints/c1/decision',body)
 assert.equal(calls[1].init.method,'POST');assert.deepEqual(JSON.parse(calls[1].init.body),body)
 let attempts=0
 globalThis.fetch=async()=>{attempts++;return new Response('{}',{status:409})}
 await assert.rejects(readLive('/r1/cancel',{expected_version:4}),/版本已变化/)
 assert.equal(attempts,1)
 } finally {globalThis.fetch=original;delete globalThis.window}
})
