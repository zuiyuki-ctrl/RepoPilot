# RepoPilot 第一周：仓库理解与检索

依据：`RepoPilot_PRD_v1.1.md` 第 13～18、20～21 节。
当前起点：根目录只有 FastAPI 示例代码和 HTTP 请求示例，尚未形成数据库、索引和评测链路。
时间预算：暂按 7 个学习日、每天 3～4 小时；这是排期假设，不是完成保证。若 Python、SQL 或 Docker 需要补基础，延长学习日，不省略验收。

## 本周成果

能从固定 commit 的真实 Python Git 仓库创建 Workspace Copy，扫描文件、生成 AST CodeChunk、写入 PostgreSQL/pgvector，通过 API 返回带路径、符号和行号的 Top-K 结果，并对至少 10 个已核验问题生成可重跑的 Recall@1/3/5 报告。

本周不做 LangGraph、自动改代码、Reflection、前端、MCP、Hybrid Retrieval 或测试执行沙箱。Docker Compose 用于启动应用和数据库，与以后执行目标仓库测试的 Docker Sandbox 是两件事。本周扫描和解析目标仓库，不导入执行其 Python 模块。

## 带练方式

每个任务依次完成：说明问题 → 写输入输出和失败场景 → 自己实现最小版本 → 用测试或运行证据验证 → 代码审查 → 记录取舍。

- 你负责核心实现，先用自己的话解释设计，再写代码。
- 我负责拆解任务、解释必要概念、审查代码和引导排错。默认先给提示和小例子，需要时再给局部示范。
- 每天保留一个可运行增量和一段复盘：做了什么、如何验证、遇到什么问题、为何采用当前方案。
- 卡住约 20～30 分钟后，提供复现步骤、完整错误、预期行为和已尝试的方法，避免无目的地改代码。
- 不一次性创建 PRD 中所有空目录和抽象；目录随当天实现增加。

## 每日计划

| 学习日 | 你要完成的实现 | 工程思维练习 | 当日验收证据 |
|---|---|---|---|
| Day 1：启动地基 | Git 初始化与忽略规则；Python 依赖声明；backend/app/main.py；配置与基础日志；GET /health；应用 Dockerfile；PostgreSQL/pgvector 与应用的 Compose 配置；.env.example | 区分代码、配置和运行环境；区分进程存活与依赖就绪；解释容器内外连接地址 | 按 README 启动应用和数据库；/health 返回 200 和约定 JSON；数据库可连接且 vector 扩展可用；真实凭据不入库 |
| Day 2：数据层 | SQLAlchemy 的 Repository、RepositoryFile、CodeChunk、AgentTask、TaskEvent；Session；Alembic 首次迁移；仓库创建和查询的数据访问方法 | 区分 API Schema 与数据库 Model；说明外键、唯一约束、事务和回滚的作用 | 空库迁移成功；创建后可查询；失败写入会回滚；外键或唯一约束的负例测试通过 |
| Day 3：仓库导入 | 注册、查询和文件列表接口；固定 commit 的 Workspace Copy；扫描、过滤、文件 hash 与元数据落库 | 区分源仓库与工作副本；设计重复注册和失败状态；处理路径边界 | 导入真实仓库，记录 commit；排除 .git、.venv、node_modules、__pycache__ 和二进制内容；不跟随逃出仓库的链接；源仓库不被改动；无效路径有明确错误 |
| Day 4：Python 解析 | 使用 Python ast；提取模块、类、函数、异步函数和方法；限定符号名、行号及源码；索引接口串起扫描和解析 | 定义 Chunk 的语义边界；说明类与方法内容重叠的取舍；语法错误如何影响批次 | CodeChunk 真实落库；测试覆盖异步函数、同名方法、嵌套定义、装饰器、空文件和语法错误；源码切片与行号吻合；重复索引不累积重复记录 |
| Day 5：向量检索 | Embedding 接口与真实实现；批处理；pgvector 存储；semantic_search(repository_id, query, top_k) | 解释文本如何变成可比较向量；固定模型、维度和距离定义；处理外部调用失败 | 真正的代码和 query 使用同一模型向量化；返回有序结果；跨仓库隔离；维度不匹配和调用失败可诊断；固定索引记录可追踪 |
| Day 6：Search API | Pydantic 请求响应；Search 路由与服务；参数校验、状态检查、错误处理和日志；完善注册与索引的串联 | 解释 API → Service → 数据访问/RAG 的责任边界；制定错误契约 | 结果包含路径、符号、行号和 score；明确 score 含义及排序方向；测试空 query、非法 top_k、仓库不存在和未就绪；完成真实数据库的 API 集成验证 |
| Day 7：评测与演示 | scripts/run_eval.py 的 retrieval 模式；至少 10 个用例；配置快照；JSON/Markdown 报告；README 与完整演示 | 区分系统能运行和检索有效；从失败证据提出改进假设 | 同一入口重跑；保存有序 Top-5；按文件/符号粒度分别汇总 Recall@1/3/5；保留零命中和执行错误；分析未命中原因 |

AgentTask、TaskEvent 按 PRD 在 Day 2 建立模型，但本周不实现 Agent 行为。eval_cases、eval_runs 数据库持久化留到第二周，本周使用 JSON。

## 提前处理的依赖

1. Day 1 核实 Python、Git、Docker Compose 可用性；Windows 下写清宿主机路径如何挂载为容器路径，API 使用容器实际可见的路径。
2. Day 2 前确定 Embedding 服务、模型和维度，再固定向量列定义；具体供应商与版本在实施时核实。尚未接通时可用测试替身开发接口，但测试替身结果不能充当真实检索评测。
3. Day 3 选定真实 Demo 仓库，冻结 commit。优先使用你有权访问且熟悉的 Python 后端仓库；先检查其模块是否足够支持 10 个有意义的问题。定义第一版只接收干净工作区，避免 commit 与实际文件不一致。
4. Day 3～4 手工阅读 Demo 仓库，逐步写满 10 个问题与正确目标；在检索调试前记录 dev/held_out 拆分，避免依据搜索结果反推标签。
5. Day 4 确定超长符号的处理规则与稳定目标标识；Day 5 记录模型、维度、分块配置及索引版本，索引未完成时不伪装为 ready。

## 评测必须遵守的口径

每例保存 query、repository_commit、dataset_version、split、匹配粒度与非空 expected_targets。目标使用仓库相对路径和限定符号名，不使用重建后会变化的 chunk UUID。标签只供评估器使用。

Recall@K = 前 K 条结果映射后的命中目标数 / 该例全部标注目标数。

先截取 K 条原始结果，再按目标去重；不能去重后从后续排名补齐。例如标注两个目标，只找到了一个，Recall 为 0.5，不是 1。

文件级和符号级用例分别宏平均。执行错误记 0 并另报数量；空标签在运行前阻止批次。检查 0 ≤ Recall@1 ≤ Recall@3 ≤ Recall@5 ≤ 1。固定索引下若重跑排序不同，记录原因。本周不预设 Recall 达标数字。

交付文件：

- evals/datasets/code_retrieval_v1.json
- evals/configs/vector_baseline.json
- evals/reports/retrieval_baseline_v1.json
- evals/reports/retrieval_baseline_v1.md
- scripts/run_eval.py
- README.md

## 第一堂练习：Day 1 的第一个增量（约 60～90 分钟）

目标：先让一个职责清晰、配置可解释的 FastAPI 最小服务在本地运行。

先用自己的话回答三个问题：

1. 一次搜索请求，从 HTTP 进入到返回代码片段，需要经过哪些模块？每一层负责什么？
2. 数据库密码为什么应从环境读取？.env.example 应放哪些信息？
3. /health 返回 200 能证明什么？数据库断开时，它是否仍应返回 200？你选择怎样的契约？

然后自己完成：

1. 将应用入口整理到 backend/app/main.py，保留必要的包结构。
2. 增加 GET /health，响应为 {"status": "ok"}。本次先把它定义为进程存活检查；数据库就绪单独验证。
3. 声明依赖，写 .gitignore 和不含真实秘密的 .env.example。
4. 在 README 写清工作目录、环境准备、启动命令和验证方法，并按自己的说明实际执行一次。

提交审查材料：改动文件、实际启动命令、/health 的状态码与响应、三个问题的回答。遇到错误附完整报错，不必等所有步骤成功才反馈。

这一步通过审查后，再接 Day 1 的 Compose 和数据库任务。当天完成与否以运行证据为准。

## 第一周结束时的自检

- 能依据 README 从空数据库启动、迁移、导入、索引、搜索和评测。
- 能解释一次搜索的数据流和各模块职责。
- 能说明重复索引、部分失败、路径隔离和模型维度变化如何处理。
- 能定位至少一个实际未命中案例，并给出有证据的改进假设。
- PRD 第 16 节全部验收后，再进入第二周。
