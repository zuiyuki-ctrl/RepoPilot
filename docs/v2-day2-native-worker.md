# Day 2：Native Adapter、持久 worker 与审批检查点

2026-10-15：代码及集中离线验证完成；新迁移、真实 PostgreSQL 并发、真实 worker/模型及新审批页面浏览器验收尚未执行。Day 1 页面连接已由用户反馈通过。

## 执行链路

```text
绑定 fresh AgentTask 的通用 Run
→ prepare（配置和初始 Python 快照检查）→ plan
→ 等待计划审批 → review_plan → begin
→ generate → 等待候选审批 → apply
→ 若还有文件，逐个重复生成/审批/应用
→ execution completed / lifecycle evaluating / evaluation pending
```

Native Adapter 复用已有服务，不重写 Agent 图。计划不能超出冻结 editable_files；候选应用仍检查 base_file_hash 和 Python 语法。拒绝候选不写该候选，也不自动撤销先前已批准的文件。本日没有自动 Reflection 重试。Day 3 接通独立权威测试，不能把旧任务 completed 或旧 task_id 的 TestRun 当成新 Run 通过。

## 两个新表的作用

- RunWork：下一步做什么、步骤状态、累计活跃时间、取消请求、执行 token 与清理结果。
- RunCheckpoint：需要批准的完整计划/候选、hash、版本及人工决定。

例如候选 A 已生成，刷新页面从检查点读回 A；批准后 worker 应用 A，不再请求模型生成 B。重复相同决定返回原记录；过期版本、不同内容或改成另一决定返回 409。检查点决定、调度状态及事件在一个短事务保存。

`agent/adapters/base.py` 定义 metadata/prepare/run/cleanup；`native.py` 了解旧任务和计划，通用 worker 只了解阶段结果。API 只登记人工决定，模型和文件写入在独立 worker 子进程执行，等待模型不持有 ORM 行锁。

## 页面与接口

在现有 Run 列表/详情/事件读取外，新增：

| 接口 | 用途 |
|---|---|
| GET `/api/v2/runs/{id}/control` | 当前步骤、清理状态和最近检查点；没有 worker 绑定返回 null |
| POST `/api/v2/runs/{id}/checkpoints/{checkpoint_id}/decision` | expected_version、payload_sha256、decision、comment；只登记决定 |
| POST `/api/v2/runs/{id}/cancel` | expected_version；幂等登记取消 |

结构错误 422，状态/内容冲突 409，不存在 404，数据库错误 503。内部模型错误由 worker 记录，不映射用户 422。live 页面显示完整审批正文、批准/拒绝、取消及清理问题；阅读待审批内容时不自动替换，批准后轮询等待 worker 领取。

已绑定 v2 Run 的旧任务 HTTP 写接口返回 409，GET 保留。旧 CLI/直接 Python 服务仍是可信内部入口，本机操作者不得另行使用它们或手工修改 v2 工作区；本期不是任意主机代码的权限沙箱。每条 Run 必须使用独立注册的工作副本。

## 启动与恢复

先停止旧 worker（若存在），执行一次迁移：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

新 head `d714a02b0001`，父 revision `d714a01b0001`。有新表记录时降级拒绝销毁证据。

无模型的单次领取检查：

```powershell
.\.venv\Scripts\python.exe -m scripts.platform_worker --once
```

持续 worker 去掉 `--once`。不带 `--allow-model` 不执行 plan/generate；已批准的候选应用不需要模型。真实规划/候选调用由操作者显式加 `--allow-model`，助手本轮没有运行。

模块开发入口 `scripts.enqueue_native_run` 接受可信平台生成的 AgentRunRequest JSON、repository_id、新的 created plan task_id 和 creation_key。它只入队。config_sha256 对应旧任务完整 AgentRunConfig；agent.implementation_sha256 来自 NativeAdapter.metadata；initial_snapshot_hash 用现有 Python 快照算法。不要手填虚假指纹或借用已完成的历史任务。正式页面创建/冻结入口留 Day 4—5。

PostgreSQL session advisory lock 保证单 worker；每个阶段还有持久 active_token。等待审批释放执行槽位，其他 Run 可以推进，恢复再领取。活跃时间不包括人工等待；max_tool_calls 对应现有规划工具预算，未实现的 Token 硬预算明确拒绝。

正常重启继续已提交的准备状态或审批决定。若旧阶段还留有 active_token，队列拒绝继续；无法区分“调用未完成”和“已完成但没落盘”，所以不按心跳超时自动重放。终端记录 Run ID、子进程 PID 和 token。

执行中取消/超时会停止子进程，但强制停止可能落在文件写入与 DB 提交之间，也不能仅凭父进程退出证明所有子孙进程清理。此时显示 interrupted/unknown，保留阻塞 token。先停止旧 worker 及子进程并检查工作副本，确认无写入者后才能执行以下形式：

```text
python -m scripts.platform_worker --recover-run RUN_ID --token STEP_TOKEN --confirm-writers-stopped
```

恢复需要独占 worker 锁，只把旧 Run 固定为 interrupted/unknown 并解除阻塞，不继续旧 Run、不重放。`operator_confirmed` 明示操作者确认，不冒充自动进程验证。不得对仍运行的子进程使用此选项。

## 证据及验证范围

每个阶段结算时把 TaskEvent 映射到 RunEvent，保留 task_id、legacy_sequence、node_name、原 payload，由平台分配新 sequence；游标和事件同事务保存。已接入模型、Embedding、工具、检索、实际准备上下文及计划事件，但先标 partial，不推测完整调用总数或 L2。原 payload 保存在后台，本日页面显示元信息和审批正文，完整 Trace 投影与覆盖率由 Day 6 汇总；未发生 Reflection 不补造。

集中回归 135 项：134 通过，1 项 Windows 符号链接权限用例跳过；含 Day 2 新增 20 项。验证暂停/恢复、相同审批幂等、冲突、取消、配置/快照漂移、事件游标、未决步骤阻塞、恢复不重放及清理错误单列。DB/模型/进程调度为模拟，迁移 SQL/DDL 离线检查、单一 head 确认；前端类型检查和生产构建通过。

没有读取真实 Key、运行付费请求或改写历史实验报告。真实新迁移、数据库并发、真实进程清理和浏览器审批仍待集中联调。后续只需围绕一条 Run 验证“计划暂停 → 候选暂停 → 应用后待独立验收”，再配一条取消/中断支线，不重跑历史六条实验。
