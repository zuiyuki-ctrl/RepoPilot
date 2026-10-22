# RepoPilot

**可观测、可评测、可实验的 Coding Agent 平台。** 面向本机可信操作者，接入内置 Native Agent 或独立 Process Agent，固定任务、源码、测试与配置，保存执行证据，并对不同策略作成对比较。

更新：2026-10-22。当前代码包含 Agent / Benchmark 登记、实验预览与启动、持久 worker、审批与取消、独立测试、Trace / Diff、比较与人工决定、报告导出，以及外部 Agent 的受控模型网关。模型网关已有无付费部署检查记录；真实供应商付费端到端和 MiniFix 实验仍不能写成已验收。

## 先看演示：历史与实时两种模式

环境：满足 `frontend/package-lock.json` 中 Vite 引擎要求的 Node.js 与 npm。保留仓库中的 `reports/experiments`、`reports/comparisons` 文件。

```powershell
# 在项目根目录执行
Set-Location frontend
npm ci
npm run dev
```

打开终端给出的本机地址，按 **实验总览 → 策略对比 → deduplicate / Hybrid 运行详情 → 历史 Diff 与测试输出** 查看。[5～10 分钟演示讲稿](docs/demo-guide.md)包含具体观察点和解释边界。

历史页面从已保存的报告生成只读快照，不需要 API Key、数据库或 Docker，不会重新执行实验。当前比较来源由 `frontend/comparison-source.json` 指定，不能删除其引用文件；历史目录中还保留后续链路验收及准备失败/未完成记录。

实时页面通过 `/api/v2` 访问后端，提供 Dashboard、Agent / Benchmark 登记、实验与 Run 操作、模型账本和保存的请求预览。它需要 API、数据库；校验和执行还需要独立 worker 及相应 Docker 镜像。后端未连接时显示连接问题，不拿历史快照冒充实时状态。前端开发服务将 `/api` 代理至 `127.0.0.1:8000`。

## 平台与 Agent 的职责

平台主流程：**登记并校验 Agent / Benchmark → 预览冻结实验 → worker 执行 → 平台独立测试 → Trace / Diff / 用量证据 → 成对比较 → 人工决定与导出**。

- Native Adapter 复用内置 Agent；Process Adapter 执行遵循目录 JSON 协议的独立 Docker 镜像，不要求外部 Agent 使用 LangGraph。
- 执行完成不等于测试通过；观测层级不等于质量分；缺失用量和成本保持未知。平台不根据一次失败自动断言根因。
- 在线 Process 只能经显式配置的网关访问固定模型上游；供应商凭据不交给 Agent，Agent 仅获得短期 Run 凭证，调用由平台账本关联并去重。Mock / fake 用量不计入真实模型指标，测试容器仍断网。
- 版本、源码提交、修改范围、保护测试及预算在实验前冻结。审批、取消、执行栅栏及清理状态防止不确定结果被自动重放。

内置 Agent 的代码处理链路仍然保留：

```text
Git 固定提交 → 独立工作副本 → Python AST 分块与索引
                                   ↓
需求 → Vector / Keyword / Hybrid 检索 → LangGraph 工具循环 → 修改计划
                                   ↓
人工审批 → 生成完整文件候选 → 原文件 hash 校验 → 应用到工作副本
                                   ↓
Docker 测试 → TestRun / TaskEvent → 完成检查 → 历史 Diff 与报告
```

- 检索使用 PostgreSQL / pgvector，Hybrid 通过 RRF 融合两路候选；实验模式由程序锁定运行级检索策略。
- 候选生成和实际写入分开；审批、路径范围、文件 hash 与受保护测试限制写入行为。
- TestRun 保存测试结果和快照标识，TaskEvent 保存顺序与调用关联；历史报告不读取当前工作区冒充过去的结果。
- 已有失败分析与重试服务；本批六条运行没有触发 Reflection，当前实验 CLI 只覆盖首轮流程。

分层：`api/routes` 处理 HTTP；`services` 管理业务与事务；`db/repositories` 访问数据；`agent` 包含编排与适配器；`scripts` 提供 worker、CLI 和验收入口；Vue / TypeScript 前端提供实时操作和历史展示。

## 已保存的早期实验结果

以下是三个固定用例、两种检索策略的六条 completed 主运行，属于有人类审批的开发集演示，不是外部 MiniFix 的实验结果，也不代表通用成功率。

| 固定用例 | 任务 | Vector | Hybrid |
|---|---|---|---|
| task-list-v1 | 修复先分页后过滤 | completed；8 项测试通过 | completed；8 项测试通过 |
| deduplicate-v1 | 保留首次出现的完整记录 | completed；6 项测试通过 | completed；6 项测试通过 |
| statistics-v1 | 增加按状态统计 | completed；12 项测试通过 | completed；12 项测试通过 |

测试数量来自保存的 pytest 输出。两条额外准备记录（一条错误、一条未完成）单独保留；旧 task-list / Vector 的新版检索轨迹未记录。每个用例每种策略仅运行一次；没有完整采集 token、成本及全部生成参数，不能宣称统计显著提升或完全可复现。

在 deduplicate 的共同查询 `deduplicate.py` 中，Hybrid 将实现从向量排名 7、关键词排名 1 融合到排名 3；这说明该次查询有关键词贡献，不等于端到端成功率提升。输入选择、来源和限制见[实验对照说明](docs/experiment-comparison.md)。

## 启动实时后端与 worker

当前工作方式为 Windows PowerShell、Python 3.11、本机 FastAPI 与 Docker PostgreSQL。按 `.env.example` 在本机配置环境，不提交或分享真实密钥。以下命令不执行模型请求：

```powershell
# 在项目根目录执行；已有虚拟环境时跳过创建
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
docker compose up -d db
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --reload-dir backend --port 8000
```

已有虚拟环境时跳过创建。`/health` 检查进程存活，`/ready` 检查数据库连接，接口文档位于 `/docs`。数据库连接成功不等于业务表已迁移。

迁移会修改所配置的数据库，执行前确认目标与备份；不要用 `docker compose down -v` 清理环境，它会删除数据卷。

在另一个项目根目录终端启动 worker：

```powershell
.\.venv\Scripts\python.exe -m scripts.platform_worker
```

不带 `--allow-model` 不授权模型调用，但 worker 仍可能处理已排队的无模型校验和执行工作。模型调用须同时满足入口/API 授权与 worker 授权；在线 Process 还需独立的网关部署配置。详见 [Agent / Benchmark 登记](docs/v2-day4-catalog.md)、[实验创建](docs/v2-day5-experiments.md)、[worker 与恢复](docs/v2-day2-native-worker.md)和[真实网关部署](docs/model-gateway-live-runtime.md)。

真实实验还需注册固定提交的任务仓库、受保护测试与本机不可变镜像。不要把 Agent 源码仓库误登记成待修复任务仓库。旧 Native CLI 的[分阶段实验流程](docs/experiment-first-run.md)作为历史复现说明保留，不是实时平台的唯一入口。

## 文档与验证

- [PRD v2.0](docs/RepoPilot_PRD_v2.0.md)：目标范围，不能作为已完成清单。
- [v2 阶段交付说明](docs/RepoPilot_v2_delivery.md)：2026-10-17 阶段总结；后续网关能力以网关文档为准。
- [模型网关实施与验证记录](docs/v2-model-gateway-plan.md)：代码、模拟验证、真实容器检查与未验证范围分开记录。
- [无付费网关部署](docs/model-gateway-mock-runtime.md) / [真实模式部署](docs/model-gateway-live-runtime.md)：模型与凭据启用条件。
- [Process 与独立评测](docs/v2-day3-process-evaluation.md)、[比较口径](docs/v2-day6-comparison.md)、[资源与导出](docs/v2-day6-resources-export.md)：模块操作说明，历史迁移版本不作为当前 head。
- [检索与上下文证据](docs/retrieval-context-evidence.md)：区分命中、工具消息和后续模型请求。
- [前端说明](frontend/README.md)：构建、快照及显示规则。
- [脚本入口说明](scripts/README.md)：区分平台入口、历史实验工具与网关验收夹具，标注副作用边界。
- [历史文档归档](docs/archive/README.md)：旧需求、七天计划及前端布局记录，不再作为当前开发排期。

网关 D2 文档记录集中回归 384 项、63 子测试通过，以及 live 无调用部署 22 项、TLS 假供应商与观测 20 项、固定代理网络 17 项检查通过。这些是历史检查记录，不代表在当前电脑重新执行过，也不是付费模型效果证明。跨电脑需要重建/核实镜像；被 Git 忽略的本机验收报告不会随 pull 自动出现。

项目定位仍是本机可信操作者使用的 MVP，不宣称完整 L2、自动根因判定、多租户生产安全、通用修复成功率或严格费用上限。

## 文件保留与清理

- `reports/`、`evals/` 是历史证据与评测定义，前端直接引用其中部分文件，不按临时文件清空。
- `.platform-artifacts/` 可能保存未导出的运行证据；它不受 Git 跟踪，不能靠 Git 恢复。
- `__pycache__/`、`.pytest_cache/`、`frontend/dist/` 是可再生产物；`frontend/public/data/` 可在保留原报告的前提下通过 `npm run snapshots` 重建。
- 保留 `.env`、虚拟环境、依赖、数据库数据卷及迁移文件；不要用全局清理命令替代逐项确认。
