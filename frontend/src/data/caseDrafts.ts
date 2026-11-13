export interface RequiredTest { classname: string; name: string }
export interface DraftText { title: string; user_request: string; editable_files: string[] }
export interface DraftSelection {
  repository_id: string; repository_commit: string; source_files: string[]; protected_test_files: string[]
  test_image: string; background: string
  acceptance: { version: string; required_tests: RequiredTest[]; baseline_failure_tests: RequiredTest[]; manual_criteria: string[] }
}
export interface DraftPreview {
  preview_sha256: string; snapshot_sha256: string; model: { model: string; destination: string }
  files: { path: string; bytes: number; sha256: string }[]; contents: Record<string, string>
}
export interface CaseDraft {
  id: string; status: string; revision: number; selection: DraftSelection; preview: DraftPreview
  text: DraftText | null; baseline: { passed: boolean; reason: string; [key: string]: unknown } | null
  error: { reason: string; message: string } | null; confirmed_benchmark_id: string | null
}
export const draftLabels: Record<string, string> = {
  queued: '等待 worker（需 --allow-model）', validating: '正在校验失败基线', generating: '正在生成题面',
  ready: '基线通过 · 等待人工确认', failed: '失败 · 未生成可用 Case', interrupted: '中断 · 需显式恢复',
  discarded: '已丢弃', confirmed: '已确认注册 · 可用性请查看 Benchmark 校验状态',
}
export function activeDraft(draft: CaseDraft | null): boolean {
  return !!draft && ['queued', 'validating', 'generating'].includes(draft.status)
}
export function canConfirmDraft(draft: CaseDraft | null, dirty: boolean, busy: boolean): boolean {
  return !!draft && draft.status === 'ready' && draft.baseline?.passed === true && !!draft.text && !dirty && !busy
}
export function parseTestItems(input: string): RequiredTest[] {
  const tests = input.split('\n').map(s => s.trim()).filter(Boolean).map(line => {
    const index = line.indexOf('::')
    if (index <= 0 || index === line.length - 2) throw new Error('每行使用 classname::测试名称（参数化名称需完整），例如 tests.test_task_list::test_filter[open]')
    return { classname: line.slice(0, index), name: line.slice(index + 2) }
  })
  if (!tests.length || tests.length > 200) throw new Error('请声明 1–200 个验收测试项。')
  if (new Set(tests.map(testKey)).size !== tests.length) throw new Error('测试项不能重复。')
  return tests
}
export function testKey(test: RequiredTest): string { return `${test.classname}::${test.name}` }
export function buildDraftSelection(input: {
  repositoryId: string; commit: string; sourceFiles: string[]; testFiles: string[]; image: string
  background: string; tests: string; failed: string[]
}): DraftSelection {
  const tests = parseTestItems(input.tests)
  if (!input.repositoryId || !/^[a-f0-9]{40}$/.test(input.commit)) throw new Error('请先选择已登记的固定提交。')
  if (!/^sha256:[a-f0-9]{64}$/.test(input.image)) throw new Error('请填写本地测试镜像的完整 sha256 ID，不能使用可变 tag。')
  if (!input.sourceFiles.length || !input.testFiles.length) throw new Error('请选择源码和受保护测试文件。')
  if (input.sourceFiles.some(p => input.testFiles.includes(p))) throw new Error('源码与受保护测试不能重叠。')
  const failed = tests.filter(t => input.failed.includes(testKey(t)))
  if (!failed.length || failed.length !== new Set(input.failed).size) throw new Error('请从当前验收测试中选择预期失败项。')
  return { repository_id: input.repositoryId, repository_commit: input.commit,
    source_files: [...input.sourceFiles], protected_test_files: [...input.testFiles],
    test_image: input.image, background: input.background,
    acceptance: { version: 'v1', required_tests: tests, baseline_failure_tests: failed, manual_criteria: [] } }
}
