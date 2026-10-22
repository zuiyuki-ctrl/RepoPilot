# RepoPilot — Coding Agent Evaluation & Experiment Platform

## Product Requirements Document v2.0

日期：2026-10-13。状态：需求基线草案，待实现。本文吸收本轮产品讨论，并以当前代码和 v1 七天阶段的真实验收为起点；文中的新增协议、表、接口和页面均为 v2 要求，不表示已经实现。

> 通过标准化 Agent Adapter 将 Coding Agent 与评测基础设施解耦，使不同 Coding Agent、Agent 版本和运行配置能够接入统一的 Benchmark、Sandbox、Trace、Evaluation 与 Experiment Pipeline。

产品理念：**让 Coding Agent 的每一次改进，都有证据支持。**

## 1. 背景：已有基础与限制

### 1.1 已验证的基础

v1 已具备仓库提交固定与隔离工作副本、代码索引、向量/关键词/混合检索、内置 LangGraph Agent、计划审批、候选修改、受控写入、Docker 测试、反思与有限重试、事件轨迹、历史报告和实验对比。实际能力与验证范围参见 [七天阶段记录](archive/core-platform-seven-day-plan.md)。

2026-10-13 的 task-list 新配对由用户完成：Vector / Hybrid 修改前均为 2 失败、6 通过，修改后均为 8 通过；实验级声明验收双方 passed；各记录 37 个事件和 7 次用量完整的请求。任务 Token 分别为 18,014 / 19,097，准备期各 443 单列。用户已确认新数据页面可正常浏览。此单对结果验证管线，不证明策略总体收益；供应商内部版本、价格及采用门槛的缺失仍明确展示。

### 1.2 当前限制

- `experiment_execution_service.py` 直接依赖内置任务、计划、候选和审批服务；外部 Agent 无法作为同等被测对象接入。
- `ExperimentDefinition` 固定 baseline=vector、candidate=hybrid、changed_parameter=retrieval_policy；尚不能表达 Agent 版本对比。
- 现有 `AgentTask` 同时承载内置 Agent 工作流和实验关联，不能直接用它代表任意外部进程的生命周期。
- 真实实验主要通过脚本分阶段推进，前端消费导出快照；尚无通用 Agent Registry、实验创建和执行控制页面。
- 当前 Docker 能力主要隔离测试执行，不能据此宣称任意外部 Agent 已被安全隔离。

v2 复用已验证的评测资产和纯分析逻辑，逐步替换与内置 Agent 强绑定的编排。旧 PRD v1.1 保留历史意义；新增平台化范围以本文为准，不回写旧实验的口径和证据。

## 2. 产品定位、目标用户与价值

面向自研 Coding Agent 的工程师、AI Infra 与 Agent Evaluation 团队，支持三个主要问题：

1. Agent 为什么失败？查看实际执行、Diff、测试及可获得的内部轨迹，形成有依据的待验证假设。
2. 改动是否有效？在声明的任务集、运行条件与重复计划下对比改善、退化、资源消耗和未知项。
3. 新版本是否值得采用？按预先声明的门槛提供本批结论，允许人工记录采用、保留或继续实验。

平台提供证据和判断依据，不自动承诺定位根因、统计显著、生产可靠性或发布安全。

## 3. v2 目标与最小交付

首版交付必须形成：注册 Agent 版本 → 选择版本化 Benchmark → 冻结双方配置 → 明确启动实验 → 独立运行 → 平台验收 → 查看配对证据与决策。

| 目标 | v2 MVP 范围 |
|---|---|
| Agent 解耦 | Native Adapter 包装内置 Agent；Process Adapter 运行一个不导入 RepoPilot 后端的外部 Demo Agent |
| 外部接入 | 本机操作者注册已准备的容器镜像与参数数组；Python 程序也通过 Process Adapter 接入 |
| 独立验收 | 平台取得最终源码快照，独立检查 Diff、受保护测试和验收规则，不采用 Agent 自报成功 |
| 可观测兼容 | L0 可用；L1/L2 可选且逐字段标记实际完整性，不强制使用 RepoPilot 的检索 |
| 实验泛化 | 比较两个冻结的 Agent Configuration，区分单变量受控实验和多变量 Benchmark 对比 |
| 产品入口 | 五类页面及最小本机 HTTP API；保留脚本入口作为同一服务层的客户端 |

外部 Demo 可以是确定性修复程序，用于协议验收，必须标明 fixture/demo，不能将其成绩宣传为通用 Agent 能力。

## 4. 非目标

- 不在 MVP 接入具体商业 Coding Agent、HTTP Agent、远程 SaaS Agent 或专用 Python SDK。
- 不提供“拖入任意代码即可自动适配”的承诺，不自动安装未知依赖、构建或拉取任意镜像。
- 不建设公网多租户服务、分布式调度、大规模并发、计费、CI 发布门禁或插件市场。
- 不同时新增 Reranker、检索算法或复杂评分模型；优化方向必须由证据和下一轮实验支持。
- 不以任意 shell 字符串作为启动协议，不自动执行模型生成的主机命令。
- 不重写旧 Agent，不补造历史 Trace、Token、环境身份、验收定义或人工审批。

## 5. 核心概念

| 概念 | 含义及边界 |
|---|---|
| Agent | 被测系统的逻辑身份，例如团队自研 Agent，不等于目标源码仓库 |
| Agent Version | 不可变实现版本：版本标签、实现/镜像指纹、Adapter 版本和能力声明；相同标签不同内容拒绝覆盖 |
| Adapter | 把具体 Agent 启停和输出转换为平台协议；不判定任务成功 |
| Capability | 对代码修改、用量、工具、检索、上下文、暂停恢复等能力的声明及验证结果 |
| Agent Configuration | 固定版本加模型、Prompt、策略、预算和非秘密运行配置的快照；秘密只保存引用 |
| Benchmark Suite Version | 固定的 Case 清单、顺序及内容指纹，不是动态文件夹扫描结果 |
| Case Version | 任务描述、源码提交、可修改范围、受保护测试、环境和验收规则 |
| Experiment | 声明比较模式、双方配置、全部 Case、重复序号、干预策略和可选决策门槛 |
| Run | 一侧配置在一个 Case、一个重复序号上的执行实例，绑定唯一 workspace |
| Evaluation Result | 平台对具体最终快照的独立判断及证据，和 Agent 执行状态分开 |
| Artifact | 输入快照、调用记录、Diff、JUnit 等不可变文件及 SHA256；路径可迁移，内容身份不可变 |

用户提供的目标源码仓库是 Agent 的修复对象；Agent 程序本身是另一份运行产物。RepoPilot 的仓库向量化只供选择该能力的 Agent 使用，外部 Agent 可使用自有检索，也可完全不检索。

## 6. 架构与职责

```text
UI / CLI → Registry + Benchmark + Experiment Service
                         ↓ 冻结请求、分配 Run
                    Runner / Worker
                    ↓            ↓
             Native Adapter   Process Adapter
                    ↓            ↓
              内置 Agent      外部 Agent 容器
                    └──── 独立工作副本 ────┘
                              ↓ 停止写入、平台采集最终快照
               Diff / Integrity → Evaluation Sandbox
                              ↓
                Evaluation + Trace → Comparison → UI / Report
```

- Runner 管理启动、预算、超时、暂停/恢复、取消和回收；不理解内置计划 JSON 的细节。
- Native Adapter 内部可以调用现有业务服务，但通用 Runner、评测及对比不能反向导入内置节点或要求外部 Agent 创建 AgentTask。
- Evaluation 只接收版本化规则、平台采集的快照和证据；保持纯规则与测试执行边界清晰。
- Trace 接收平台观测和 Agent 上报，保留来源和完整性；不同来源不能混为一类可信度。
- 长时执行交给单独 worker，API 只登记和查询。MVP 单 worker、全局并发 1，数据库保存调度状态；不用 FastAPI 进程内后台任务冒充持久队列。
- 状态转换及事件写入使用短事务；模型等待、容器运行和测试不持有数据库行锁。

## 7. Agent Adapter 协议 v1

### 7.1 生命周期

概念接口为 `metadata()`、`prepare(context)`、`run(request)`、`cleanup(context)`；具体同步/异步实现按当前服务形态选择，不为统一 async 强制重写现有同步服务。

| 操作 | 责任 |
|---|---|
| metadata | 返回协议版本、身份、实现指纹、能力和支持的配置字段；不启动付费调用 |
| prepare | 检查依赖、隔离环境和输入挂载，返回本次 Run 的准备结果；不自动安装、拉取或调用模型 |
| run | 处理固定任务，只修改获准的工作区；可返回执行结果或待人工操作状态 |
| cleanup | 回收本次创建的资源，可重复调用；不得删除共享仓库、其它 Run 或历史证据 |

Runner 无论正常结束、超时、取消、解析失败，都尝试 cleanup。清理失败单独保存，不覆盖原始错误；残留容器可按 run_id 定位并恢复清理。

### 7.2 输入 AgentRunRequest

必须包含 protocol_version、run_id、case_id/version、任务描述、工作区逻辑路径、repository_commit、Agent 版本/配置指纹、允许修改范围、预算、执行超时和输出协议位置。非秘密环境只包含声明的字段。

- 工作区由平台分配，不接受 Agent 返回的任意主机路径；容器内固定路径与主机路径隔离。
- 平台保存验收定义及受保护测试来源。Agent 可读取允许可见的测试，但不能修改平台保存的权威测试或规则。
- `agent_config` 是该 Adapter 接受的有版本 schema，未知字段拒绝；不自动将字段拼接为 shell 指令。
- Token/模型次数预算注明 enforceable 或 advisory。L0 无法计数时不能声称严格限制 Token；平台仍强制墙钟、进程资源和输出大小限制。

### 7.3 输出 AgentRunResult

包含 protocol_version、run_id、execution_status、受控 error、实际 Agent 身份、可选 usage/trace 引用；没有可作为验收结论的 `success=true` 字段。

execution_status 为 completed / failed / timed_out / cancelled / awaiting_input。completed 仅表示执行正常结束；超时、取消由平台实际控制结果认定，Agent 不能自行覆盖。

非法结构、未知版本、身份不匹配、结果缺失均为 protocol_error。进程退出码 0 但没有有效结果不能当完成；非零退出码与 completed 冲突时保存双方事实并判执行失败。

### 7.4 Process Adapter 首版传输

- 外部 Agent 在单独容器中运行。注册项包含已存在的镜像 ID/digest、入口参数数组、协议版本及支持配置，禁止 `shell=True` 或拼接命令字符串。
- 请求为只读 `/input/request.json`；源码位于 `/workspace`；Agent 向 `/output/result.json` 写唯一结果，可另写 `/output/trace.jsonl`。stdout/stderr 是日志，不用于猜测最终结果。
- 容器退出并确认停止后才读取产物；平台限制文件大小、行数、JSON 深度和日志量，拒绝符号链接、越界路径、重复终态及错误 run_id。超限记录截断或协议错误，不静默丢弃后宣称完整。
- usage/trace 是可选结构化输入，带 schema_version、来源、调用 ID 和时序；缺文件可正常作为 L0 完成。声称提供却缺失时记录 missing。
- MVP 不要求外部 Agent 实时流式传输。运行中可见平台生命周期，内部轨迹在退出后导入；不把这个能力描述为实时 Deep Trace。

### 7.5 审批、恢复和中断

Native Adapter 必须保留当前计划/候选审批。暂停时存平台可恢复检查点，返回 awaiting_input 与待审批内容引用；审批决定持久化后继续同一个 Run，禁止重复执行已确认的模型调用或写入。

Experiment 显式冻结 intervention_policy：Native 的逐步人工审批，或启动前授权在范围内自主执行。Process Demo 使用后者；不得替用户默默批准已有计划。两种干预方式不同必须在对比中展示；受控实验要求一致，多变量 Benchmark 可作为已声明差异。

重复 start/cancel/approve 请求不重复产生执行副作用。worker 重启后先核对所属容器与检查点；无法证明可恢复时标记 interrupted/unknown 并保留证据，不自动重放付费请求。

## 8. 可观测层级与能力协商

| 层级 | 可采集证据 | 可以支持的指标/分析 |
|---|---|---|
| L0 Black Box | 平台启动/终止、前后快照、stdout/stderr、退出状态、时间、独立测试 | 声明任务验收、测试结果、Diff、平台墙钟 |
| L1 Instrumented | 可选模型请求、用量、工具和错误结构 | 在实际覆盖范围内计算 Token、估算成本、工具统计、模型耗时 |
| L2 Deep Trace | 可选检索、实际上下文、规划、反思 | 有标注时计算 Recall，支持更细证据分析；不自动证明根因 |

L0/L1/L2 是展示摘要，不能代替字段级 capabilities。每项显示 declared、validated，以及本次 available / partial / missing / unsupported / invalid；注册声明 L2 不意味着每次运行都完整。

所有事件保存 source（platform / adapter / agent_reported）、run_id、平台递增 sequence，可选原始 event_id/parent_call_id、发生时间和接收时间。sequence 表示平台接收顺序，不伪装为跨进程精确因果顺序；重复事件去重，冲突保留异常，不跨调用合并 usage。

外部上报 Token 显示 agent_reported；有能力但记录不完整，只展示已知小计与覆盖率；不提供则为未知，不是 0。Recall 必须有版本化相关性标注及明确查询范围，无检索/标注就显示不适用或未记录。

## 9. 独立评测协议

### 9.1 平台证据链

冻结 Case/验收 → 验证原始基线 → Agent 执行 → 确认所有写入进程停止 → 平台校验修改范围与受保护内容 → 生成不可变最终源码快照 → 新测试容器执行 → 解析平台取得的 JUnit → 计算 Evaluation Result。

不得直接采用 Agent 提供的 Diff、测试结论或 result.success。它们只能作为附加声明。Agent 容器不挂载平台测试输出目录；评测使用平台准备的权威测试和配置，不能让工作区修改的 pytest 配置/插件控制验收命令。

### 9.2 Evaluation Result

绑定 run_id、final_snapshot_hash、规则版本/hash、Diff hash、TestRun ID、JUnit hash、结论及缺失原因。结论为 passed / not_passed / unknown；缺证据不猜测。每次重新评测创建新记录，并由报告明确选择，不覆盖旧结论或择优替换。

- bug_fix：指定基线测试真实断言失败；最终必需测试齐全且通过；Diff 和保护规则满足。
- feature：声明的功能/回归测试齐全且通过；如含人工语义标准，须有绑定本次证据的真实复核。
- 越界修改、受保护测试被篡改、已知执行失败/超时按声明规则为 not_passed；协议损坏、缺有效测试报告等阻断细项记录，不能判 passed。
- 执行失败后可安全取得快照时仍可评测并展示测试事实，但失败执行不能仅凭后续测试通过改称端到端成功。Runner 中断且无法确定事实为 unknown。
- 原始/最终快照、测试与 Agent 版本关联不一致时停止汇总正向结论。

### 9.3 统计口径

已启动 Run 计入任务成功率分母，包括启动后失败、超时、取消。启动前准备失败单列。进行中和 unknown 明示；暂定通过比例不冒充完整最终成绩。重复运行按预先声明的 case/version/repeat_index 配对，不挑最好一次。

测试通过率保留 passed / (passed+failed+errors+skipped) 及覆盖率；漏跑必需测试不能通过验收。资源比较使用相同完整样本，缺失不是免费。成本需版本化价格与币种，标明估算；无法计价保持未知。

Latency 分开记录 preparation、execution、evaluation、human_wait 和总墙钟；嵌套耗时不直接相加。MVP 优先保证平台起止区间准确，缺人工等待区间不推算为 0。索引成本属于可选准备期开销，不强行计入不使用平台检索的 Agent。

## 10. Experiment 模型与决策

### 10.1 两种模式

| 模式 | 可不同的内容 | 允许表达的结论 |
|---|---|---|
| controlled | 显式声明的单一配置维度；其余要求条件一致且可核对 | 本批条件下的结果差异，支持后续因果假设；单次 Trace 或单对样本不证明因果 |
| benchmark | 声明的 Agent、版本、模型、Prompt、策略等多项变化 | 固定任务与验收环境下双方的观察表现，不归因到其中某项变化 |

两者均固定 Suite/Case、提交、测试与验收、重复计划、样本选择规则，并公开双方预算和人工干预。受控实验禁止未知字段被静默忽略；Benchmark 也不能因为允许多变量就忽略缺失的任务或测试证据。

受控模式记录实际条件差异/缺失及允许变量。Benchmark 将 Agent/模型差异列为声明差异，而非套用 v1 Vector/Hybrid 的一致性规则将所有跨 Agent 对比判无效；执行身份或验收环境不可核实时仍降级为证据不足。供应商内部版本无法取得必须注明不可完全复现，不由用户填假值。

### 10.2 创建与冻结

创建时选择 Suite 版本、Case 全集或明确子集、双方不可变配置、模式、变化字段、重复次数、执行顺序、预算、干预策略和可选决策门槛。启动前预览预计 Run 数和可能的付费调用，由用户明确启动。MVP 固定顺序、串行执行并记录顺序偏差，不声称完成随机试验。

启动后冻结 manifest 与各内容 hash；修改规则创建新 Experiment。每个 (experiment, side, case_version, repeat_index) 只有一个主 Run，重试/恢复与额外尝试单独关联并保留，不丢掉失败样本。已完成旧 Run 不默认复用进新实验；复用能力延期，先避免条件不一致和事后挑样本。

### 10.3 判断输出

复用改善、退化、保持成功、双方未成功、未决、不可比分类，展示范围与分母；将观察差异、可比性和因果解释分开。

预先门槛、事后探索性门槛和人工采用决定分别保存。批次输出 meets_batch_rules / does_not_meet_batch_rules / insufficient_evidence，不触发部署。Reranker 等仅作为具备证据的后续实验方向：例如有目标候选却未进入最终上下文，需要候选及选择证据；仅 Token 高不能推出“应该加 Reranker”。

## 11. 前端体验：五类核心页面

| 页面 | 最小能力 |
|---|---|
| Dashboard | 选定实验/时间范围的 Agent、Run、已启动/通过/未知数量和最近实验；不同 Suite 不混成一个全局能力分数 |
| Agents | 注册与查看版本、运行身份、Adapter、能力、校验报告；Add Agent 作为页面内流程 |
| Benchmarks | 导入平台支持的版本化清单，查看 Case、提交、测试环境、范围、验收覆盖；缺配置不能标可运行 |
| Experiments | 创建双方配置、声明比较模式、启动/取消、查看进度、配对结果、资源、证据缺口和人工决策 |
| Run / Trace | 生命周期、执行/评测分离状态、来源/完整性、Diff、Tests、内部轨迹、事实与假设、审批操作 |

接入流程：身份与版本 → Native/Process → 已有镜像及入口参数 → 能力/配置 → 无费用协议校验 → 注册为可运行。HTTP、专用 Python Adapter 等未实现类型不作为可选项展示。

Ready 只表示特定版本和环境的协议校验通过，不证明 Agent 能修复任务。Validation 包含能启动、接收请求、只写授权目录、返回合法结果、可超时终止/清理；在临时 fixture 上执行，不自动触发用户模型凭据。变更版本或运行环境后需重新校验。

复用 Vue 和现有组件；新执行控制通过 API，历史导出仍可只读浏览，明确 live/archived 来源。页面展示 Agent 所需的运行限制，避免向浏览器输出密钥、原始秘密环境或任意主机文件。

## 12. 安全、隔离和资源边界

MVP 定位为本机、单操作者、受信任注册者的研究平台，不作为敌对多租户安全服务。

- Agent 运行容器与验收容器分别管理。每 Run 独立可写源码，平台权威测试/定义/历史产物不可写；验收从停止后的独立快照执行。
- 容器非 root、去除多余 capabilities，设 CPU/内存/PID/超时限制；不挂载 Docker socket、RepoPilot 数据库、主机用户目录或 `.env`。
- 测试容器默认无网络；外部 Demo 同样无网络。需真实模型的外部 Agent 接入不属于无网络 Demo 验收，后续必须先实现可执行的网络出口策略和秘密注入，不能仅靠文档白名单声称限制了访问。
- 凭据由本机运行配置引用并按最小范围注入，不存入 Agent 配置快照、请求 JSON、Trace、报告或前端。日志脱敏并设大小上限；不承诺能识别任意自定义秘密。
- 平台控制整个容器生命周期，超时/取消停止所有子进程后再采集快照；主机上失控的任意外部进程启动不在 MVP 范围。
- 产物安全读取、Diff 范围和测试来源校验共同工作；防止被测代码作弊是持续问题，不把普通容器隔离等同于对恶意代码的完整防护。

## 13. 数据模型与持久化要求

以下为逻辑模型，不强制每个名词独立建表。先确定生命周期和唯一性，再提交迁移；避免只增加 JSON 文件却没有可恢复的运行状态。

| 模型 | 核心持久化内容 |
|---|---|
| Agent / AgentVersion | 稳定身份、不可变版本、Adapter/镜像指纹、能力、配置 schema、校验记录及时间 |
| BenchmarkSuiteVersion / CaseVersion | 版本化清单与内容 hash，提交、测试/规则及环境引用 |
| Experiment | 模式、双方配置快照、样本及重复计划、门槛、冻结 hash、启动/取消状态 |
| Run | 唯一配对槽位、版本与 workspace、执行和评测状态、检查点、时间、预算、清理状态 |
| RunEvent / Artifact | 平台序号、来源、原始调用 ID、证据引用、hash、大小、协议与脱敏版本 |
| EvaluationResult | 快照、Diff、TestRun、规则 hash、passed/not_passed/unknown 和原因 |

优先复用 Repository、TestRun、事件存储和报告服务。TestRun 当前依赖 AgentTask，v2 必须提供独立 Run 关联或明确的通用绑定迁移；禁止为外部 Agent 伪造内置计划任务。Native Run 可以保存 legacy_task_id 作为实现关联。

数据库约束保证 Run 槽位唯一、事件序号唯一、任务关联正确；终态证据不可原地覆盖。旧记录缺字段允许明确的 legacy 表达，不通过默认值伪装为新协议记录。

## 14. API 设计边界

新增 `/api/v2`，保留 v1 路由。下列为最小资源契约方向，字段 schema 在对应模块实现时确定；不一次生成所有空接口。

| 接口 | 用途 |
|---|---|
| POST/GET /agents；GET /agents/{id} | 注册逻辑身份、列表与详情 |
| POST /agents/{id}/versions；POST /agent-versions/{id}/validate | 注册不可变版本、显式执行协议校验 |
| POST/GET /benchmark-suites；GET /benchmark-suites/{id}/versions/{version} | 导入清单和查看冻结任务集 |
| POST/GET /experiments；GET /experiments/{id} | 创建草案及查看实验/配对进度 |
| POST /experiments/{id}/start；POST /experiments/{id}/cancel | 显式启动或取消，由 worker 执行 |
| GET /runs/{id}；GET /runs/{id}/events | 生命周期与按 sequence 分页的事件 |
| POST /runs/{id}/approvals | 保存具体待审批项的人工决定，关联检查点，防止过期审批 |
| POST /runs/{id}/cancel；GET /runs/{id}/report | 取消单次 Run、读取历史报告 |
| GET /experiments/{id}/comparison | 固定版本证据的比较结果，含覆盖率与规则来源 |

校验/启动等长操作返回 202 与 operation/run 引用，前端轮询即可，MVP 不强制 WebSocket。start 必须幂等，同一幂等键不同请求拒绝；取消重复请求返回已有状态。

用户输入不合法为 422，状态/版本冲突为 409，资源不存在为 404，基础设施不可用为 503；内部异常不统一映射 422。已被 worker 接受的执行错误记录在 Run 中，不能让查询接口只返回无法诊断的 500。协议错误给受控 reason_code，完整受限日志作为产物，不直接泄漏任意异常文本。

## 15. 从 v1 迁移

1. 保留 v1 数据、脚本和历史前端快照；七天阶段作为已验收基线，不重跑六条旧实验或改历史结论。
2. 提取/复用独立 Evaluation 输入模型，使平台验收不要求 Plan、Source ID 或检索存在。
3. 包装 Native Adapter，建立通用 Run 与旧 AgentTask 的明确映射，保留审批及有限恢复。
4. 实现容器 Process Adapter 与真正独立的 Demo；相同 Case 经同一 Evaluation 服务，不创建另一套评分。
5. 将 Vector/Hybrid 作为 Native Agent 的两份配置；新比较器使用模式规则，旧报告继续按原协议解释。
6. 接入 Registry、worker 和页面，脚本保留为薄入口。迁移回滚不删除已生成的历史证据；新增关联先允许旧记录为空并明确 legacy。

本文不要求一次性重构全部 services 或替换 LangGraph；Adapter 隔离实现差异，评测内核保留已验证部分。

## 16. 验收标准

| 编号 | 可核查验收 |
|---|---|
| A1 解耦 | 外部 Demo 在独立容器中运行，不 import backend.app，不调用内置计划/候选接口；仍能完成同一 Benchmark 的平台评测 |
| A2 独立判断 | Demo 自报完成但不修复时，平台测试不通过；修复后通过必需测试；伪造 Agent success 不影响评测结论 |
| A3 L0 | 不提供 usage/检索轨迹也可完成评测，页面显示缺失/不支持，Token/Cost 不填 0，不强制索引向量化 |
| A4 协议 | 缺结果、错 run_id、非法 JSON、超限、非零退出、超时、取消均保存受控错误；容器/子进程被回收，重复启动不重复执行 |
| A5 权威证据 | 修改受保护测试或越界文件被识别；使用平台测试和新容器，从冻结快照验收；不采信 Agent 自带 JUnit 作为权威测试结果 |
| A6 Native 兼容 | 现有 Agent 走 Adapter 后保留人工审批、事件和候选流程；输入相同规则时复用原验收，不绕过审批 |
| A7 模式 | 同 Agent 的 Vector/Hybrid 可声明 controlled；不同 Agent 版本可声明 benchmark；声明差异和未知分开，不能错误归因或默默忽略差异 |
| A8 批次完整性 | 预声明 Case/重复全部保留；失败、未知、准备失败与额外尝试分别展示；不筛选最好结果计算成功率 |
| A9 产品闭环 | 五类页面可注册/校验、选任务、创建/启动、查询运行、打开配对证据和决策；报告可导出再读，历史只读链路保留 |
| A10 决策诚实 | 未配门槛/价格或证据不足保持未知，人工决策不覆盖机器结论；没有自动发布或因一次提高就推荐采用 |

优先用无模型的 Demo 做异常和协议集中验收；Native 真实模型调用由用户明确启用。通过离线测试、真实容器测试、真实模型联调、页面目视验收分别记录，不混称全部通过。

## 17. 开发里程碑与推进顺序

| 阶段 | 完整小模块 | 退出条件 |
|---|---|---|
| M1 协议与评测边界 | Run/Request/Result/Capability 模型，独立评测输入与状态映射 | 内置对象不再是通用评测的必填输入，纯模拟完成 completed≠passed 验证 |
| M2 Native Adapter | 包装内置服务，持久化 Run 映射、审批/恢复和取消边界 | 原流程通过 Adapter 跑通，旧接口及历史回归通过 |
| M3 Process Adapter | 容器运行、产物解析、清理、独立 Demo | A1—A5 集中验证，外部进程确实与平台评分解耦 |
| M4 Registry 与通用实验 | 版本注册/校验、Suite 清单、模式、冻结配置、单 worker 幂等调度 | 同一 Case 的 Native/Process 和 Native 配置比较均可表达，失败样本不丢失 |
| M5 五页闭环与交付 | 复用现有 Vue 页面，补注册/创建/控制入口，统一报告及文档 | 完成第 18 节演示，更新真实验证记录和限制，可准备 v2 发布说明 |

这是依赖顺序，不预先承诺五天完成；以模块验收推进。每阶段只增加所需迁移/API，不先搭建庞大插件框架。协议错误、状态机和进程清理需有针对性测试，其余按模块集中验收，避免每几行代码就要求人工联调。

## 18. 最小演示场景

1. 注册 RepoPilot Native 版本和独立 Demo Process 版本，分别展示实际能力：Native 可提供深层轨迹，Demo 仅 L0。
2. 导入固定 task-list Case 与 8 项必需测试，记录修改前两项失败。创建 benchmark 模式实验，提前说明双方实现和人工干预差异。
3. 用户明确启动。Native 在原审批节点等待人工决定；Demo 在范围内独立修改。平台分别采集最终快照并运行同一套独立验收。
4. 在 Experiments 查看双方测试、验收、Diff、执行时间与覆盖率；Demo Token/Cost 为未知仍可评测。点击某条 Run 查看对应证据。
5. 用明确标为 fixture 的 Demo 错误版本（不修复或错误修复）验证退化和失败展示，再展示修复版本；不把故意缺陷包装成真实策略研究成果。
6. 人工根据本批证据记录继续实验或保留/采用的范围，不自动部署。后续再选实际外部 Coding Agent 扩展接入。

**v2 的关键技术证明：相同评测基础设施能够评价不依赖 RepoPilot 内置 Agent 的独立程序；不同能力深度不会阻止独立验收，也不会让缺失数据伪装成完整证据。**
