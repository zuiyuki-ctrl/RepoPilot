import { readdir, readFile, mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { buildRunDetail } from './run-detail.mjs'

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repo = path.resolve(frontend, '..')
const root = path.join(repo, 'reports', 'experiments')

// 只读取这几种业务快照；不会复制整个 reports 或读取环境配置。
const allowed = /^(preparation\.json|plan_inspection_.+\.json|candidate\.json|apply-result\.json|test-result\.json|complete-result\.json|task_.+\.json|evidence\.json)$/

async function collect(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = []
  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    const full = path.join(directory, entry.name)
    if (entry.isDirectory()) files.push(...await collect(full))
    else if (entry.isFile() && allowed.test(entry.name)) files.push(full)
  }
  return files
}

export function parsePytestSummary(stdout) {
  if (typeof stdout !== 'string') return null
  // 只接受 pytest 的整行汇总，避免把日志中间的文字当作统计。
  const line = stdout.split(/\r?\n/).reverse().find(value => /^(?:=+\s*)?(?:\d+ (?:passed|failed|skipped|errors?|xfailed|xpassed|deselected)(?:, )?)+ in \d+(?:\.\d+)?s(?:\s*=+)?$/.test(value.trim()))
  return line?.trim() ?? null
}

function timestamp(value) {
  return value.exported_at ?? value.inspected_at ?? value.created_at ?? value.task?.completed_at ?? value.test_run?.completed_at ?? value.test_run?.started_at ?? null
}

function latest(records) {
  return [...records].sort((a, b) => {
    const delta = Date.parse(timestamp(b.data) ?? '') - Date.parse(timestamp(a.data) ?? '')
    return (Number.isFinite(delta) && delta !== 0) ? delta : a.source.localeCompare(b.source)
  })[0]
}

export function buildHistory(records, generatedAt = new Date().toISOString()) {
  const preparations = records.filter(r => path.basename(r.source) === 'preparation.json')
  const experimentIds = new Set()
  const details = {}
  const runs = preparations.map(record => {
    const p = record.data
    if (!p.experiment_id || experimentIds.has(p.experiment_id)) throw new Error(`实验 ID 缺失或重复：${record.source}`)
    experimentIds.add(p.experiment_id)
    const directory = record.source.slice(0, record.source.lastIndexOf('/'))
    const artifacts = records.filter(r => r.source.startsWith(directory + '/') && r !== record)
    const issues = []
    const usable = artifacts.filter(r => {
      const d = r.data
      const taskId = d.task_id ?? d.task?.id ?? d.candidate?.task_id
      const experimentId = d.experiment_id ?? d.experiment?.experiment_id
      const repositoryId = d.task?.repository_id ?? d.candidate?.repository_id
      if ((taskId && taskId !== p.task_id) || (experimentId && experimentId !== p.experiment_id) || (repositoryId && repositoryId !== p.repository_id)) {
        issues.push(`关联不一致，未用于汇总：${r.source}`)
        return false
      }
      if (d.test_run && d.test_run.task_id !== p.task_id) {
        issues.push(`TestRun 不属于当前任务，未用于汇总：${r.source}`)
        return false
      }
      return true
    })
    const report = latest(usable.filter(r => /^task_.+\.json$/.test(path.basename(r.source))))
    const inspection = latest(usable.filter(r => path.basename(r.source).startsWith('plan_inspection_')))
    const evidence = latest(usable.filter(r => path.basename(r.source) === 'evidence.json'))
    details[p.experiment_id] = buildRunDetail(record, usable, report, evidence)
    const candidates = usable.filter(r => path.basename(r.source) === 'candidate.json')
    const applied = usable.some(r => path.basename(r.source) === 'apply-result.json')
    const task = report?.data.task ?? inspection?.data.task
    const testResults = usable.filter(r => path.basename(r.source) === 'test-result.json')
    const testResult = latest(testResults)
    const test = report?.data.test_run ?? testResult?.data.test_run
    const testSource = report?.data.test_run ? report : testResult
    if (test && testResults.some(r => (r.data.test_run_id ?? r.data.test_run?.id) && (r.data.test_run_id ?? r.data.test_run?.id) !== test.id)) {
      issues.push('存在不同 TestRun 的测试结果；总览仅使用终态报告关联的 TestRun。')
    }
    return {
      experimentId: p.experiment_id,
      taskId: p.task_id ?? null,
      repositoryId: p.repository_id ?? null,
      caseId: p.case.case_id,
      caseVersion: p.case.case_version,
      goal: p.case.user_request,
      strategy: p.run_config.retrieval_policy,
      config: { maxToolCalls: p.run_config.max_tool_calls ?? null, maxRetries: task?.max_retries ?? null },
      commit: p.case.repository_commit,
      createdAt: p.created_at,
      preparationStatus: p.status,
      preparationStage: p.stage,
      preparationError: p.error_type ?? null,
      taskStatus: task?.status ?? null,
      taskStatusSource: report?.source ?? inspection?.source ?? null,
      progress: report ? 'terminal_report' : test ? 'tested' : applied ? 'applied' : candidates.length ? 'candidate_saved' : inspection ? 'plan_snapshot' : 'preparation',
      candidateCount: candidates.length,
      retryCount: task?.retry_count ?? null,
      test: test ? {
        id: test.id,
        status: test.status,
        exitCode: test.exit_code,
        timedOut: test.timed_out,
        passed: test.status === 'finished' && test.exit_code === 0 && test.timed_out === false,
        summary: parsePytestSummary(test.stdout),
        startedAt: test.started_at,
        completedAt: test.completed_at,
        snapshotHash: test.snapshot_hash ?? null,
        image: test.image,
        source: testSource.source,
      } : null,
      evidence: evidence ? {
        status: evidence.data.trace_status,
        exportedAt: evidence.data.exported_at,
        lastSequence: evidence.data.last_sequence,
        fetchedEventCount: evidence.data.event_count,
        savedEventCount: evidence.data.events?.length ?? null,
        taskStatusAtExport: evidence.data.task_snapshot_before_event_fetch?.status ?? null,
        warnings: evidence.data.warnings ?? [],
        source: evidence.source,
      } : null,
      reportSource: report?.source ?? null,
      issues,
      // 来源清单保留重复导出；仅白名单字段进入浏览器，不含本机工作区路径和原始大段日志。
      sources: [record, ...artifacts].map(r => ({ path: r.source, timestamp: timestamp(r.data), selected: [record, report, inspection, evidence, testSource, ...candidates, ...usable.filter(a => path.basename(a.source) === 'apply-result.json')].includes(r) })),
    }
  })
  return { schemaVersion: 1, generatedAt, sourceRoot: 'reports/experiments', runs, details }
}

async function main() {
  const records = []
  for (const file of await collect(root)) {
    records.push({ source: path.relative(repo, file).split(path.sep).join('/'), data: JSON.parse(await readFile(file, 'utf8')) })
  }
  const { details, ...history } = buildHistory(records)
  const output = path.join(frontend, 'public', 'data')
  await mkdir(output, { recursive: true })
  await writeFile(path.join(output, 'history.json'), JSON.stringify(history, null, 2) + '\n')
  await mkdir(path.join(output, 'runs'), { recursive: true })
  for (const [id, detail] of Object.entries(details)) {
    if (!/^[0-9a-f-]{36}$/i.test(id)) throw new Error('不合法的实验文件 ID')
    await writeFile(path.join(output, 'runs', `${id}.json`), JSON.stringify(detail, null, 2) + '\n')
  }
  console.log(`历史快照已整理：${history.runs.filter(r => r.taskId).length} 条任务运行，${history.runs.filter(r => !r.taskId).length} 条准备记录。`)
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main()
