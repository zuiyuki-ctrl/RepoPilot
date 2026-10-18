# Day 6 第二模块：固定实验成对比较

2026-10-16。完成本模块，不表示 Day 6 的决策、资源分析和导出已全部完成。

## 改变了什么

此前 Experiments 页面列出了两个分组的 Run，但没有回答哪些用例改善、退化，或哪些结果根本不能比较。本模块新增 `GET /api/v2/experiments/{experiment_id}/comparison` 和页面成对结果表。

比较服务在 `backend/app/services/platform_comparison_service.py`。只读数据库中的冻结清单、Run、Evaluation、TestRun，不调用 Agent、不访问当前源码工作区，不重新运行测试。使用 PostgreSQL REPEATABLE READ / READ ONLY 事务，使一次比较中的记录来自同一数据库快照。

## 比较口径

1. 按 Case 索引与 repetition 配对，不按完成时间、列表相邻项或最佳一次结果配对。重复/缺失成员、额外尝试不静默丢弃；响应保留全部成员。
2. 核对清单 hash、目录内容 hash、实际配置变化和 controlled 模式声明。Benchmark 允许不同 Agent / 多变量配置，不强制改名为 Vector/Hybrid。
3. 对每个 Run 核对成员归属、原请求 hash、Agent 身份/配置、Case、规则、commit、编辑范围、预算、测试镜像及冻结 runner 指纹。Native 派生 runtime_fingerprint 与准备流程保持一致，不用当前代码指纹替换历史值。
4. 对终态 Evaluation 按版本 1 规则核对其内容 hash、结果与 Run 一致性、测试 ID、TestRun 所属及保存的测试字段。多个 Evaluation 不挑选“最好一个”。两边初始源码 hash 不同不可比。
5. 两边均已启动、准备完成、终态明确且证据核对通过，才分为 improved / regressed / both_passed / both_not_passed。进行中、unknown、缺失评测或未启动为 undecided；条件或证据冲突为 non_comparable。

这是**已保存自动测试结果的证据核对**。不重新验证磁盘上的 Diff 字节、不证明完整 Trace、不做根因推断。数据库中相互一致的记录不等同于不可篡改外部审计凭证。

## 分母与示例

- 每组分别显示计划数、成员数、已启动数、未启动数、准备失败数、核验通过数和已启动待定数。准备失败是未启动的子集，不应相加为总数。
- API 的 observed_pass_fraction = 已核验通过 / 全部已启动；进行中和缺证据的已启动 Run 仍在分母。这是当前已知通过占比，不是忽略未知结果后的最终成功率。无已启动记录为 null，不是零。
- paired_pass_delta_percentage_points =（改善对数 − 退化对数）/ 可比对数 × 100；必须同时展示计划/可比数及排除项，无可比对子为 null。
- 实际 noop/fix fixture：baseline 未通过、candidate 通过，因此 1 对改善、描述性差值 +100 个百分点。这里只有一个玩具用例，不代表通用 Agent 提升 100 个百分点，也不能支持发布建议。
- 整批执行前取消：两组各有一个未启动成员，没有可比对子；不是双方失败，也不计算为 0% 成功率。

comparison_sha256 绑定本次投影结果，observed_at 不参与内容 hash。因此相同证据重复读取 hash 相同，正在运行的数据改变时 hash 改变。本模块没有把比较结果持久化成不可变导出快照；不能把此接口当成已经完成的历史报告导出。

## 验证

- Day 1—6 **113 项离线回归通过**，新增比较测试文件 17 项（含子用例），覆盖四类明确结果、未启动/准备失败、进行中、unknown、缺失/多条评测、错误测试归属/内容、清单/请求冲突、重复/缺成员、重复次数错配、Native 派生配置、controlled 声明及 hash 稳定性。禁用 dotenv/外网，数据库、模型、Docker 均不真实调用。
- 前端类型检查与 Vite 构建通过，未新增依赖或数据库迁移。
- 真实 DB 只读 TestClient：实验 `12955175-7643-45d4-9f18-8dfdf149e58d` 返回 1 对可比/1 次改善；实验 `e2cd826e-7574-4573-b7b6-2c609186be77` 返回 1 对待定、两组 started=0。两者重复读取内容 hash 一致。没有重新运行容器、模型或 Embedding，没有修改历史记录。
- 浏览器验收待用户：打开 Experiments 中已有 `Day5 noop vs fix fixture`，下方应出现成对比较和 Run 证据链接。无需创建新实验。

## 后续

本模块完成时资源比较、冻结发布门槛、独立人工采纳记录、历史导出尚未实现，接口当时显式返回 not_assessed / null。

2026-10-16 接续：第三模块已接入冻结质量门槛与独立人工决定，见 [门槛与人工决定](v2-day6-decisions.md)。比较 hash 现在包含系统质量判定，旧比较展示 hash 可能因此变化；已有 Run/Evaluation 原始记录不改写。资源比较和完整历史导出仍待后续。
