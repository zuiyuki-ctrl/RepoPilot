<script setup lang="ts">
import type { TestRecord } from '../data/run-detail'
import { formatDate } from '../data/display'
import CodeBlock from './CodeBlock.vue'
defineProps<{ test: TestRecord | null }>()
</script>
<template>
  <template v-if="test">
    <dl class="metadata test-metadata">
      <dt>TestRun ID</dt><dd class="mono">{{ test.id }}</dd>
      <dt>执行状态</dt><dd>{{ test.status }}</dd>
      <dt>退出码 / 超时</dt><dd>{{ test.exitCode ?? '未记录' }} / {{ test.timedOut === null ? '未记录' : test.timedOut ? '是' : '否' }}</dd>
      <dt>开始 / 完成</dt><dd>{{ formatDate(test.startedAt) }} / {{ formatDate(test.completedAt) }}（日本时间）</dd>
      <dt>测试镜像</dt><dd class="mono">{{ test.image ?? '未记录' }}</dd>
    </dl>
    <p class="drawer-note">下面是保存的 pytest 输出，其中耗时仅表示 pytest 汇总耗时，不是 Agent 总耗时。未结构化采集的失败、跳过数量不推断为零。</p>
    <h3>stdout</h3><p v-if="test.stdoutTruncated" class="issue-note">输出已截断</p><CodeBlock :text="test.stdout" />
    <h3>stderr</h3><p v-if="test.stderrTruncated" class="issue-note">输出已截断</p><CodeBlock :text="test.stderr" />
    <p v-if="test.error" class="issue-note">{{ test.error }}</p>
    <details class="inline-details"><summary>测试配置与源码快照</summary><dl class="metadata"><dt>超时上限（秒）</dt><dd>{{ test.timeoutSeconds ?? '未记录' }}</dd><dt>源码快照 hash</dt><dd class="mono">{{ test.snapshotHash ?? '未记录' }}</dd></dl></details>
  </template>
  <p v-else class="quiet">测试记录未记录</p>
</template>
