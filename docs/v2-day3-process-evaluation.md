# Day 3：Process Adapter 与平台独立评测

2026-10-15 实现。代码及验证结果以七天计划的 Day 3 实际记录为准；**本机 Docker 引擎检查未成功，真实容器、数据库 worker 和新页面联调待用户执行，不能标为 Day 3 全部验收通过。**

## 1. 这个模块解决什么

同一个 task-list 任务现在可以交给不导入 RepoPilot 后端的独立程序。程序只负责修改自己的工作区、按协议返回执行结果；平台负责测试和判断。

```text
可信准备入口冻结 Case / 测试 / 原始文件 / 镜像 / 运行器指纹
→ worker 运行原始基线（不符合声明就停止，不调用 Agent）
→ Native 审批执行，或离线 Process 容器执行
→ 确认写入者停止
→ 平台保存最终快照并检查修改范围、受保护文件
→ 新容器运行平台保存的权威测试
→ TestRun + Evaluation + 事件同 Run 关联
→ live 页面查看结果、历史 Diff、测试及受限日志
```

例如 Demo noop 自报 completed，但没有修改分页逻辑：最终测试仍失败，平台结论 not_passed。Demo fix 写入预设正确实现后，只有必需测试与保护规则都满足才 passed。这个 Demo 是确定性协议 fixture，不是模型或通用 Agent 能力实验。

## 2. 实现入口与复用边界

- `schemas/process_agent.py`：容器配置与可选上报事件 schema，拒绝未知字段；镜像只接受已有 `sha256:<64 hex>` ID。
- `agent/adapters/process.py`：请求文件、结果身份/协议校验、退出码冲突、可选 trace。没有验收评分逻辑。
- `services/platform_container.py`：无网络、非 root、只读容器根文件系统、资源限制、固定挂载、参数数组启动、受限日志、容器归属检查及停止/清理确认。
- `services/platform_artifacts.py`：有界读取、重复 JSON 键/深度限制、链接和硬链接拒绝、全文件范围检查、固定字节快照及 Diff。
- `services/platform_test_collector.py`：冻结测试包、原始基线、独立最终测试。Native/Process 共用，没有第二套评分器。
- `services/platform_worker.py` / `run_worker_service.py`：复用 Day 2 的执行栅栏；增加 baseline/evaluate 阶段。等待模型不持数据库事务，评测使用独立时间预算。
- `services/platform_report_service.py`：从已保存的 Evaluation、TestRun 引用和 Diff 读取，不重新扫描当前工作区。
- `scripts/prepare_platform_run.py`：模块开发入口，只冻结和入队，不调用模型或测试；正式前端注册/创建入口仍在 Day 4—5。
- `examples/process_agent/`：stdlib-only Demo、显式构建 Dockerfile 与配置示例。

本轮没有新增数据库迁移；复用 Day 1—2 的表。数据库需已升级到 `d714a02b0001`。旧 v1 行为和报告保留，不批量重跑。Day 2 旧开发入口创建且未绑定测试包的 Run 保持 pending，不用当前文件补造它的原始基线；要完整验收请创建新 Run。

## 3. 固定 Python 权威测试边界

首版仅支持小型 `python-basic` 用例，不安装目标依赖，不支持任意测试工程。

- 初始目录只接纳 `.py/.md/.txt` 及根 `.gitignore`；拒绝其它隐藏文件、pytest.ini、pyproject.toml、conftest.py、sitecustomize.py 等未适配配置。不能删除原用例配置后仍声称同一版本被支持；应明确使用兼容 Case。
- 只排除来源仓库根 `.git`，不静默忽略 Agent 后来创建的非 Python 文件。修改未声明文件、删除/修改受保护测试、增加 pytest.ini 等都会被发现并阻止通过。
- Python 快照 hash 兼容旧算法；另保存全部初始文件 hash，并对所有最终文件做范围检查。拒绝链接/重解析点/硬链接，单文件 1 MB、总量 10 MB、500 文件、1000 目录。
- Agent 只能挂载 input（只读）、自己的 workspace（可写）、output（可写），不能访问 authority、原始快照、平台数据库或平台测试输出。
- 测试从新容器运行：源码只读挂 `/workspace`，平台测试/pytest.ini 只读挂 `/authority`，唯一报告目录单独挂 `/test-results`。
- 使用固定 `python -I` 启动器，先导入受信镜像的 pytest，再加入源码导入路径；清理 PYTEST_*、关闭自动插件加载、`--noconftest`、固定 `-c` / rootdir / 测试路径和 import mode。不会回退执行 Agent 提供的测试命令。
- 环境指纹除镜像/超时外，还包含采集器和容器运行器实现指纹。中途改变实现则拒绝原冻结测试包，不把不同评测器当同一环境。
- JUnit 仍通过已有精确内容校验。v2 的运行器身份单独作为平台来源元数据保存；旧 JUnit 口径不改变。

这防止常见工作区配置影响验收，不是对恶意 Python 的完整防作弊保证：测试会导入被测代码，同一测试进程中的恶意代码仍是限制。容器不是敌对多租户安全边界。产物在读取时限量，日志保留有上限且 Docker 不保存额外日志；尚无绑定目录硬盘配额，受信操作者需关注磁盘占用。

## 4. 超时、取消、恢复与分级观测

正常 Process 超时由容器层停止整个容器，确认停止后记录 timed_out；进程退出码非零不能因为 result 写了 completed 就当成功。缺结果、非法 JSON、重复键、错版本/身份/run_id 等记录协议错误，不猜测 stdout 作为结果。

父 worker 强杀子进程或子进程异常退出时，也尝试按 run_id 和用途清理所属容器。Docker 失联、归属不符、清理不能确认或写入是否完成不确定时保留 active_token，标 interrupted/unknown，不开始下一次运行，也不自动重放。人工恢复沿用 Day 2 文档；**必须先确认容器和本机写入进程均停止**，`--confirm-writers-stopped` 不是自动检查工具。

测试本身每次最多 120 秒，Agent 预算不包含测试和人工等待。Process 的外围阶段允许额外清理时间；它不冒称可强制 Token 或模型调用次数。准备失败不设置 Agent started_at。

L0 来自平台执行、Diff、TestRun 证据；L0 不需要向量化或模型用量。可选 `/output/trace.jsonl` 首版接受受限调用/用量/上下文指纹结构：版本、事件 ID、run_id、kind、调用 ID、Token 和内容 hash；固定上限 1 MB、1000 行。重复同内容去重，冲突或非法结构标 invalid；外部记录来源为 agent_reported，无法确认应有调用数时标 partial，不自动升为完整 L1/L2。

`trace: true` 却没有文件显示 missing；不提供显示 unsupported。页面显示传输状态和字段来源，完整调用汇总/覆盖率可视化仍属 Day 6。不是宣称任意第三方现有 trace 格式已经适配。

## 5. 需要操作者执行的真实验收

下面保留可复现的操作步骤；初次编写时尚未执行，2026-10-15 的真实验收结果见第 7 节。全部使用项目根目录；先启动 Docker Desktop，并确认 Linux engine 正常。

### 5.1 环境与镜像

```powershell
docker info
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
docker image inspect repopilot-pytest:py311 --format '{{.Id}}'
```

如果 `repopilot-pytest:py311` 不存在，先按已有 sandbox/Dockerfile 显式准备测试镜像；不要把 API 镜像作为权威测试镜像。

可以复用已有 pytest 镜像作为 Demo 基底，无需为 Demo 安装任何库：

```powershell
docker build --pull=false --build-arg BASE_IMAGE=repopilot-pytest:py311 -t repopilot-protocol-demo:v1 examples/process_agent
docker image inspect repopilot-protocol-demo:v1 --format '{{.Id}}'
```

自行复制 `examples/process_agent/config.example.json` 为本机配置文件，把 image 替换为上面返回的完整镜像 ID；示例占位符故意不能通过校验。先保持 `--mode noop`，下一次新 Run 改为 `fix`。程序实现相同但启动配置不同，必须如实记录，不声称这是两个真实模型版本。

### 5.2 冻结并入队一条 Process Run

选择**已注册、干净且处于 Case 指定 commit 的 task-list 仓库**，不是 RepoPilot 自身仓库。Process 会另复制工作区，不修改注册仓库。没有该仓库时先沿用原仓库注册入口；本阶段不需要扫描、索引或 Embedding。

```powershell
.\.venv\Scripts\python.exe -m scripts.prepare_platform_run `
  --repository-id <实际仓库UUID> `
  --case evals/experiments/cases/task-list-v1.json `
  --definition evals/experiments/definitions/task-list-pipeline-v1.json `
  --test-image <测试镜像完整sha256ID> `
  --process-config <你的本机配置JSON路径> `
  --agent-name "Protocol Demo (fixture)" `
  --agent-version v1 `
  --creation-key day3-task-list-noop-01
```

尖括号处先替换真实值，不要原样执行。该命令只做本机检查、保存冻结文件及入队；失败后保留 Run 和产物查看原因，不删除证据强行复用同一个 creation_key。CLI 对已存在键明确拒绝，不重新执行准备；worker 使用已有唯一 Run。

### 5.3 执行与页面核对

```powershell
.\.venv\Scripts\python.exe -m scripts.platform_worker
```

不加 `--allow-model`。该 worker 可执行离线 Process、测试及已批准写入；Native plan/generate 被过滤，不会因为队列里有 Native 就偷偷调用模型。`--once` 每次只领取一个阶段，不是自动跑完一条 Run。

重启 API，运行前端，打开命令打印的 `/live/runs/<Run ID>`。正常 noop 应看到原始 2 failed/6 passed、最终仍有失败，execution completed、evaluation not_passed；fix 新 Run 应看到最终 8 passed，且只有 task_list.py 修改。实际结果以日志为准，不预填成功记录。

异常支线可修改新配置的 mode 为 `wrong-id / invalid-json / missing / nonzero / timeout / tamper / outside`，每次创建新 Run；timeout 样例默认会等待预算到期，也可以从页面取消。记录 TestRun ID、结果、清理状态及容器是否确实消失。异常 fixture 不能混入真实模型成功率。

Native 如需完整新链路，用同一准备命令的 `--task-id <新建created计划任务UUID>` 替换 `--process-config`；该任务需与 Case、仓库和已冻结配置匹配。保留原索引准备与人工审批，真实模型由你显式启用 `--allow-model`。不要借用 v1 已完成任务或为旧 Run 事后补造基线。

所有原始本机产物位于 `.platform-artifacts/<Run ID>/`，已加入 gitignore；如需跨机，须一起迁移数据库记录和完整证据包，不能只搬一个最终文件。后续正式导出模块统一做可移植投影。此处不自动清空历史目录。

## 6. 适合你亲手做的面试准备

1. **做一次“自报完成但平台不通过”的实测。** 保存 noop/fix 两条 Run 的真实 ID，指出平台验收来自哪个快照、哪个 TestRun，而不是 Demo 的返回字符串。
2. **做一次取消或错误协议。** 观察为什么终止本机 docker CLI 不等于停止容器，解释为何不能确认停止时宁可 unknown/阻塞，也不能自动重复模型请求。
3. **画清四条边界。** Adapter 负责执行，worker 负责持久调度，collector 负责权威证据，evaluation 负责纯规则判断。展示一个 Agent 不上报 Token 也能被评测的 L0 运行。
4. **诚实说限制。** 固定 Python profile、无网络 Demo、单 worker、无敌对代码防作弊保证；没有真实容器结果时就说只完成离线验证。不要把这组 fixture 当作 Agent 成功率提升实验。

推荐用一句话开场：**“我把 Agent 的执行结果和平台验收分开，同一套固定测试可以评测内置 Agent 与独立外部程序；缺少内部轨迹不会阻止评测，也不会被包装成完整证据。”**

## 7. 2026-10-15 本机真实验收

使用实际 PostgreSQL、持久 worker、Docker 29.1.3 与无模型协议 Demo，共运行六条独立 Run。数据库此前已在 `d714a02b0001`，本次没有补跑 Day 2 迁移。Demo 基于已有本地 pytest 镜像构建，没有下载依赖、调用模型或 Embedding。

| 场景 | Run ID | execution | evaluation | 核查结果 |
| --- | --- | --- | --- | --- |
| noop | `f1c7c515-5e89-426a-935b-62cc16cbd699` | completed | not_passed | 基线和最终均为 2 failed / 6 passed，无文件改动 |
| fix | `58f52820-ea71-488b-bc06-c3b3350afb3a` | completed | passed | 基线 2 failed / 6 passed，最终 8 passed；只修改 task_list.py |
| wrong-id | `a638f061-447f-4077-9b6f-07d02c5e6104` | failed | not_passed | 错误结果身份被拒绝，原因 execution_failed |
| timeout | `6e4f6418-7e5d-4a1b-9077-d725b4c0c227` | timed_out | not_passed | 10 秒 Agent 预算到期，平台评测仍独立结束 |
| tamper | `781341e8-a2d2-4f89-839f-54c95859005e` | completed | not_passed | tests/test_task_list.py 被修改，workspace_constraints_violated；不执行最终测试 |
| outside | `e51154eb-4b88-44f8-90c4-7fedac1d827a` | completed | not_passed | 新增越界 outside.txt，workspace_constraints_violated；不执行最终测试 |

六条 Run 均为 finished，清理记录均为 confirmed，active_token 均为空；结束后 `docker ps -a --filter name=repopilot-v2` 无残留。用户目视确认 noop/fix 页面正常展示基线/最终测试、Diff，以及独立的执行与验收结果。

fix 的最终 TestRun 为 `2ca9b7f9-0e7f-448e-bdcf-9a6fe2e7af7c`，最终快照为 `a0b6a0edf7bcbee65a3bc6bed8dd7ac7baed899a5dc00cfa3eae500ff5ce330a`。报告通过已有 report 服务从持久证据导出到 `.platform-artifacts/day3-acceptance-20261015/<mode>-report.json`；目录被 gitignore，跨机不会自动带走。

测试镜像：`sha256:14ae9449013b4c5cf1ac42d09ae368570eda7315f3b8757c6274e9e48fab1d28`。Demo 镜像：`sha256:7f80a6f974f9e481701db8ab7bdeb174a813e89da936f2f17775e4b7952fcba4`。

本次补充 CLI `--timeout-seconds`（1～3600，默认 600），控制 Agent 预算，平台测试保留独立预算。没有更改执行/验收判定来迎合结果。

结论：Day 3 外部协议 Demo 的正常与上述异常链路真实验收通过，可进入 Day 4。不代表真实模型效果、Native 新审批全流程、所有异常组合或任意恶意代码防护已通过；取消和其他协议错误本轮没有另做真实容器复测。
