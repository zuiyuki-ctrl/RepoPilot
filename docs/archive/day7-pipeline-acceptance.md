# 第七天：一对新运行验证采集链路

> 历史归档（2026-10-22）：这里记录一次特定验收及其结果，不代表当前环境或新一轮测试已通过。当前入口见 [项目 README](../../README.md)。

这次只验证平台链路，不评价策略总体优劣。使用 task-list/v1 的原提交和受保护测试，新建 Vector / Hybrid 各一条主运行。历史六条记录保留，不补写历史证据。

## 1. 更新环境并准备新运行

在项目根目录执行以下命令；迁移完成后重启正在运行的 API：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw '迁移失败，停止后续操作。' }
.\.venv\Scripts\python.exe -m alembic current
```

当前迁移 head 应为 `b691a9df8021`，增加 `TestRun.test_report`。用户尚未确认该数据库已升级。不要以离线测试通过替代真实迁移。

本轮新增定义 `evals/experiments/definitions/task-list-pipeline-v1.json`：必需测试共 8 个，修改前指定的 2 个分页筛选用例必须失败。名称已用本机临时副本的 pytest JUnit 核对；准备命令仍会在固定 Docker 镜像里重新取得真实基线，不复用本机结果。

以下命令会产生真实 Embedding 费用，并运行 Docker 基线测试；由用户执行。先做 Vector，完成后把 strategy 改为 hybrid 再做一遍，双方使用同一个定义。两条运行之间不要修改模型配置、Prompt、实现、用例、定义或镜像。若确需修复平台，保留失败记录并重新声明后续实验，不修改已冻结记录。

```powershell
$strategy = 'hybrid'
$experimentOutputDir = Join-Path 'D:\RepoPilot\reports\experiments' ('day7-task-list-' + $strategy + '-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m scripts.start_experiment --case evals/experiments/cases/task-list-v1.json --definition evals/experiments/definitions/task-list-pipeline-v1.json --source-path D:/RepoPilot-demo-tasklist --retrieval-policy "$strategy" --output-dir "$experimentOutputDir" --allow-embedding --allow-baseline-tests
if ($LASTEXITCODE -ne 0) { throw '准备失败，请保留 preparation.json 和终端输出，不继续规划。' }
$preparationFiles = @(Get-ChildItem -Path "$experimentOutputDir\*\preparation.json" -File)
if ($preparationFiles.Count -ne 1) { throw '准备记录不是唯一文件。' }
$experimentPreparation = $preparationFiles[0].FullName
Write-Output "本次准备文件：$experimentPreparation"
```

本轮不设置真实采用门槛或价格。单对链路验收不支持发布决策；没有价格时成本应保持未知。

## 2. 沿用既有审批与执行流程

每条运行继续使用现有 `plan_experiment → review_experiment → execute_experiment generate/apply/test/complete/report`。目标文件为 `task_list.py`。计划、候选分别由用户查看后批准，不自动批准；命令失败时保留证据，不直接重复启动任务。最终测试不通过就先检查原因，不为了得到绿灯而改固定测试。

终态后再运行 `export_retrieval_evidence --preparation "$experimentPreparation"`，保留这次最新导出及 report-result.json。规划阶段的证据可以保留，但不能替代全程观测。每个命令都用项目内 `.venv` 的 Python。

## 3. 汇总并核对页面

两条运行结束后，新建对比 manifest；runs 各填本次 preparation、终态报告 JSON（不是 report-result.json）和终态后的 evidence.json，role 均为 primary。使用实际路径，不按目录排序猜测最新报告。执行 `scripts.compare_experiments --manifest <清单路径>` 生成新报告；然后将 `frontend/comparison-source.json` 指向新 comparison.json，再运行前端 snapshots/build。这一步在拿到实际文件后完成，不提前写占位报告覆盖历史页面。

集中检查三件事：

- **可观测**：准备期 Embedding 单列；任务报告能关联研究、规划、候选和查询 Embedding 的调用、usage 与耗时。缺 usage 明示缺失；JUnit、TestRun ID、最终 Diff 可核对。
- **可评测/可实验**：修改前 2 失败、修改后必需 8 项通过时，声明的自动验收可以通过；若实际失败则如实保留。双方定义及已知条件一致，缺失供应商内部版本仍显示证据不足，不填假值。
- **决策/页面**：后端和页面结论一致，成本未知、未配置门槛及不可比原因可见。本轮即使两条验收都通过，严格配对/采用结论仍可能为 insufficient_evidence；这是边界的正确展示，不是要求把页面变绿。

完成后记录真实实验 ID、报告路径、缺失字段和页面核对结果，再更新七天计划。

## 本轮结果（2026-10-13）

以上命令流程已由用户执行，无需重跑。Vector / Hybrid 均完成，修改前指定 2 项失败、修改后 8 项通过，实验级自动验收双方为 passed。每条任务 37 个事件，7 次请求 usage 完整；任务 Token 分别为 18,014 / 19,097，准备期各 443 Token 单列。缺供应商内部版本、价格及采用门槛，严格配对与决策保持证据不足。

本轮清单：[day7-task-list-manifest.json](../../reports/comparisons/day7-task-list-manifest.json)。结果：[JSON](../../reports/comparisons/comparison_bbd13694363747b3a8e2742b0ad28567/comparison.json) / [Markdown](../../reports/comparisons/comparison_bbd13694363747b3a8e2742b0ad28567/comparison.md)。前端已经选择该报告，双方详情及轨迹关联一致，21 项快照测试及生产构建通过。

用户已反馈页面测试正常，本轮“总览 → 策略对比 → 运行详情”的目视确认待办关闭。此项依据用户实际测试反馈，助手没有另外执行浏览器验收。七天阶段的代表性链路验收完成，历史报告继续保留；下一阶段见 [PRD v2.0](../RepoPilot_PRD_v2.0.md)。
