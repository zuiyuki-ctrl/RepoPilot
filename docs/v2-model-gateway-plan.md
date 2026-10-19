# 真实外部 Agent 模型网关实施计划

日期：2026-10-19。状态：A、B1 与 B2 限定范围检查点已通过；B3a 固定供应商协议、假上游响应/usage 与账本结算完成，最新集中回归 277 passed、63 子测试通过。生产入口仍为 mock-only。下一步 B3b：供应商级出站隔离、可信密钥挂载及假上游容器验收；尚未进入 C。此前 Docker 16 项基础 + 62 项故障检查对应 B2 镜像，不代表本轮新代码已通过容器验收。未迁移现有业务库、未调用真实模型。延续 v2 平台，非重建 Agent 框架。

## 1. 目标与范围

让独立 Process Agent 能通过平台访问真实模型，每次调用绑定 Run、授权和预算，留下平台采集的请求证据。最终用于展示“有缺陷的 Agent → 观察失败 → 修改 Agent → 固定任务对照实验”，不再以离线 noop/fix 代替真实模型能力。

首版仅支持现有聊天供应商的非流式文本 Chat Completions 子集，以及小型 Python Agent。模型和允许参数在实验前冻结，不允许 Agent 自选上游 URL、凭据或任意透传请求头。工具调用参数是否纳入首版以 MiniFix 所需为准，未支持字段明确拒绝。供应商参数需在实现时核对官方协议。

本阶段不做价格系统、多供应商、流式、多模态、通用外网工具、完整 L2、自动根因分析。Native 继续使用原路径；不把它的历史调用声称为网关采集。离线 Process 和既有报告必须保持兼容。

## 2. 接入设计与控制边界

目标拓扑：`Agent 容器 → 专用模型网关 → 固定供应商`。Agent 只连接内部隔离网络；网关连接内部网络和受控出站网络，不把平台业务 API、数据库、宿主服务或 Docker socket 暴露给 Agent。网关不提供任意 HTTP 代理，只转发已校验的模型请求。基线/最终测试容器仍用 `--network none`。

这是目标设计，不是已经验证的 Docker 隔离结论。先用本机 Docker Desktop 做无模型网络探针，确认 Agent 可访问网关、无法绕过网关访问外网或宿主服务。未通过不得回退到 host 网络或普通可出网 bridge。网关部署/控制通道在这个检查点确定，供应商 Key 只在可信网关侧，不能进入 Agent 镜像、参数、Trace 或导出文件。

每个执行尝试发放短期 Run 凭证，与 Run ID、worker 所有权 token、配置 hash 和截止时间绑定；服务端只持凭证摘要，明文通过独立只读挂载交给该 Agent，结束后撤销并清理。凭证不是供应商 Key，也不能调用业务管理接口。请求体里的 Run ID 不作为身份依据。

所有请求同时满足：实验/可信独立入口显式授权、worker `--allow-model`、当前执行所有权有效、Run 正在 Agent 执行阶段、未取消/到期、预算足够。目录协议校验使用无模型 probe，不能因用户点击“校验 Agent”产生费用。独立 CLI 入队入口也必须校验授权，不能只保护前端实验路径。

## 3. 调用账本、预算与证据

预计新增 Run 模型授权/额度记录和模型调用账本（名称在实现时确定）。记录配置/请求 hash、幂等调用 ID、状态、实际 usage、时间与受控错误；必要内容存有界产物引用，不把全文塞进普通日志。现有 RunEvent 关联调用账本，避免网关记录和 Agent 自报重复计数。

短事务原子完成鉴权、预算占用和调用登记；网络等待不占数据库行锁。首版每 Run 最多一个在途请求。相同调用 ID、相同内容返回原结果或在途状态；同 ID 不同内容冲突。已向供应商发出后遇超时、断线或进程中断，标记结果未知，不自动重发，不释放可能已经消耗的调用额度。重启不得绕过账本重新消费。

硬限制：每 Run 调用次数、请求字节/消息数量、单次输出上限、单次及执行截止时间。失败的真实尝试也计调用次数；重复获取结果不重复计费请求。Run 总 Token：优先采用可验证的供应商计数/适用 tokenizer 上界，能做可靠预留才声明 enforced；否则明确 advisory，记录实际 usage 并在超限或 usage 缺失时停止后续调用，不把字符数当精确 Token，也不声称保证总费用。

取消/超时后拒绝新请求并撤销凭证；已被供应商接收的请求不保证立即停止或不收费。迟到结果保留到账本，不恢复 Agent 执行、不改变取消终态。明确“受理在取消之前”的在途边界，不承诺跨网络绝对同步撤销。

保存实际转发的模型、允许参数、消息内容的有界证据及完整 hash、调用状态、耗时和供应商 usage；不保存鉴权头、原始敏感异常或 Key。内容截断与缺失明确展示。平台知道的是经过网关的请求，Agent 内部检索/上下文选择仍属自报；本阶段不凭 hash 自动宣称 L2 完整。

## 4. 四个实施模块

| 模块 | 完整交付内容 | 验收重点 |
| --- | --- | --- |
| A · 授权和契约 | Process 可选模型配置、冻结模型策略、授权与调用账本迁移；兼容旧配置 hash | 外部模型也需要 API/worker 双授权；离线配置仍可用；预算/幂等并发检查 |
| B · 网关和运行器 | 专用网关、短期 Run 凭证、隔离网络、固定上游、取消/清理/恢复联动 | Mock 上游真实容器调用成功；跨 Run、绕过网络、过期请求拒绝；测试继续断网 |
| C · 观测和页面 | 网关调用映射 Trace、资源去重、实际请求证据；配置/预算/异常展示 | 不重复计算自报 usage；未知不记零；可以从 Run 查看一次真实转发内容 |
| D · 集中使用验收 | 独立最小外部 Agent 示例、接入说明、无模型异常回归，再由用户触发少量真实调用 | 真实生成修改 → 独立测试 → 查看 Trace/Diff → 导出；失败仍可追查 |

已核对的关键修改入口：

- `schemas/process_agent.py`：当前没有模型策略；新增字段必须避免改变旧登记的规范化 hash。
- `platform_experiment_service.py`：当前 needs_model 只检查 Native；拆成“需要模型”和“需要 Native 索引”，不能让外部模型 Agent 被迫做 Embedding。
- `run_worker_service.py`、`run_control_service.py`、`experiment_preparation.py`：补所有入队/领取路径的授权和所有权绑定，不以 adapter 名称代替授权。
- `platform_container.py`、Process Adapter 与目录校验：区分在线 Agent、离线 probe、平台测试；增加网关/网络清理及未确认清理时的恢复边界。
- Trace/资源/比较服务：识别平台采集来源、记录真实请求覆盖、保持历史数据不补造。

先做 A；B 的网络探针是继续真实接入的检查点。每个模块结束做针对性离线检查，整条链路接通后集中验收，不要求用户每写一个函数就测试。

## 5. 完成标准与接续

集中验收只分三组：①模拟上游验证协议、额度、重复请求、取消及未知结果恢复；②真实 Docker 验证隔离、调用和清理；③用户明确开启真实模型，运行一个小任务并从前端查看证据和独立验收。第三组不预先要求 Agent 修复成功，要求结果真实且可解释；费用调用由用户执行。

完成后可表述为“支持协议适配后的外部 Agent 通过受控网关调用指定真实模型”。不能表述为“任意 Agent 零改动接入”“完整 L2 自动观测”或“严格费用上限”。随后再构建上下文截断缺陷 Agent 和修复版，开展固定任务的对照演示。

初次整理本计划时只写了文档。以下为随后实际实施记录，以记录的验证范围为准。

## 6. 模块 A 实施记录（2026-10-19）

已实现：

- `schemas/model_gateway.py` 定义冻结的 `ModelPolicy`：供应商固定 DashScope，模型名显式指定为 Qwen 系列；文本、非流式、关闭思考，不开放 tools、多模态、任意 URL/请求头。策略包含 temperature、单次输出上限、调用次数、消息/字节限制、超时和 advisory 总 Token 阈值。
- `ProcessConfiguration.model_policy` 可选。未设置或为 null 时序列化省略该字段，旧配置和嵌套 Agent 登记的规范化 hash 保持不变。
- 实验 `needs_model` 现在包含在线 Process；Native 索引检查单独判断，不会因为外部 Agent 需要模型而调用 Embedding。旧 manifest/报告不重写。
- 实验启动的 `allow_model` 传到准备/入队；独立 `scripts.prepare_platform_run` 新增 `--allow-model`，默认禁止模型授权。worker 领取时还需独立开启 `--allow-model`，并复核冻结 bundle、配置 hash 和授权记录，不能仅靠调度提示放行。
- 新表 `run_model_grants` 保存授权策略、累计额度和执行尝试绑定；`model_calls` 保存幂等 ID、请求 hash、状态、deadline、实际 usage、结果产物 hash 和受控错误。迁移为 `d719a01b0001`，上接 `d716a06b0001`；downgrade 遇到记录会拒绝清空证据。
- `model_gateway_service` 提供 `authorize_process`、`bind_attempt`、`reserve_call`、`mark_dispatched`、`finish_call`、`revoke_attempt`。调用准入统一先锁 Run 行；相同 ID/相同内容返回账本，相同 ID/不同内容冲突；行锁加 PostgreSQL 部分唯一索引约束每 Run 一个在途调用。
- 调用登记即保守占额度；即使还未确认发出也不退额度。发出前提交 dispatched；提交与实际发送之间崩溃不能自动重放。unknown、缺失/无效 usage 会停止后续调用；总 Token 只按实际已知 usage 累计，不把未知记成零、不承诺严格总 Token/费用上限。
- Run/实验取消、worker 结算异常及恢复会撤销授权并将未结算调用保守记录为 unknown。迟到结果可以补到账本，但不恢复 Run、不改变其终态。
- 目录协议校验仍走无模型断网 probe，报告明确 `model_access_validated=false`。前端启动确认文案不再把付费风险描述为 Native 独有。

### 数据流和当前边界

`登记 model_policy → 预览冻结 → 用户 allow_model → 入队同事务写授权 → worker allow_model → 绑定 process_run 所有权/期限 → 调用占额/幂等账本 → 结算或撤销`

这不是已可用的在线网关：目前没有 HTTP 网关、凭证签发/挂载、网络配置或供应商 HTTP 转发。账本方法只供可信平台内部调用，`run_id`/worker token **不是 Agent 鉴权凭据**，不能直接暴露为公共接口。在线 Process 的 prepare/run 暂时显式拒绝并报告 `model_gateway_transport_not_implemented`，不会降级成普通外网容器。Native 的原有模型路径保持不变。

后续 HTTP 适配必须先验证短期凭证，再向账本传递解析出的 Run/worker 身份；先限制原始请求体字节，再做 JSON 校验；只在新登记调用上尝试发送一次，禁用自动重试，并按 `body_bytes` 的同一份字节发送/存证。请求正文证据产物和 RunEvent/Trace 去重尚未实现，属于 B/C 的接续工作。

参数依据：[阿里云 Chat Completions 官方协议](https://help.aliyun.com/en/model-studio/qwen-api-via-openai-chat-completions)，核对日期 2026-10-19。首版沿用项目已有 `max_tokens` 和 `enable_thinking=false`；官方提示新接入优先考虑 `max_completion_tokens`，但其模型支持范围不同。模块 B 必须用实际冻结模型核对支持情况与平台允许列表，不能直接承诺所有 Qwen 型号均可用；当前输出限制是固定转发参数，不代表已验证供应商精确计费上限。

### 已验证与未验证

- 网关新增 41 项离线测试与已有 v2 回归合计：**182 passed，63 subtests passed**。覆盖配置兼容、参数拒绝、请求限制、入口/worker 双授权、幂等/单在途、超限、取消、期限、未知 usage、迟到结果和 PostgreSQL DDL 编译。
- 前端 `npm run typecheck` 通过；本轮仅调整费用授权文案，未做浏览器验收或前端 build。
- 测试禁止加载 `.env`、禁止真实数据库连接与外部网络；没有模型调用或 Docker 操作。Windows 沙箱中的 TestClient 阶段停住后，使用同样离线保护在沙箱外完成回归。
- 行锁和唯一索引已做代码路径/离线 DDL 检查，**没有真实 PostgreSQL 并发压力或实际 upgrade/downgrade 验收**，不能据此宣称端到端并发正确。
- 当时尚未迁移本机数据库。A 阶段迁移为 `d719a01b0001`，后续最新迁移见第 8 节。开始新表联调前，由操作者确认数据库环境再执行升级；不应为了测试 downgrade 删除已经保存的授权/调用证据。

### 下一接续点：B 的安全检查点

先做无模型 Mock 网关的 Docker 网络探针：Agent 能到专用网关，但不能访问外网、宿主服务、业务 API、数据库或 Docker socket；基线/最终测试继续断网。未通过不放宽网络。通过后确定网关部署/控制通道，接短期凭证、固定上游、超时和清理恢复；再做真实数据库事务/并发验收。真实模型付费调用仍留到 D，由用户明确触发。

## 7. B1 网络检查点实施记录（2026-10-19）

新增 `scripts/probe_gateway_network.py`（宿主编排）、`scripts/gateway_probe_runtime.py`（只用标准库的容器探针）及 `tests/test_gateway_network_probe.py`。它们独立于业务配置和数据库，不加载 `.env`、不构建/拉取镜像，不修改现有 `platform_container.py` 或测试 runner 指纹，也没有解除在线 Process 的关闭状态。

### 本机实际结果

- Docker Desktop Linux Engine **28.3.2**；复用 `repopilot-pytest:py311` 的不可变 ID `sha256:21f0e32d2a261a1c2a9756e1a083ab121ccd715e416a0be79cb304364c4b6f94`。
- 2026-10-19 05:28:09—05:28:31 UTC，**18 项真实容器检查通过**，状态 `passed`，`cleanup_confirmed=true`。本机报告位于 `.platform-artifacts/gateway-network/267283a1bbe1480c9eea3c84bc745758.json`（被 Git 忽略，不会自动同步到其他电脑）。
- Agent → mock 网关 → 固定 mock 上游成功；网关拒绝 CONNECT 代理请求。
- 正向对照证实宿主临时 canary、外网 TCP、外部 DNS、模拟 API/数据库端口确实可达；Agent 对应直连均被阻断。没有用“未启动的服务连接失败”代替隔离证明。
- Agent 中不存在 Docker socket；单独的 `--network none` 测试探针无法访问网关或公网。
- 四个临时容器、两张临时网络均按本次 UUID 标签逐一清理并检查不存在；宿主固定文本 canary 已关闭。没有删除既有容器/网络或修改 Docker daemon/firewall 配置。
- **8 项离线探针测试通过**：覆盖隔离参数、不降级、正向对照失败时不得判通过、资源所有权检查和失败后的清理。未重跑全项目测试，未执行数据库迁移或模型调用。

### 由此确定的网络基础与尚未证明的内容

Agent 侧采用本次执行独占的 `bridge + --internal + gateway_mode_ipv4/ipv6=isolated`，不发布端口，不授予网络管理权限；专用网关连接内网和独立出站侧网络。测试容器继续断网。Docker 官方明确区分 internal 和 isolated，单纯 internal 仍可能访问桥接地址上的宿主监听服务：[网关模式说明](https://docs.docker.com/engine/network/port-publishing/#gateway-modes)。

这次出站侧是普通 bridge，仅用于 mock 和对照探针，**尚不是供应商级出站白名单**。模拟 API/数据库是本次启动的固定响应 canary，不是真实业务服务；公网只测试 `1.1.1.1:443` 的 TCP 握手和 `example.com` DNS，未发送仓库内容。结果是本机 IPv4 代表性检查，不是所有协议/端口、IPv6 或任意恶意容器的安全证明。其他机器、Docker/VPN/防火墙配置变化后需重新运行。

Mock 网关不是生产网关：无 Run 凭证、无模型参数转发、无账本鉴权。真实 B2 必须确定可信网关与账本的控制通道，确保 Agent 不能访问管理接口，再接短期凭证与固定上游；不得把 mock 端点直接接上真实模型。

### 复现与继续开发

先 `docker image ls --no-trunc` 确认本机已有 Python 镜像，再执行（下面 ID 仅对应本机已验证镜像）：

```powershell
python -m scripts.probe_gateway_network --image sha256:21f0e32d2a261a1c2a9756e1a083ab121ccd715e416a0be79cb304364c4b6f94 --execute
python -m pytest -q tests/test_gateway_network_probe.py
```

脚本会临时监听宿主随机端口，只返回固定探针文本，不提供文件服务；外网对照只发送固定的 TCP/DNS 探针。缺少正向对照、环境不支持或 Docker 不可访问时返回 `inconclusive`；出现可绕过路径返回 `failed`；清理不能确认时返回 `cleanup_unconfirmed`，不得继续接真实模型，也不要使用全局 prune 清理其他工作。

下一接续点是 **B2：专用网关部署/可信控制通道、短期凭证签发与验证、Mock 请求对接 A 的账本，以及取消/超时/清理恢复**。本机网络检查点已通过，不需要再次从 A 或重新搭建 Agent 框架开始。真实上游调用仍由用户在 D 阶段明确启用。

## 8. B2 第一部分：专用 HTTP/凭证与 Mock 账本核心（2026-10-19）

### 已完成的数据流

`可信 worker 内部签发一次性 Run 凭证 → Agent POST /v1/model-calls → 凭证摘要定位 Run → 当前所有权/阶段/期限校验 → 账本占额 → 保存冻结请求 → 标记 dispatched → MockTransport → 保存结果 → 账本结算 → 仍有效才返回`

- `gateway_credentials.py`：`issue_credential(run_id, worker_token, mode='mock')` 只供可信内部调用。使用 32 字节随机数生成短期 bearer，数据库只持 SHA-256 摘要；原始值以 `SecretStr` 返回，默认 repr 不展示。只允许当前有效的 process_run 执行尝试签发一次，不能通过重新签发重放或切换已有尝试。
- `authenticate(secret)` 从摘要反查 Run，再持 Run 行锁复核配置 hash、worker token、阶段、期限和取消状态；请求体不能选择 Run。未知、过期、撤销或失去所有权统一返回 401。取消/恢复已有撤销路径现在同时清除凭证摘要，保留授权模式作为历史信息。
- `gateway_app.py:create_gateway_app()` 是独立 FastAPI 应用工厂，**没有挂进 `backend.app.main`**。只开放 `GET /health` 和 `POST /v1/model-calls`，关闭 docs/OpenAPI，没有签发、取消或业务管理路由。
- HTTP 层校验重复敏感请求头、Content-Type、Content-Length、原始请求体上限、分块流式输入累计大小和 5 秒请求体读取期限；JSON 拒绝重复键/过深嵌套。Agent 只能提交 `call_id` 与文本 `messages`，不接受 model、run_id、URL、headers 或 tools。
- `gateway_exchange.py` 将实际规范化请求字节与 A 的账本 hash 比较，通过短事务标记 dispatched 后才调用 transport；等待不持数据库行锁。当前只有不发起网络请求的 `MockTransport`，不支持配置真实 URL/供应商 Key。
- 请求和结果保存在平台私有 Run 产物目录的 `gateway/requests`、`gateway/responses` 中，限制大小、按内容 hash 命名，读取时复核 hash/调用绑定；不会把鉴权头或 worker token 注入产物。不覆盖旧文件，结果缺失/损坏返回错误，不能偷偷重调来补造历史。
- 重复成功请求返回相同产物；在途请求返回 202；同 ID 不同内容/预算关闭返回 409；未知结果返回 502，绝不自动重发。取消发生在已受理请求之后时，迟到结果仍可落账，但不会交给撤销的执行尝试，也不修改 Run 终态。

### 控制通道与 Mock 边界

采用**可信网关内部直接访问现有数据库账本服务**，不通过 Agent 可访问的业务 API 转发管理命令。代码层复用 SQLAlchemy 短事务服务已完成；独立网关容器的数据库连接、最小权限配置、私有产物卷与网络部署尚未接线/验证。Agent 不应得到数据库配置或平台私有卷；后续部署不能把整个宿主工作目录或 `.env` 挂给 Agent。

`run_model_grants.gateway_mode` 和 `model_calls.transport` 明确保存 `mock`；历史记录的新字段保持 null，不回填或伪称真实调用。Mock 返回明确的模拟文本，`usage=None`，不编造供应商 Token 数。按 A 的规则，缺失 usage 会关闭该 Run 的后续新调用，但同 ID 原结果仍可重取。因此这一步是单次模拟请求闭环，不是多轮真实 Agent。

凭证签发尚未自动接到 worker、明文尚未通过只读文件挂载给容器；本轮没有凭证文件清理的真实容器验收。`ProcessAdapter` 在线分支仍明确报 `model_gateway_transport_not_implemented`，这是未完成部署前的保护，**不能为了演示手动删掉这条保护**。B1 的简单探针服务不是这个 HTTP 应用，B1 通过也不能替代 B2 的容器联调。

### 迁移与验证

- 新增迁移 `d719a02b0001`，上接 `d719a01b0001`：凭证摘要唯一约束、授权模式、调用来源。它是独立新迁移，没有回改 A 的迁移；downgrade 遇到凭证/模式/调用来源证据会拒绝丢弃。
- 本轮新增 **25 项 HTTP/凭证联调测试**，覆盖重复请求、伪造身份/参数、过期/取消/所有权丢失、分块超限、未知结果、迟到响应、证据缺失/篡改、落盘失败及迁移 DDL。
- 网关与 v2 回归：**215 passed，63 subtests passed**。测试使用真实应用/业务方法和临时产物文件，但 SQL 存储为模拟；禁用 `.env`、真实数据库连接和外网。没有启动 Docker、模型调用、数据库迁移或本轮前端改动。
- 这些结果不证明真实 PostgreSQL 并发/持久化或跨容器 HTTP 已通过，也不是完整 B2/B 模块完成。后续真实联调前，操作者确认数据库环境后执行 `python -m alembic upgrade head`，当前代码 head 应为 **`d719a02b0001`**。

### 下一接续点（继续 B2，不进入 C）

1. 把独立网关应用部署到 B1 已验证的拓扑，配置仅可信网关可访问的数据库/私有产物通道；首轮仍只允许 mock，不提供供应商 Key。
2. worker 在领取有效 process_run 后签发凭证，以独立只读挂载交给 Agent；凭证不得进入冻结 request、命令行、普通日志、RunEvent 或报告。
3. 接入 Process 容器启动、网关就绪检查和本次所有权标签；正常结束、取消、强制超时和恢复都要先撤销授权，再清理凭证文件/容器/网络。清理不能确认时保留栅栏，不自动重放。
4. 做真实 PostgreSQL 与容器 Mock 联调：跨 Run/跨尝试拒绝、并发限额、重复请求、取消、期限和崩溃恢复。完成后再接固定真实上游传输；真实付费调用仍由用户在 D 明确触发。

## 9. B2 第二部分：容器运行器与真实 Mock 闭环（2026-10-19）

### 本轮完成

- 新增 `gateway_runtime.py`：显式平台配置、不可变本地镜像、internal/isolated 专属网络、Run/attempt 所有权标签、网关就绪检查、短期凭证单文件只读挂载，以及幂等清理。默认未配置时仍拒绝在线执行，不存在普通外网/host 网络回退。
- Process Adapter 从可信 worker 接收尝试 token，而不是从 Agent 输入或 state 取身份。离线路径保持原样；配置了 model_policy 的路径只支持当前 Mock 部署。运行元数据保存 `gateway_mode=mock`、镜像 ID、宿主运行器 hash 与 `model_access=false`。
- 父监督器在结束/强停子进程之前提交撤销，并在子进程退出后补做资源清理。显式恢复分为“短事务撤销 → 无行锁清理 → 再核对 token 后解栅栏”；撤销/清理不确定时保留原 active_token，不自动重放。
- 新增 `backend/Dockerfile.gateway`、锁定主要依赖的 `requirements.gateway.txt`、`gateway_entrypoint.py`。入口禁用 dotenv，只读挂载中的 DB-only JSON；不复制 `.env`，不提供真实供应商配置。网关绑定当前 Run/attempt，使用非特权 DB role，并拒绝明显特权及能修改业务生命周期的角色。
- Agent 不挂载 DB 配置或私有证据；网关只挂本 Run 的 `gateway/` 证据子目录。Windows 凭证目录先配置 DACL，POSIX 为 0700。在线 stdout/stderr 不采集、自报 trace 暂不导入，避免可读 bearer 被复制进普通日志；C 阶段再接可信网关观测。
- `platform_container.py`、`platform_test_collector.py` 未改动，现有测试 runner 指纹没有因本轮变化而失效，基线/最终测试仍断网。
- 新增独立的 `scripts.probe_gateway_runtime` 与固定 `gateway_smoke_agent.py`，只创建一次性 PostgreSQL/容器/网络，不使用现有数据库。具体配置与 Agent 协议见 [Mock 运行说明](model-gateway-mock-runtime.md)。

### 实际验证结果

- 新增 **18 项离线运行器测试**，集中覆盖正常生命周期、网络/容器/就绪各阶段故障、取消、撤销失败、资源所有权、清理失败保留栅栏、跨 Run/attempt 范围、父监督器先撤销后强停、恢复失败不解栅栏，以及适配器不降级/不导入原始在线 trace。
- 网关与既有 v2 回归最终为 **233 passed，63 subtests passed**，3 个既有警告。离线命令禁用 `.env`、真实数据库连接和外网；Windows 沙箱的临时路径拒绝访问及 TestClient 停住后，在相同保护下于沙箱外通过，并结束了本次停住的 pytest 进程。
- 最终镜像 `sha256:c1efafee8a066edc29686bb28a2b943b1a4fc8da5bf0236b9051d2c9ca164745` 的真实验收：**2026-10-19 05:55:34—05:55:49 UTC，16 项检查全部通过**。报告 `.platform-artifacts/gateway-runtime-smoke/b154dcfd-9a8f-4921-85db-7628713b4e78/report.json`，`status=passed`、`cleanup_confirmed=true`。
- 真实链路验证：Agent 只读凭证 → 独立网关 → 受限角色 PostgreSQL 账本 → 私有请求/响应证据。相同请求取回相同结果，数据库只保留一次 succeeded；不同正文 409、非法凭证 401、伪造上游参数 422；Mock usage=null，后续新调用因 usage_missing 拒绝。
- 验证了 Agent 看不到数据库配置、私有证据、Docker socket，不能写凭证文件；结束后摘要撤销、凭证文件删除。3 个临时容器、3 张网络逐项确认移除，临时数据库数据在 tmpfs 中随容器删除，临时密码文件删除；本地保留报告、固定 Mock 证据及构建镜像。按本模块标签额外检查无遗留容器/网络。
- 首次真实验收因脚本误把 `usage_missing` 写成 `usage_unknown` 被判 failed；修正的是断言，不是放宽账本规则。修正后重新运行通过，旧失败报告保留。构建阶段也修复了基础镜像默认非 root 导致依赖安装失败的问题，最终运行仍为非 root。

### 当前边界与下一步

这一步证明了**真实 PostgreSQL 中的单次 Mock 持久化和真实 Docker 部署**，不是完整 Agent 修复任务、全平台 UI 演示或生产级安全审计。临时库通过 ORM 建表，未做实际 Alembic 升降级验收；没有迁移/修改现有业务库。新的 Mock-only 运行配置没有替用户写入环境，现有 worker 不会因此自动上线。

真实 PostgreSQL 同时请求/锁竞争、请求中取消、期限与子进程强杀、DB/Docker 短暂故障后的恢复仍待集中验收；当前对应分支主要通过模拟 Docker/数据库测试，不能称作真实故障验收已完成。业务角色权限检查不是完整 ACL 审计；Mock 控制网络无公网出站，真实供应商允许列表/传输仍未实现。

继续按 B 推进：

1. 扩展现有一次性库 smoke，不另起框架，集中验证并发幂等、单在途与取消/强杀/恢复，并确保未知状态不重放、清理不明不解栅栏。
2. 完成固定供应商传输及出站边界，用假上游验证超时/错误/usage，真实付费请求仍由用户在 D 明确开启。
3. 再进入 C：把可信账本接到 Trace/资源/页面，去重 Agent 自报，明确区分 Mock/live；现在不能拿 Mock Run 结果声称真实模型策略效果。

## 10. B2 第三部分：并发与故障检查点（2026-10-19）

### 完成内容与分层证据

沿用现有一次性库探针，新增 `--faults` 和 `scripts/gateway_fault_checks.py`，没有另起 Agent 框架，也没有给生产网关加故障控制 API。脚本禁止复用已导入业务配置/数据库模块的解释器；各故障 Run 都在新建临时库内，报告记录 Run、检查层次、逐项结果以及宿主实际源文件 hash。

- **真实 PostgreSQL 服务层**：8 路同 ID 并发仅登记一行、占一次额度；不同 ID 并发只有一条获准在途。绕过服务直接插入第二条在途记录也被 PostgreSQL 部分唯一索引拒绝。跨 Run/attempt、已过期 bearer、过期前解析出的身份均不能越过准入。
- **受理后取消**：脚本专用阻塞 Mock transport 等待时，独立真实事务成功提交取消，证明等待 transport 时未持 Run 锁；在途先记 unknown，迟到结果可补为 succeeded，但不交付给撤销身份、不增加额度、不改变取消状态。这是服务 + 数据库层验证，不冒充真实供应商网络取消。
- **dispatched 提交后崩溃**：真实子进程在提交后直接退出；生产父监督器将其结算为 interrupted，账本为 unknown，额度不退、栅栏保留，同 ID 不能重新消费；显式恢复不重放、不清空证据。
- **真实 HTTP/容器**：固定 Agent 在每个容器故障场景先发起 8 路相同 ID 请求，只得到成功或在途结果，最终账本仍只有一次调用。实际使用冻结 bundle、ProcessAdapter、execute_step 与 supervise；测试包装仅禁用子进程 dotenv。
- **强杀与清理失败**：强停本次真实 worker 子进程，确认父进程撤销并清理其容器。额外创建本次拥有的网络占用容器，使 `network rm` 确实失败；凭证文件和栅栏保留，显式恢复也不能提前解栅栏。移除占用者后恢复成功，历史调用/额度保持不变。
- **DB 连接故障恢复**：仅把临时库的网关角色设为 NOLOGIN 并终止该角色连接，真实 HTTP 返回 503；恢复 LOGIN 后同 ID 重新取回既有结果，调用额度不变。没有停止数据库服务器或 Docker daemon，不宣称覆盖完整宕机/网络分区。
- **取消与期限**：运行中的真实 Agent 接受取消后不误报正常失败；实际执行期限到期后为 timed_out。没有把 child 已停但清理未确认的状态误当作安全完成。

### 修复的业务问题

定向回归复现：取消已提交、授权撤销导致子进程先抛错退出时，`settle_step` 原先先处理 `error_code`，可能把取消写成 failed。现在在**清理已确认**的错误分支优先写 cancelled 与 EXECUTION_CANCELLED；强杀、结果缺失或清理失败仍走上方 interrupted/保留栅栏分支。该竞态通过确定性回归验证，不能仅凭真实容器取消的一次时序声称穷尽所有调度情况。

### 最终结果与边界

- 最终报告：`.platform-artifacts/gateway-runtime-smoke/e018b8d8-2033-4744-8140-ca88e1720303/report.json`。**16 项基础 + 62 项故障检查全部通过**，11 个故障 Run，`status=passed`、`cleanup_confirmed=true`。网关镜像沿用 `sha256:c1efafee8a066edc29686bb28a2b943b1a4fc8da5bf0236b9051d2c9ca164745`；本轮业务修复在宿主 worker 结算层，报告另存该源码 hash。
- 新增 **9 项离线回归/探针保护测试**；网关与 v2 集中回归 **242 passed，63 subtests passed**，3 个既有警告。`py_compile`、`git diff --check` 通过。
- 早期一次探针因测试夹具的任务描述与冻结 bundle 不一致而中止；修正夹具后重新执行，失败报告保留，没有放宽冻结检查。
- 各临时尝试、子进程、网络占用容器、PostgreSQL 容器/网络及密码文件清理确认；额外按两个模块标签只读核查无遗留容器/网络。临时数据库随 tmpfs 容器移除，不能恢复；本地保留脱敏报告、固定 Mock 证据及源文件 hash。现有业务数据库、`.env`、模型供应商均未访问。
- 这是限定并发规模和故障注入下的检查点，不是长期压力、安全认证、全量网络分区恢复或真实模型能力证明。临时库仍通过 ORM 建表，Alembic 升降级与业务环境迁移未验收；前端完整演示、真实 Token/费用仍未完成。

**下一步：继续 B 的固定供应商传输，而不是再重复做 Mock 单次 smoke。** 实现冻结模型/参数的唯一上游、禁止自动重试、单次超时、响应字节/usage 校验与未知结果落账；同时落实可信网关出站边界。先使用假上游集中验收，真实付费调用仍留给用户明确启用的 D。完成后再进入 C 的 Trace/资源/页面去重与展示。

## 11. B3a：固定协议与假上游结算（2026-10-19）

### 本轮交付

数据流：`冻结请求 → 支持的模型/参数检查 → 账本占额并提交 dispatched → 固定协议假上游 → 有界响应解析 → 私有结果证据 → usage 结算 → 活跃身份才接收答案`。

- 新增 `gateway_upstream.py:DashScopeProtocolTransport`。当前必须显式注入可信测试 adapter，没有默认网络客户端、真实 Key 加载器或环境开关；模式固定 `dashscope_fake`，鉴权头使用固定假值。Agent 请求不能提供 adapter、URL、model 或 headers。
- 协议目标固定为北京 DashScope 兼容接口 `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`，首个明确允许的模型为 `qwen-plus`。其他模型在占额之前拒绝；保留既有 ModelPolicy 和实际请求规范化方式，不改变历史配置 hash。继续使用非流式文本、`enable_thinking=false` 和冻结的 `max_tokens`。这不是已经完成账号/区域/模型可用性验收；`qwen-plus` 也是可变别名，不能声称模型版本完全固定。
- 使用 HTTPX 的 async 请求，外层 `asyncio.timeout` 限制整次等待，内层限制各阶段等待；禁止环境代理与自动重定向，没有重试/备用模型逻辑。底层 adapter 由可信测试控制，不把代码层固定 URL 等同于容器出站白名单。
- 响应原始字节上限 262144；拒绝压缩、重复关键头、长度不符、非 JSON、重复 JSON 键及过深结构。仅接受单个 assistant 文本选择，拒绝工具/思考内容/拒绝结果；`finish_reason=length` 明确标记 `truncated=true`，不能伪装为完整回答。模型回答成功也不等于任务修复成功。
- usage 提取三项严格整数并核对总和，允许供应商的额外明细字段但不冒充已采集该明细。单次 total 大于 1000000 作为本协议不支持的数据处理，避免异常计数写入累计账本；这不是费用硬预算。缺失或非法 usage 时保留可用答案，但停止新调用；非法值写 `invalid_upstream_usage`，不填零。
- 假上游成功结果明确带 `usage_source=fake_upstream`，所有调用账本带 `transport=dashscope_fake`，不能加入真实 Token/费用实验统计。旧 Mock 仍 `usage=None`，旧响应产物不回写新增字段。
- 不可用答案或结果落盘失败，如果已经解析到合法 usage，仍保留计数；HTTP 非 200、超时和断线保守结算 unknown、不退额度、不重发。迟到答案可留账，但不能交付给已撤销身份。
- `GatewayExchange` 接受显式注入的 fake 协议路径，但拒绝 live；生产凭证签发、鉴权及 RuntimeSettings 继续仅允许 mock，不能通过配置文件切换成 fake/live。health 如实显示注入的模式，仍不声明真实模型访问。

### 集中验收及边界

- 新增 `tests/test_gateway_upstream.py` **35 项检查**：冻结字节/hash、缓存取回、后续调用额度、usage 缺失/非法/保留、截断、3xx/4xx/5xx、断线/超时、不重试、取消迟到、响应大小/格式、模型白名单及 live 入口关闭。
- 包含一个**真实 localhost HTTP 慢速分块服务器**：持续有小块到达仍被整次截止时间中止，并确认连接关闭。其余供应商响应为进程内 HTTPX 假 adapter，账本存储为模拟 SQL；不冒充真实 TLS、供应商请求或本轮 PostgreSQL/Docker 验收。
- 网关与既有 v2 集中回归：**277 passed、63 subtests passed**，3 个既有警告。执行保护禁用 dotenv、真实 SQL 连接与外网，只放行测试 localhost；未读取 `.env` 或调用真实模型。首次检查的超大参数自动用例名导致 Windows 临时路径错误，改为短 ID 后重新通过，没有放宽业务检查。
- `requirements.gateway.txt` 增加 `httpx==0.28.1`；**本轮未构建/启动新网关镜像**，不能把 B2 旧镜像报告当作本轮代码已部署的证据。没有新增迁移，也没有改动业务数据库。

协议参考：[阿里云 Chat Completions 官方文档](https://help.aliyun.com/en/model-studio/qwen-api-via-openai-chat-completions)（保留兼容旧域名）、[HTTPX 超时定义](https://www.python-httpx.org/advanced/timeouts/)、[HTTPX transport 与重试接口](https://www.python-httpx.org/advanced/transports/)。

### 唯一下一接续点：B3b 出站部署，暂不进入 C

1. 为可信网关落实固定供应商出站边界：Agent 仍只能访问专属内网网关；网关不能凭普通外网 bridge 任意访问互联网/宿主/业务网。实际选定出站代理/网络约束后，以假上游验证允许与禁止目标，不能仅用 ENDPOINT 常量宣称完成。
2. 在此边界上增加真实 TLS transport、显式零连接重试和可信供应商密钥单文件挂载；不得读取业务 `.env`，不得向 Agent、日志、证据、命令行或普通环境变量泄露 Key。用户在 D 确认区域/账号/少量付费调用之前，保持 live 关闭。
3. 构建新镜像，用一次性资源集中做假上游跨容器成功/超时/取消/清理验收，记录新镜像与源码 hash。补齐此部署检查点后再进入 C 的 Trace/资源去重与页面展示，不再次重做无新增覆盖的 Mock 单次 smoke。
