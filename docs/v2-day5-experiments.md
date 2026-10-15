# Day 5：固定版本实验与批次调度

2026-10-15。当前模块把 Day 4 的版本目录接入正式 Run 管线：预览 → 显式确认 → 持久准备队列 → 独立工作区 → 基线 → Agent → 审批（Native）→ 平台验收。

## 这次弥补了什么

此前只能逐条用 CLI 准备 Run，两个结果是否属于同一实验、顺序和预算由操作者管理。现在一次选择 Suite、Baseline/Candidate 版本、重复次数、预算和计划顺序，平台冻结完整 manifest/hash，并保存每个计划成员。

例如一个 Case、两个 Agent、重复两次，启动前明确显示 **4 个 Run**。即使第三个成员准备失败，也保留为 preparation_failed；不会从列表里消失，也不会被算作已经执行的 Agent 失败。重复提交同一启动请求键，只返回原实验，不多创建四个成员。

controlled 模式要求实际执行配置差异与 changed_fields 精确一致；无差异、未声明差异、不同适配器、不同实现/镜像/能力的比较不会被伪装成单策略受控实验。多变量用 benchmark。名称/版本标签本身不作为策略差异，但仍完整保存身份。当前 fixture 的 noop/fix 结果只是协议管线验收，不是策略提升结论。

## 实现与边界

- `schemas/platform_experiment.py`：预览/启动契约，1～5 次重复、1～3600 秒 Agent 预算、两种计划顺序；每批最多 40 个 Run。干预方式固定为 adapter_default（Native 人工审批计划及每个候选，Process 无人工改写）。
- `db/models/platform_experiment.py`、迁移 `d715a05b0001`：PlatformExperiment 保存不可变快照及取消状态；ExperimentMember 保存顺序、Case 序号、重复轮次、分组、准备 token、Run 关联与失败类别。本机迁移已执行。
- `platform_experiment_service.py`：预览实际差异、冻结目录内容及校验证据、测试运行器指纹、Native 索引内容指纹；启动请求键幂等。预览到启动发生变化时拒绝旧 hash，要求重看预览。
- `experiment_preparation.py`：在 worker 中重新验证源文件/commit/镜像。Process 每次由 collector 创建独立无 .git 副本；Native 每次克隆独立注册仓库、复制已核对源码 hash 的现成索引与向量，并创建 fresh plan task。不会自动 Embedding；索引缺失/过期/模型不匹配时准备失败，须操作者事先显式准备。部分失败的文件/仓库保留供排查，不自动删除。
- 沿用 `platform_worker` 的全局并发 1：优先已有 Run 阶段，其次目录校验，再取批次准备。Run/校验/准备的未清除 token 互相阻塞。每阶段/每个成员的时间与 Run 事件保留；审批等待释放执行槽，实际顺序可能偏离计划，不假装严格实验随机化或公平调度。
- 准备与取消结算用同一事务锁协调，准备中接受取消不会漏掉刚创建的 Run。整批取消幂等；已进入 evaluating 的平台评测继续收尾。单 Run 取消/审批复用详情页原入口。
- 模型调用双重显式开启：启动 Native 实验时 allow_model=true，运行 worker 时还需 --allow-model。助手本轮未启用。Process 无网络、无模型凭据，启动不会暗中下载镜像。

准备中崩溃不自动重放。停止 worker、确认旧准备进程与写入已停止后，凭日志或实验详情里的 member ID/token 恢复：

```powershell
.\.venv\Scripts\python.exe -m scripts.platform_worker --recover-preparation <成员UUID> --token <token> --confirm-writers-stopped
```

恢复检查其容器清理，关联已创建 Run 并请求取消，成员保持 interrupted；不继续旧准备。正常完整阶段之间可以安全重启 worker，未清除 token 的非正常中断则必须显式恢复。

## API / 页面

| 接口 | 功能 |
| --- | --- |
| POST /api/v2/experiments/preview | 只读预览：Run 数、实际差异、付费阶段、快照 hash |
| POST /api/v2/experiments | 确认 hash、request_key、confirm_start、allow_model 后入队；202 |
| GET /api/v2/experiments | limit/offset 实验列表 |
| GET /api/v2/experiments/{id} | 冻结清单、成员、Run 状态、准备失败与时间 |
| POST /api/v2/experiments/{id}/cancel | 幂等取消剩余执行，不改写已有成绩 |

侧栏 **Experiments · 批次运行** 可以选择已校验版本、生成预览、确认启动、每五秒查看当前实验进度、取消整批并进入 Run 详情审批/单次取消。修改表单后必须重新预览；启动使用页面展示的那份冻结预览。页面列表只展示最近记录，完整历史通过分页 API 读取。

可选发布门槛输入及自动决策判定本日未接入，留 Day 6 的比较/决策模块；当前 settled 只代表批次成员终止，不代表发布条件达标。当前只支持 Suite 全部 Case，若需子集，登记新的有序 Suite 版本；不在启动时悄悄删减原清单。

## 本轮验证与待确认

- Day 1—5 **87 项离线回归通过**，其中 Day 5 新增 12 项：差异声明、派生运行指纹不算策略变化、Ready 条件、内容漂移、旧预览拒绝、启动幂等、Native 授权、预算边界、准备失败保留、清理不确定保留 token。数据库、Docker 为模拟，禁用 dotenv 和外网。测试日志中的异常为注入场景。
- 前端 TypeScript 检查与生产构建通过。
- 真实 PostgreSQL/API：同请求键重复启动返回同一实验；同键不同请求 409；整批重复取消 200，未准备成员保留 cancelled 且无额外 Run。
- 真实无模型 Demo 批次：实验 `12955175-7643-45d4-9f18-8dfdf149e58d`，Baseline Run `b3f3d478-c18c-44ea-8469-5a576edb3534` 为 completed/not_passed，最终 2 failed / 6 passed；Candidate Run `4e80105a-08e0-449e-8677-0c9c5144456d` 为 completed/passed，最终 8 passed。实验 settled，Docker 无 repopilot-v2 容器残留。结果导出到本机 `result.json`。
- 取消实验 `e2cd826e-7574-4573-b7b6-2c609186be77` 的两个计划成员均 cancelled，无 Run。使用 `--once` 在阶段之间退出/重新启动 worker，持久队列继续运行；这不等于强杀活动容器后的恢复已真实验证。
- 用户浏览器初次请求 agents/benchmarks/experiments 返回 404。实际检查 8000 端口的 OpenAPI 只有旧 runs 路由，而源码已注册新路由，确认运行中的 API 尚未重启；已给出使用项目 .venv 重启 uvicorn 并仅监听 backend 的命令。重启后的页面反馈待确认。浏览器新创建/启动/审批操作、Native 真实模型批次、非正常进程崩溃恢复尚未真实验证；不将模拟测试说成已联调。

本机验收资料在 `.platform-artifacts/day5-acceptance-20261015/`，不随 Git 跨机。页面简短验收：查看上述真实实验 → 查看两成员执行/验收结果并进入 Run 详情 → 刷新确认历史与冻结清单仍存在。新的完整浏览器启动可用同样两版本新建实验，勿误点允许 Native 费用。

重启后补充：助手实际请求 8000 端口 agents、benchmarks、experiments 均返回 HTTP 200；用户随后确认页面刷新正常。新页面刷新与展示验收通过；不把该反馈扩展为浏览器内新建/启动/取消所有操作或 Native 真实模型批次均已验证。

下一模块 Day 6：把这些固定实验与 Run 的观测覆盖率、资源、失败和比较/决策连接起来，不重复搭建执行器。
