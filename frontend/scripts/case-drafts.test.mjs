import assert from 'node:assert/strict'
import test from 'node:test'
import { activeDraft, canConfirmDraft, parseTestItems, buildDraftSelection } from '../src/data/caseDrafts.ts'

const input = { repositoryId:'repo',commit:'a'.repeat(40),sourceFiles:['logic.py'],testFiles:['tests/test_logic.py'],
  image:'sha256:'+'a'.repeat(64),background:'背景',tests:'tests.test_logic::test_value[param::one]',failed:['tests.test_logic::test_value[param::one]'] }
test('保留用户固定提交、完整参数化测试名称和失败声明',()=>{
  const result=buildDraftSelection(input)
  assert.equal(result.repository_commit,input.commit)
  assert.equal(result.acceptance.baseline_failure_tests[0].name,'test_value[param::one]')
  assert.deepEqual(result.acceptance.required_tests,result.acceptance.baseline_failure_tests)
  assert.equal(result.run_id,undefined)
})
test('拒绝缺失测试、重复项、失效失败选择、重叠路径和可变镜像',()=>{
  for(const patch of [{tests:''},{failed:[]},{failed:['missing']},{sourceFiles:input.testFiles},{image:'tag:latest'}]) {
    assert.throws(()=>buildDraftSelection({...input,...patch}))
  }
  assert.throws(()=>parseTestItems('tests.m::test_x\ntests.m::test_x'))
  assert.throws(()=>parseTestItems('missing separator'))
})
test('仅当前已保存、基线通过的 ready 草稿可确认',()=>{
  const ready={status:'ready',baseline:{passed:true},text:{title:'x'}}
  assert.equal(canConfirmDraft(ready,false,false),true)
  for(const status of ['queued','validating','generating','failed','discarded','confirmed','interrupted']) {
    assert.equal(canConfirmDraft({...ready,status},false,false),false)
  }
  assert.equal(canConfirmDraft(ready,true,false),false)
  assert.equal(canConfirmDraft(ready,false,true),false)
  assert.equal(canConfirmDraft({...ready,baseline:null},false,false),false)
  assert.equal(activeDraft({status:'generating'}),true)
  assert.equal(activeDraft(ready),false)
})
