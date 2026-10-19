# Process Mock 网关运行说明（B2 检查点）

这里只接通 **Mock**，不会连接模型供应商。现有入口 `allow_model` 与 worker `--allow-model` 双授权仍然需要；不能把 Mock 的执行成功称作模型修复成功或真实 Token/费用实验结果。

2026-10-19 B3a 补充：已新增固定 DashScope 协议的 `dashscope_fake` 测试路径，但下面的运行配置/凭证仍**只接受 mock**。假上游路径不是可部署的 live 模式；不要修改 mode 绕过保护。依赖新增 HTTPX，本轮尚未重建镜像，B2 历史镜像报告只证明当时源码。下一步为供应商级出站部署及新镜像假上游验收，见 [计划第 11 节](v2-model-gateway-plan.md#11-b3a固定协议与假上游结算2026-10-19)。

## 1. 数据流与隔离

`已授权 process_run → 绑定 worker token → 签发短期 bearer → 单文件只读挂载 → Agent → 专属网关 → PostgreSQL 账本 + 私有证据 → 撤销 → 清理`

- Agent 仅连本次尝试独占的 internal/isolated 网络，没有端口发布；网关同时接可信控制网络。当前 Mock 控制网络也必须是 internal/isolated，不能直接替换成普通外网 bridge。
- Agent 得到 `/input`（只读）、`/workspace`、`/output` 和 `/run/repopilot/credential`（只读）。它得不到数据库文件、平台私有证据目录、Docker socket、供应商 Key。
- 网关只挂载数据库配置单文件和本 Run 的 `gateway/` 证据子目录；应用绑定 Run 和 worker token，即使拿到其他 Run 的有效 bearer，也不能在这个实例使用。
- bearer 不写入 request、argv、环境变量、事件或普通日志；环境变量仅包含固定 URL、凭证**路径**与 `mock` 标记。在线 stdout/stderr 不采集，自报 trace 暂不导入，可信观测接入留到 C。Agent 自己能读取 bearer，因此它生成的工作区/输出文件仍应视为不可信、不得直接公开。
- Windows 凭证父目录写入前设置当前用户和 SYSTEM 的 DACL；POSIX 父目录为 0700。容器通过只读单文件绑定读取。运行结束先撤销摘要，再停止容器/删除网络，最后删除凭证文件。
- 子进程、父监督器和显式恢复都可按 Run/attempt 标签清理。失败保留 `active_token` 栅栏，不自动重放、不删除其他所有者的资源。
- `platform_container.py` 与其测试 runner 指纹未改；旧离线 Process、基线/最终测试仍为 `--network none`。

## 2. 先运行不依赖业务环境的 smoke

需要 Linux Docker Engine 28+、已有 Python 3.11+ Agent 镜像和 PostgreSQL/pgvector 镜像。**不要从 `.env` 复制配置给这个脚本。**

构建镜像时，用 `docker image inspect` 确认本地基础镜像标签指向预期 ID；BuildKit 的 `FROM` 不能直接使用本机 `sha256:…` image ID。构建完成后，运行器只接受不可变镜像 ID：

```powershell
docker image inspect repopilot-pytest:py311 --format '{{.Id}}'
docker build --pull=false --build-arg BASE_IMAGE=repopilot-pytest:py311 -f backend/Dockerfile.gateway -t repopilot-gateway:mock-b2 backend
docker image inspect repopilot-gateway:mock-b2 --format '{{.Id}}'
docker image inspect pgvector/pgvector:pg16 --format '{{.Id}}'

# 将下面三个值替换为刚才核实的 sha256:... ID，不要原样运行占位值。
python -m scripts.probe_gateway_runtime --gateway-image <网关ID> --agent-image <Python镜像ID> --postgres-image <PostgreSQL镜像ID> --execute
```

构建会下载 `backend/requirements.gateway.txt` 中锁定的主要依赖；运行脚本不构建/拉取镜像。Dockerfile 只复制 `app/` 和入口，不复制项目 `.env`；构建阶段 root 安装，运行时为 10001:10001、只读根文件系统、移除 capabilities。

脚本创建新的 UUID 标记资源：临时 PostgreSQL（数据在 tmpfs）、宿主 127.0.0.1 随机端口、隔离控制网络、专用网关和 Agent。宿主 worker 只连接该新端口；网关使用新建的受限 DB role。脚本禁止 dotenv，不读取/迁移现有业务数据库，没有真实模型请求。

临时库使用 `Base.metadata.create_all`，**不是 Alembic upgrade/downgrade 验收**。报告保存在 `.platform-artifacts/gateway-runtime-smoke/<probe UUID>/report.json`，不会随 Git 自动同步。报告只含检查结果、镜像/hash、受控错误，无数据库密码和 bearer。

正常清理会删除本次容器/网络/密码文件，临时数据库随容器移除而销毁；保留报告与固定 mock 请求/响应证据。如果撤销或资源清理不能确认，保留临时库和配置供恢复，报告 `cleanup_unconfirmed`；不要使用 `docker system prune`。需要先依据本次报告 UUID 检查资源及仍存活的 worker，再针对该尝试恢复。

## 3. 接入实际 worker（操作者确认后才配置）

此步骤会使用指定业务库，**不由 smoke 自动执行**。先核对数据库地址/备份和迁移 head `d719a02b0001`，再由操作者升级。当前仍是实验性 mock 部署，不是生产就绪网关。

配置一个可信内部控制网络，Docker 选项如下；将所需 PostgreSQL 容器接入该网络并分配固定别名。不要把 Agent、业务 API 或不可信容器接入控制网络：

```text
--driver bridge --internal
--opt com.docker.network.bridge.gateway_mode_ipv4=isolated
--opt com.docker.network.bridge.gateway_mode_ipv6=isolated
```

由数据库管理员创建专用非特权 login，禁止 superuser、createdb、createrole、replication、bypassrls。它只需数据库 CONNECT、public schema USAGE，以及：

```sql
GRANT SELECT ON platform_runs, run_work, run_model_grants, model_calls TO your_gateway_role;
GRANT UPDATE (id) ON platform_runs TO your_gateway_role; -- SELECT FOR UPDATE 所需，不用于修改 ID
GRANT UPDATE ON run_model_grants, model_calls TO your_gateway_role;
GRANT INSERT ON model_calls TO your_gateway_role;
```

不要授予业务生命周期/事件写入权限或使用 worker 的管理员凭证。入口会拒绝明显特权角色和能修改 Run 生命周期的角色，但这个检查不是完整 ACL 审计；DB role 目前也不是逐 Run 的行级权限隔离。

在只有操作者可读、被 Git 忽略的位置创建两个本地文件。路径应为绝对路径、普通文件、无链接/重解析点；不要在聊天中粘贴真实密码。

`database.json`（仅挂给可信网关，字段值均为字符串）：

```json
{
  "DB_HOST": "gateway-db",
  "DB_PORT": "5432",
  "DB_NAME": "your_database",
  "DB_USER": "your_gateway_role",
  "DB_PASSWORD": "由操作者在本地填写"
}
```

`runtime.json`（平台配置，不是 Agent 注册参数）：

```json
{
  "mode": "mock",
  "image": "sha256:替换为64位镜像摘要",
  "control_network": "your-isolated-control-network",
  "database_file": "C:/绝对路径/database.json"
}
```

启动 worker 的同一 PowerShell 进程中设置：

```powershell
$env:REPOPILOT_GATEWAY_RUNTIME_CONFIG = 'C:/绝对路径/runtime.json'
```

没有配置时在线 Process 拒绝启动；没有可信 worker 尝试绑定时不能调用运行器。这里不提供取消隔离、注入真实 URL/API Key 或降级到宿主网络的开关。

## 4. Agent 对接协议

Agent 从 `REPOPILOT_MODEL_GATEWAY_URL` 获取固定 POST 地址，从 `REPOPILOT_MODEL_CREDENTIAL_FILE` 读取 bearer。`REPOPILOT_MODEL_TRANSPORT` 当前只能是 `mock`。POST JSON 只允许：

```json
{"call_id":"step-1","messages":[{"role":"user","content":"问题文本"}]}
```

鉴权头为 `Authorization: Bearer <文件内容>`，不要输出这个头。Agent 不能选 Run、model、URL、headers、tools。`call_id` 同 ID 同正文返回原记录；同 ID 不同正文 409；在途返回 202，不能换 ID 绕过；unknown 不自动重试。

Mock 的 `usage` 为 null，不伪造 Token。按账本规则，这次成功后停止新的调用，原 ID 仍可取回结果。这不是完整多轮 Agent，也不能用于真实策略成功率/成本比较。

## 5. 集中故障验收

在第 2 节同一个命令末尾追加 `--faults`，例如：

```powershell
python -m scripts.probe_gateway_runtime --gateway-image <网关ID> --agent-image <Python镜像ID> --postgres-image <PostgreSQL镜像ID> --execute --faults
```

必须以新 Python 解释器运行；如果配置/数据库模块已被导入，脚本在创建资源之前就拒绝，避免复用到其他数据库 Engine。不要在已有业务服务或交互式 Notebook 中调用此函数。

故障场景分层记录，不能相互替代：

| 层次 | 检查内容 |
| --- | --- |
| 真实 PostgreSQL + 服务 | 8 路并发登记同 ID/不同 ID；部分唯一索引阻止第二条在途记录；跨 Run/attempt、过期身份拒绝；受理后取消与迟到结果 |
| 真实子进程 + PostgreSQL | 在 dispatched 提交后直接退出；父监督器撤销、标记 unknown、保留额度/栅栏；显式恢复不重放 |
| 真实容器 + HTTP + worker | Agent 发起 8 路相同 ID 请求；强杀真实 worker 子进程；通过额外占用者让 network rm 失败；断开临时网关 DB 账号连接后重连；运行中取消；真实执行期限到期 |

请求中取消使用脚本专用的阻塞 Mock transport 和真实数据库事务，以确定性控制“已受理、尚未返回”的边界；它不是供应商网络请求取消实验，也没有在生产网关增加延迟/故障接口。容器场景使用真实 `ProcessAdapter`、冻结 bundle、`execute_step` 和 `supervise`；入口的测试包装仅禁止子进程加载 dotenv。

数据库故障只对本次新建的 `gateway_smoke` 角色暂时设为 NOLOGIN，并终止该角色在临时库中的连接。确认真实 HTTP 返回 503 后恢复 LOGIN，再检查同 ID 能读取既有结果、额度不增加。这不等同于整个数据库服务器重启、磁盘损坏或网络分区的验证。

网络清理故障通过本次 UUID 标记的额外容器占用本次网络触发，不停止 Docker daemon、不改变防火墙。清理失败时检查凭证文件和栅栏仍保留；移除自己创建的占用者后再显式恢复。临时数据库只有在所有额外尝试/子进程都确认清理后才销毁，否则保留供调查，报告不能为 passed。

报告新增 `fault_cases`（Run 与层次）、`fault_checks`（逐项结果）、`fault_last_case` 和 `fault_sources`（实际宿主服务/探针源文件 hash）。日志中的 `Gateway cleanup unconfirmed; durable fence retained` 在故意制造网络忙的场景属于预期观察，是否验收通过仍以最终报告全部检查及 `cleanup_confirmed=true` 为准。

这些是限定规模的故障验收，不是长期压力测试或完整安全证明。供应商传输、真实 Token、真实费用、Alembic 升降级及完整前端任务演示仍另行验收。
