import { readFile, writeFile, mkdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { redactText } from './run-detail.mjs'

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repo = path.resolve(frontend, '..')
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// 只投影页面需要的字段，不把原报告中的本机绝对路径、源码和日志整体发布。
export function buildComparisonSnapshot(report, source, history) {
  if (report.schema_version !== 1 || !Array.isArray(report.pairs) || !Array.isArray(report.additional_attempts)) throw new Error('不支持的对照报告')
  const seen = new Set()
  function row(run, caseId, version, strategy) {
    if (!uuid.test(run.experiment_id) || seen.has(run.experiment_id)) throw new Error('实验 ID 缺失或重复')
    seen.add(run.experiment_id)
    if (run.case.case_id !== caseId || run.case.case_version !== version || run.strategy !== strategy) throw new Error('对照运行与用例/策略不一致')
    const found = history.runs.find(item => item.experimentId === run.experiment_id)
    const normalize = value => value?.replaceAll('\\', '/')
    const selectedReport = normalize(run.artifacts?.report?.path)
    const detailMatches = Boolean(found && found.taskId === run.task_id && found.strategy === strategy
      && found.test?.id === run.test?.id && found.reportSource && selectedReport?.endsWith('/' + found.reportSource))
    const detailEvidenceMatches = Boolean(detailMatches && found.evidence?.source
      && normalize(run.artifacts?.evidence?.path)?.endsWith('/' + found.evidence.source))
    return {
      experimentId: run.experiment_id, taskId: run.task_id, strategy, status: run.status,
      retryCount: run.retry_count, stage: run.preparation_stage, errorType: run.preparation_error_type,
      completionSequence: run.completion_event_sequence, detailMatches, detailEvidenceMatches,
      test: run.test ? { id: run.test.id, exitCode: run.test.exit_code, timedOut: run.test.timed_out,
        passed: run.test.process_passed, image: run.test.image } : null,
      traceStatus: run.retrieval?.trace_status ?? null,
      traceLastSequence: run.retrieval?.snapshot_last_sequence ?? null,
      warnings: [...(run.retrieval?.warnings ?? []), ...(run.retrieval?.association_warnings ?? [])].map(redactText),
      queries: run.retrieval?.queries.map(query => ({ query: redactText(query.query), sequence: query.event_sequence,
        diagnostics: query.diagnostics ? Object.fromEntries(['vector_candidate_count', 'keyword_candidate_count', 'overlap_count', 'final_keyword_hit_count']
          .map(key => [key, query.diagnostics[key] ?? null])) : null, hits: query.hits.map(hit => ({ rank: hit.rank,
          filePath: redactText(hit.file_path), symbol: redactText(hit.symbol_name),
          vectorRank: hit.vector_rank ?? null, keywordRank: hit.keyword_rank ?? null })) })) ?? [],
      contexts: run.retrieval?.contexts.map(context => ({ tool: context.tool_name, sequence: context.event_sequence,
        disposition: context.disposition, chars: context.content_chars, modelAttempts: context.model_calls.length })) ?? [],
      artifactHashes: Object.entries(run.artifacts ?? {}).filter(([, artifact]) => artifact)
        .map(([name, artifact]) => ({ name, sha256: artifact.sha256 })),
    }
  }
  return { schemaVersion: 1, generatedAt: report.generated_at, source,
    limitations: report.limitations.map(redactText),
    pairs: report.pairs.map(pair => ({ caseId: pair.case_id, caseVersion: pair.case_version,
      differences: pair.recorded_condition_differences, complete: pair.pair_complete,
      runs: ['vector', 'hybrid'].map(strategy => pair.runs[strategy]
        ? row(pair.runs[strategy], pair.case_id, pair.case_version, strategy) : null) })),
    additional: report.additional_attempts.map(run => ({ caseId: run.case.case_id,
      ...row(run, run.case.case_id, run.case.case_version, run.strategy) })),
  }
}

async function main() {
  const config = JSON.parse(await readFile(path.join(frontend, 'comparison-source.json'), 'utf8'))
  if (typeof config.report !== 'string' || !/^reports\/comparisons\/comparison_[a-f0-9]+\/comparison\.json$/.test(config.report)) throw new Error('对照来源必须是 reports/comparisons 下明确指定的报告')
  const report = JSON.parse(await readFile(path.join(repo, config.report), 'utf8'))
  const history = JSON.parse(await readFile(path.join(frontend, 'public/data/history.json'), 'utf8'))
  const snapshot = buildComparisonSnapshot(report, config.report, history)
  await mkdir(path.join(frontend, 'public/data'), { recursive: true })
  await writeFile(path.join(frontend, 'public/data/comparison.json'), JSON.stringify(snapshot, null, 2) + '\n')
  console.log(`策略对照快照已整理：${snapshot.pairs.length} 个用例，${snapshot.additional.length} 条额外记录。`)
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode = 1 })
}
