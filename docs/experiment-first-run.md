# 首次真实实验：task-list / Vector

本轮只运行一个固定用例、一种策略。模型与 Embedding 调用由用户执行；候选生成后检查内容，再明确应用。不修改验收测试或手动补充修复答案。以下命令在 `D:\RepoPilot` 的 PowerShell 中执行，使用项目虚拟环境，不依赖是否已经激活。

2026-10-08 只读预检：样例仓库 `D:\RepoPilot-demo-tasklist` 工作树干净，HEAD 为 `4629a3a98cb62c989ed4e1e67be9514703b3d346`，源码与测试均被 Git 跟踪；数据库容器健康，`repopilot-pytest:py311` 镜像存在。数据库迁移当前为 `352b3ea56d2f`，尚缺 `fde182df4042`（agent_tasks.run_config）。此记录不代表之后的环境状态，也不代表实际测试通过。

## 第一段：准备与规划，停在人工审批前

先补齐迁移。此命令使用本机配置连接数据库，不要把配置或密钥贴到聊天中：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw '迁移失败，停止实验' }
.\.venv\Scripts\python.exe -m alembic current
```

预期迁移到 `fde182df4042`。另开一个 PowerShell 终端启动当前项目服务，保留终端查看日志；已经在该端口运行本项目最新代码时不用重复启动：

```powershell
Set-Location D:\RepoPilot
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000
```

回到操作终端，先只读检查样例，再准备独立实验。后一个命令会调用真实 Embedding：

```powershell
.\.venv\Scripts\python.exe -m scripts.prepare_experiment --case evals/experiments/cases/task-list-v1.json --source-path D:/RepoPilot-demo-tasklist
if ($LASTEXITCODE -ne 0) { throw '样例检查失败，停止实验' }
.\.venv\Scripts\python.exe -m scripts.start_experiment --case evals/experiments/cases/task-list-v1.json --source-path D:/RepoPilot-demo-tasklist --retrieval-policy vector --allow-embedding
if ($LASTEXITCODE -ne 0) { throw '准备失败，保留错误记录，不重复运行后续命令' }
```

从输出复制本次“记录文件”路径，填入变量。不要自动选择目录中“最新文件”，避免拿到其他实验：

```powershell
$experimentPreparation = Read-Host 'D:\RepoPilot\reports\experiments\1050c45d-458e-41bf-a4d7-cd5ce1f897b2\preparation.json'
.\.venv\Scripts\python.exe -m scripts.plan_experiment --preparation "$experimentPreparation" --run --allow-model
```

此命令会真实调用规划模型和检索服务。预期状态 `awaiting_review`、范围 `valid`、越界文件 `[]`。打开输出中的计划检查 JSON，检查 `task.result.plan` 是否针对本次需求且只修改 `task_list.py`。范围检查不等于计划语义正确。此处停下检查，不把后两段无条件连着执行。

## 第二段：明确批准、生成候选，再明确应用

仅在认可刚才的计划后提交批准：

```powershell
.\.venv\Scripts\python.exe -m scripts.review_experiment --preparation "$experimentPreparation" --decision approved --comment '已检查计划范围和任务目标，同意执行本次固定用例'
if ($LASTEXITCODE -ne 0) { throw '审批未确认成功，先查询任务状态' }
.\.venv\Scripts\python.exe -m scripts.execute_experiment generate --preparation "$experimentPreparation" --file-path task_list.py --allow-model
if ($LASTEXITCODE -ne 0) { throw '候选未确认保存成功，停止并检查操作记录' }
```

generate 会真实调用模型，但只保存候选。打开输出的 `candidate.json`，检查 `candidate.proposal.content` 是完整 Python 文件，目标路径正确、未修改测试。不要手工修正候选后作为未干预实验应用；有问题先保留记录并反馈。

认可候选后，将本次候选文件路径填入变量并应用：

```powershell
$experimentCandidate = Read-Host 'D:\RepoPilot\reports\experiments\1050c45d-458e-41bf-a4d7-cd5ce1f897b2\preparation.json'
.\.venv\Scripts\python.exe -m scripts.execute_experiment apply --preparation "$experimentPreparation" --candidate "$experimentCandidate" --confirm-apply
if ($LASTEXITCODE -ne 0) { throw '应用未确认成功，停止并查询实际写入状态' }
```

写入目标是实验独立工作区，不是样例源仓库。服务会核对实验关联、批准计划、测试基线和原文件 hash；发生 hash 冲突不能通过手动改 hash 绕过。

## 第三段：测试，按本次结果完成并导出

```powershell
.\.venv\Scripts\python.exe -m scripts.execute_experiment test --preparation "$experimentPreparation"
$experimentTestExit = $LASTEXITCODE
if ($experimentTestExit -ne 0) { throw "测试阶段未通过（退出码 $experimentTestExit），保留记录，不执行 complete" }
```

退出码 0 表示通过；1 表示测试未通过但结果已保存；2 表示操作异常。不要把“测试未通过”自行改写为任务已经 failed，当前首轮正常测试结束后任务仍可处于 executing。

通过后复制本次打印的测试运行 ID，不选旧记录：

```powershell
$experimentTestRun = Read-Host '54a99c2d-aaa0-4364-871f-89efc2fdf319'
.\.venv\Scripts\python.exe -m scripts.execute_experiment complete --preparation "$experimentPreparation" --test-run-id "$experimentTestRun"
if ($LASTEXITCODE -ne 0) { throw '完成未确认成功，停止并查询状态' }
.\.venv\Scripts\python.exe -m scripts.execute_experiment report --preparation "$experimentPreparation"
```

保留本次 `preparation.json` 所在目录，包括 `operations/` 内的请求、候选、结果及错误记录。验收看三件事：配置为 vector 且任务/仓库归属一致；本次 TestRun 对应实际测试结果；历史报告的任务、TestRun 和最终 Diff 一致。真实结果不预设成功。

## 中断后的处理

- 规划或审批超时：不重发写请求；用下面的命令只读刷新任务状态，再决定后续操作：

  ```powershell
  .\.venv\Scripts\python.exe -m scripts.plan_experiment --preparation "$experimentPreparation"
  ```

- apply / test / complete 报错，尤其本地结果保存失败：先看本次操作目录的 `request.json`、`error.json`，再查询该任务的 events / test-runs；不能认为失败退出就等于业务操作未发生。
- report 导出失败：仅重新执行 report，不重复模型生成、写入、测试或完成操作。
- 当前实验入口只处理 retry_count=0 的首轮；失败后的 Reflection 接续尚未接入实验命令，不自行绕过检查。

第一次先反馈第一段的任务 ID、状态、范围检查与计划内容；不要提供真实 Key。若继续完成全部三段，提供 report-result.json 和对应报告即可，不必粘贴全部事件。
