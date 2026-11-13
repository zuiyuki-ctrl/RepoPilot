# 自动生成评测题草稿

## 用途与边界

从已登记的固定 Git 提交、源码和已知失败的验收测试生成 `bug_fix` 题面。它是题库的**创作入口**，不是自动修复入口：不创建 AgentTask、PlatformRun 或 Experiment，不修改仓库，也不更改验收测试。

```text
已登记仓库 + 用户选择 → 本地文件预览 → 用户授权 → 持久 worker
    → 固定容器失败基线 → 无工具模型生成 → 人工编辑/确认
    → 现有 BenchmarkRegistration → 现有 CatalogValidation → 实验可选
```

只有草稿作业存入新增 `case_drafts` 表；正式 Case 仍嵌在现有不可变 Benchmark / Suite descriptor 中，没有第二套题库或评分器。第一版确认时创建一个单 Case 的 Suite 版本；不追加或覆盖已有不可变 Suite。题名保留在正式 `Case.user_request` 的首行。

## 启动准备

1. 核对数据库目标与备份后，在仓库根目录执行 `python -m alembic upgrade head`。新增迁移为 `d1113a01b001`；不会由 API 自动迁移。非空草稿表禁止直接 downgrade，避免丢失授权和基线证据。
2. 按 README 启动 FastAPI、数据库、前端。仓库须已登记，有固定的 40 位提交、干净独立副本；第一版不切换提交。需要不同提交时先登记对应副本。
3. 使用现有 `python-basic` 测试镜像，例如 `repopilot-pytest:py311`，用 `docker image inspect repopilot-pytest:py311` 查看完整 `Id`。填写 `sha256:…` 而不是 tag；镜像必须已在本机，不自动拉取。范围沿用 v2 Python profile：有界的 `.py/.md/.txt/.gitignore` 仓库、独立测试模块，无本地 conftest/plugin、虚拟环境或其他配置发现。
4. 模型复用已有 `CHAT_MODEL`、`CHAT_BASE_URL`、`DASHSCOPE_API_KEY` 与 `request_tool_turn` / `ModelObservation`，不是 Run 专属网关授权。不要在页面填写凭据。
5. 生成前检查现有队列，然后在独立终端启动 `python -m scripts.platform_worker --allow-model`。此开关也会允许队列中已授权的 Native 模型工作，不是仅授权当前草稿；单 worker 按现有 Run、Catalog、Preparation、Draft 顺序处理。不带开关的 worker 不领取草稿。

## 页面操作

1. 打开实时 **Benchmarks → 生成评测题**，选择仓库。页面显示其登记提交，不提供任意 checkout。
2. 勾选相关源码和受保护测试文件，二者不能重叠。最多 30 个源码、20 个测试文件，发送内容合计最多 120 KB。
3. 声明验收测试项，每行 `classname::name`，例如 `tests.test_task_list::test_filter[open]`。从已有 JUnit 报告复制精确标识；参数化后缀和类名必须完整。这里不运行用户源码猜测测试名。从这些项中勾选至少一个预期失败项。
4. 输入不可变测试镜像 ID，可补充业务背景，点击 **预览将发送的文件**。展开可查看发送文件全文、大小和 SHA256，核对模型与目标地址。模型只接收选定源码、测试、背景和声明的验收项，不接收其他仓库文件、运行日志或凭据。
5. 分别勾选模型发送和隔离测试授权，再点 **授权并生成草稿**。输入发生变化会撤销预览与勾选；后端会再次校验快照、选择、模型配置和运行器指纹。确认前没有正式 Case。
6. 页面每两秒查询当前任务，显示排队、基线校验、模型生成、失败或可确认。关闭页面不会终止持久任务；重新打开可在最近 30 份草稿中恢复查看。失败时展开基线证据可看实际失败项、未收集项、额外失败项和受限日志。不会自动重试付费请求。
7. 基线通过后可修改题名、题面和允许修改范围。范围只能是已授权源码的非空子集；测试和提交不可改。**先保存草稿编辑，再确认**。要改变输入或失败声明需新建草稿并重新授权。
8. 输入 Suite 名称/版本、Case ID/版本，点击 **确认保存并校验 Benchmark**。注册、确认和排队环境校验在同一事务内完成。关闭抽屉后刷新版本列表，等待 `ready` 再用于实验；`confirmed` 本身不是可用标记。可在排队前/生成后丢弃未确认草稿，执行中需等完成或显式恢复。

## 基线与安全规则

- 与正式 Run 共用 `platform_test_collector.run_authority`、`assess_baseline`、受保护测试挂载和 JUnit 完整性解析；不是新评分器。草稿增加更严格的**实际失败集合等于预期失败集合**要求，正式 Run 原有门槛保持不变。
- 测试在无网络、只读源码与 authority、固定资源限制的容器运行，超时 120 秒。模型既不能提供测试命令，也不能选择提交、测试或验收规则。语法/导入错误、skip、缺少测试、全通过、额外失败、无效报告都不能成为可确认草稿。
- 模型仅返回 `title`、`user_request`、`editable_files`，严格拒绝多余字段、重复 JSON 键、越界路径、未选文件、测试文件和明显补丁/代码块。题面是否准确、是否泄露过多解题思路仍需人工审阅，不能声称语义已自动证明。
- 保存后复用现有环境校验，并将草稿的快照、运行器与镜像证据对照当前环境；变化会使 Benchmark 无效。实验准备仍按原流程重新检查与运行基线。
- 权限维持本机可信操作者 MVP 边界，不新增公开远程多租户认证。不要把后端未经鉴权暴露到公网。

## 中断与恢复

与 Catalog/Run/Preparation 共用全局执行栅栏。容器清理不能确认时保留 token、标为 `interrupted`；进程崩溃可能停留在 validating/generating，同样保留所有权。不会重放模型请求。

确认 worker、模型请求执行进程和容器写入者已停止后，使用 worker 日志里的草稿 ID 与 token：

```powershell
python -m scripts.platform_worker --recover-case-draft <UUID> --token <UUID> --confirm-writers-stopped
```

恢复会检查并清理该草稿拥有的基线容器，置为失败，不删除历史证据。不确认停止写入者时不得清理栅栏。要再次生成需新草稿、新预览和新授权。

## 验证与兼容性

```powershell
python -m pytest -q tests/test_case_drafts.py tests/test_platform_day2.py tests/test_platform_day3.py tests/test_platform_day4.py tests/test_platform_day5.py
# frontend 目录
npm.cmd run test:case-drafts
npm.cmd run typecheck
npx.cmd vite build
```

测试覆盖正常基线/生成/编辑/确认、注册前无 Case、幂等确认、非法模型字段与路径、未授权、快照改变、失败声明不符、无法运行/超时、丢弃、过期编辑、中断栅栏及迁移离线 SQL。测试 mock 模型、Docker 和存储；真实 PostgreSQL 事务、Docker 挂载与模型供应商仍需部署环境联调。

2026-11-13 本机验证：草稿测试与 `test_platform_day1` 至 `day7`（含 day6 的 comparison / decision / resources）合计 **178 passed、63 subtests passed**；前端草稿与资源逻辑测试 **8 passed**，`vue-tsc --noEmit` 与 Vite 生产构建通过。存在既有测试收集/弃用警告，无失败。未执行实际数据库迁移、真实模型请求、真实 Docker 基线或浏览器端到端联调；不能把 mock 通过视为供应商效果证明。

本次提取共享 collector 函数改变了运行器实现指纹。**历史报告不重写**；旧冻结实验/运行包不能假装运行器未变。升级后若提示 runtime/environment/bundle changed，请重新校验并新建实验版本，不复用旧冻结包。
