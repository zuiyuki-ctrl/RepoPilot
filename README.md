# RepoPilot

面向 Python Git 仓库的 Coding Agent 与实验评测项目。通过代码检索、LangGraph 研究与规划、人工审批、候选生成、受控写入和 Docker 测试，把一次修改与它的证据关联起来。

当前已跑通三个固定小用例的 Vector / Hybrid 两组流程，共六条 completed 主运行；提供离线实验总览、策略对比和运行详情。它们是有人类审批的开发集演示，不代表通用任务成功率，也没有证明 Hybrid 整体更优。

## 先看演示

环境：满足 `frontend/package-lock.json` 中 Vite 引擎要求的 Node.js 与 npm。保留仓库中的 `reports/experiments`、`reports/comparisons` 文件。

```powershell
Set-Location D:\RepoPilot\frontend
npm ci
npm run dev
```

打开终端给出的本机地址，按 **实验总览 → 策略对比 → deduplicate / Hybrid 运行详情 → 历史 Diff 与测试输出** 查看。[5～10 分钟演示讲稿](docs/demo-guide.md)包含具体观察点和解释边界。

前端启动时从已保存的历史文件生成显示快照，不需要 API Key、数据库或 Docker，不会重新执行实验。它目前是只读展示，不是实时任务操作台。对比报告由 `frontend/comparison-source.json` 明确指定。

## 已实现的主链路

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

分层：`api/routes` 处理 HTTP；`services` 管理业务与事务；`db/repositories` 访问数据；`agent` 编排模型与工具；`scripts` 负责命令行和本地实验文件；`frontend` 展示历史快照。LangGraph 当前承载研究和规划，审批、写入与测试由服务和分阶段入口串联。

## 当前实验结果

| 固定用例 | 任务 | Vector | Hybrid |
|---|---|---|---|
| task-list-v1 | 修复先分页后过滤 | completed；8 项测试通过 | completed；8 项测试通过 |
| deduplicate-v1 | 保留首次出现的完整记录 | completed；6 项测试通过 | completed；6 项测试通过 |
| statistics-v1 | 增加按状态统计 | completed；12 项测试通过 | completed；12 项测试通过 |

测试数量来自保存的 pytest 输出。两条额外准备记录（一条错误、一条未完成）单独保留；旧 task-list / Vector 的新版检索轨迹未记录。每个用例每种策略仅运行一次；没有完整采集 token、成本及全部生成参数，不能宣称统计显著提升或完全可复现。

在 deduplicate 的共同查询 `deduplicate.py` 中，Hybrid 将实现从向量排名 7、关键词排名 1 融合到排名 3；这说明该次查询有关键词贡献，不等于端到端成功率提升。输入选择、来源和限制见[实验对照说明](docs/experiment-comparison.md)。

## 本机后端开发

当前工作方式为 Windows PowerShell、Python 3.11、本机 FastAPI 与 Docker PostgreSQL。按 `.env.example` 在本机配置环境，不提交或分享真实密钥。以下命令不执行模型请求：

```powershell
Set-Location D:\RepoPilot
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
docker compose up -d db
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --reload-dir backend --port 8000
```

已有虚拟环境时跳过创建。`/health` 检查进程存活，`/ready` 检查数据库连接，接口文档位于 `/docs`。数据库连接成功不等于业务表已迁移。

真实实验另需固定版本的样例 Git 仓库、测试镜像和模型配置，按[分阶段实验流程](docs/experiment-first-run.md)执行；其中明确标注的 Embedding 和模型步骤可能产生费用。离线展示不需要执行这些命令。

## 文档与验证

- [需求文档](docs/RepoPilot_PRD_v1.1.md)：目标范围，不能作为已完成清单。
- [当前进度与后续计划](docs/this-week-plan.md)：实际完成项、真实验收和剩余边界。
- [检索与上下文证据](docs/retrieval-context-evidence.md)：区分命中、工具消息和后续模型请求。
- [前端说明](frontend/README.md)：构建、快照及显示规则。

最近对照模块的 13 项离线测试、前端 19 项数据测试、类型检查和生产构建已通过；页面由用户验收通过。这些不是全项目回归结果，六条历史实验也不验证所有异常分支。当前不包含多租户、生产部署或任意仓库依赖环境的自动构建。
