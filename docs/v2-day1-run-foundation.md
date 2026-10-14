# v2 Day 1：通用 Run 与独立评测基础

实现日期：2026-10-14。本日实现内部创建/状态/评测服务和只读 API，不执行 Agent。Native Adapter、实际 worker、容器采集器、注册和实验启动留到后续模块。

## 具体改变

原来 TestRun 必须关联内置 AgentTask，验收读取 TaskExecutionReport。现在增加独立的 PlatformRun、PlatformRunEvent、RunEvaluation，外部程序无需伪造内置计划。

TestRun 保留 task_id 并新增 run_id，通过数据库 XOR 约束保证恰有一个所属对象。原 v1 记录继续 task_id 非空；新 v2 测试使用 run_id。Native 之后通过 PlatformRun.legacy_task_id 关联旧业务任务，不能直接把旧 task TestRun 当成新的 Run 证据；转换/执行路径由 Day 2 明确处理。

运行阶段、Agent 执行结果、评测结论分别保存。例如 lifecycle=finished、execution_status=completed、evaluation_outcome=not_passed，表示程序正常结束，但平台验收失败。started_at 仅在进入 running 时填写；准备失败/排队取消不伪装为已执行。

## 协议与观测

- `schemas/platform_run.py`：固定逻辑 workspace、可修改相对路径、Agent 实现身份、预算及规则/配置/环境/初始快照指纹；AgentRunResult 不接受 success 或评测字段。
- `run_observation_service.py`：九项固定能力，逐项记录声明、校验、实际可用性、是否发生、来源和事件引用。后端推导层级，前端不自行计算。
- L0 需要 execution/tests/diff 的完整证据；L1 还需 model_usage/tool_trace；L2 再需 retrieval/context/planning/reflection。条件阶段可凭明确事件记录为 not_occurred；无法确认发生与否为 unknown，不能由缺日志推断没有执行。
- available 必须有事件引用；升级层级还要求已知应有记录数与实收数一致。应有调用数未知时不计算完整覆盖。声明更深层能力但证据不齐，摘要标 partial。没有运行数据时 level=unknown，不默认 L0。
- `record_capabilities` 核对引用确实属于当前 Run；Day 1 没有自动映射原 Agent 轨迹，Day 2 的 Adapter 负责产生有语义的证据。协议校验不是对外部自报数据真实性的证明。

## 独立评测与事务

`platform_evaluation_service.evaluate_run` 接收平台内部 EvaluationInput，不依赖 Plan、Source ID 或检索。它复用既有 JUnit 解析校验，对比 TestRun 归属、快照、测试环境、必需测试、基线失败和工作区约束。

`finish_evaluation` 锁住 Run，核对冻结 Case/规则/环境、执行状态和数据库 TestRun 内容；在一个短事务里保存不可覆盖的评测输入、结论、终态及事件。同一证据重放返回已有结果，已完成 Run 不接受另一份证据覆盖。手工语义标准当前保持 unknown，尚未实现 v2 人工验收记录入口。

**这仍是平台可信采集器的内部接口**：writers_stopped、Diff 和保护检查由后续平台采集器填写，不接受 Agent 的 HTTP 提交。Day 1 没有实现进程停止、真实 Diff 采集或权威测试隔离；纯输入通过不等于这些真实能力已验收。

`create_run` 按创建键和请求指纹幂等；状态变更用行锁加 expected_version 防止过期恢复。`claim_next_run` 仅为 SKIP LOCKED 原子领取原语，不代表全局并发控制或持久 worker 已实现。Day 2 必须补执行所有权及重启恢复，不能直接用此原语启动多个无协调 worker。

## 最小页面和接口

- GET `/api/v2/runs?limit=20&offset=0`：只读列表。
- GET `/api/v2/runs/{id}`：通用状态与观测能力。
- GET `/api/v2/runs/{id}/events?after_sequence=0&limit=50`：按平台序号分页，Day 1 只公开事件元信息，不转发任意 payload 或秘密配置。
- 参数错误 422，未找到 404，数据库/迁移不可用 503；内部协议 ValueError 不包装成用户输入错误。

Vue 新入口为 `#/live/runs`，详情为 `#/live/runs/{id}`；旧 `#/experiments`、`#/comparisons`、`#/runs/{experimentId}` 仍读 archived 快照，不混入新运行。前端 dev/preview 的 `/api` 默认代理到 127.0.0.1:8000；生产部署需配置同源反向代理，Vite 构建不会部署 API。

## 用户集中验收（无模型调用）

1. 在项目根目录执行 `.\.venv\Scripts\python.exe -m alembic upgrade head`，再执行 `alembic current`（同一虚拟环境）确认 head 为 `d714a01b0001`。迁移增加三张表及 TestRun 所属约束；有 v2 数据时 downgrade 会拒绝销毁证据，不能强制删除表。
2. 重启 API：`.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --reload-dir backend`。在 frontend 目录运行 `npm.cmd run dev`，点击“实时运行 · v2”：应显示后端已连接，首次无 Run 时空列表正常；切回历史页面仍可查看原记录。

这两步验证真实迁移与最小读取链路。非空运行、真实审批和执行由后续模块验收，不为让页面有数据而把模拟结果写入真实实验数据库。

建议亲自理解的一点：为什么测试记录要有明确且唯一的所属对象、为什么 execution completed 不等于 evaluation passed。面试时可以用“外部程序返回 0，但必需测试失败”解释这两个设计，无需为了学习重新手写本轮所有 CRUD。
