# Day 4：Agent 版本登记与 Benchmark 导入

2026-10-15。实现入口：`schemas/platform_catalog.py`、`services/platform_catalog_service.py`、`services/catalog_validation_service.py`、`api/routes/platform_catalog.py`、`frontend/src/pages/LiveCatalog.vue`。

## 功能与设计原因

之前每次准备都传本机配置文件，现在在 Agents 页面登记 Native/Process 的名称、版本、配置和能力声明，保存在 PostgreSQL。同名同版本相同内容返回已有记录，不同内容返回 409，必须升级版本，避免后续实验引用的配置被覆盖。

登记不等于可执行。点击“显式校验”生成持久 CatalogValidation，由原 platform_worker 领取，不在 API 请求里运行容器。RunWork 和 CatalogValidation 的执行 token 互相阻塞；清理未确认时不能再领取或自动重放。数据库只在领取和结算时使用短事务，不持行锁等待 Docker。

- **Native：** 核对冻结实现指纹与配置；若配置指定测试镜像，也检查本地存在。不会调用模型，报告明确 `native_static_contract`，不伪造已验证的观测能力。
- **Process：** 已有不可变镜像、无网络、十秒协议 fixture；检查返回身份、退出码、写入边界和声明的 trace。只验证 execution，不把 fixture 运行计入任务成功率。缺镜像不自动下载或构建。
- **Benchmark：** 导入有序 Case 清单、注册仓库 ID、commit、编辑/保护范围、验收规则与测试镜像。校验干净工作副本、文件存在、受支持的 python-basic profile、文件指纹、保护测试指纹，并在真实受限容器导入 pytest。每个不同镜像只探测一次；不在此阶段执行任务基线。

例如 noop Demo 正确返回 result.json，可以通过协议校验成为 ready；但 Day 3 的 noop 实际修复任务测试仍失败。**ready 代表最近一次指定范围的校验通过，不代表 evaluation passed。** 后续正式 Run 仍需重查环境并运行基线。

新增 AgentVersion、BenchmarkVersion、CatalogValidation 三张表，迁移 `d715a04b0001` 接在 Day 2 后，本机已真实升级。校验历史不覆盖，版本详情展示最近一次结果。若 worker 崩溃，保留 token，操作者确认写入停止后才能恢复；不把 interrupted 自动当可重试任务。

## API 与页面

| 接口 | 用途 |
| --- | --- |
| POST /api/v2/agents、/benchmarks | 登记 Agent / 导入 Suite |
| GET /api/v2/agents、/benchmarks | limit/offset 分页列表 |
| GET /api/v2/agents/{id}、/benchmarks/{id} | 固定配置、指纹、最近校验 |
| POST /api/v2/agents/{id}/validate、/benchmarks/{id}/validate | 携带 request_key UUID 显式入队，返回 202 |
| GET /api/v2/catalog-validations/{id} | 单次历史校验 |
| GET /api/v2/catalog-repositories | 仓库 ID/name/commit，不暴露宿主路径 |

字段校验 422、内容/请求冲突 409、资源不存在 404、数据库异常 503。容器和协议失败写入校验报告，不统一变成 HTTP 422。页面支持配置生成、JSON 文件导入、完整配置查看、校验与刷新；列表展示最近 100 条，API 支持分页。

当前仍是可信操作者本机入口，没有多租户认证，不直接暴露到公网。不要在 argv/JSON 中填密钥；Process 不接入模型凭据和网络，不支持任意宿主挂载。无费用握手失败的 Agent 不能假装 Ready。

## 简短操作

1. 重启/刷新 API 与前端，打开侧栏 Agents，查看 `Day4 Native acceptance`、`Day4 Demo noop` 等验收记录。若要自行登记，使用 [示例 JSON 与说明](../examples/catalog/README.md)，改配置时升级 version。
2. 打开 Benchmarks，查看 `Day4 task-list suite` 的 Case/规则/校验结果。自行导入时替换示例仓库 UUID 和镜像 ID；展开“已注册仓库”可查看 ID/commit。点击显式校验后运行下面 worker，刷新结果。
3. 刷新整个浏览器，记录应仍存在。wrong-id 与 missing-image 样例应为 invalid，不删除失败历史来制造全通过。

```powershell
.\.venv\Scripts\python.exe -m scripts.platform_worker
```

无需 `--allow-model`。单 worker 优先处理 Run，空闲时领取校验；暂不承诺繁忙队列公平调度。正式实验创建/批次启动留 Day 5。

若中断，先停止原 worker 并确认相关写入停止，使用日志中的校验 ID/token 恢复：

```powershell
.\.venv\Scripts\python.exe -m scripts.platform_worker --recover-validation <校验UUID> --token <执行token> --confirm-writers-stopped
```

恢复会清理该 ID 所有的容器，保存失败并解除阻塞，不重放。之后再显式创建新校验请求。

## 本轮验证

- **离线：75 项 Day 1—4 回归通过**，Day 4 新增 11 项。禁用 dotenv/外网，数据库与 Docker 模拟，覆盖版本冲突、请求幂等边界、清理失败保留 token、协议身份/范围/超时、缺 pytest 拒绝、Native 无模型执行、API 错误映射。synthetic 异常日志为测试注入。
- **前端：** TypeScript 检查与生产构建通过；浏览器新表单/导入操作待用户确认，不沿用 Day 3 的页面通过结论。
- **真实数据库/API：** 迁移成功；TestClient 连接实际数据库验证重复登记返回原记录、内容冲突 409、重复 request_key 返回同一校验、非法字段 422、后续请求可重读持久记录。这不是浏览器或外部 HTTP 客户端验收。
- **真实 worker/Docker：** Native 静态检查 ready；Process noop ready；wrong-id 和缺镜像 invalid；Suite 环境和 pytest 导入检查 ready。6 个校验任务最终 4 passed / 2 failed（其中包含 Suite 增补探针后的第二次校验），active_token 全部清除。不是任务成功率。未调用模型/Embedding，也未运行任务基线。

| 场景 | 版本 ID | 初次校验 ID |
| --- | --- | --- |
| Native | 67c4f120-87a9-4b40-a5bf-e967823d1e71 | 78674747-b4c2-4079-8bb7-1316fa80d69e |
| Process noop | 862a094d-4605-4e9f-b9af-98de6e19a02a | 080bde70-cbc6-44fc-849a-49b9f408356b |
| Process wrong-id | f562728a-d889-4190-99f0-105333c69f1d | 9d0877a7-d0b9-48e3-a973-c358cce23375 |
| Process 缺镜像 | 643800df-2be6-470c-a92a-b77b45904318 | 33cf3815-64a1-4fdb-afaa-883c7a3fa440 |
| task-list Suite | 796409e3-901a-4c52-9cad-27e7c4ea8ce2 | 7051604a-811c-4b9e-bcd3-d6263d06697e |

补充 pytest 镜像探针的 Suite 校验 ID：`44df5362-0bd0-4d1d-8daa-f7266f835b77`。初次历史校验不补造此证据。本机配置/结果在 `.platform-artifacts/day4-acceptance-20261015/`，被 gitignore，不随代码自动跨机。示例 fixture 不代表真实模型通用能力。

下一步 Day 5：用固定 Agent/Suite 版本创建实验 manifest，接通批次调度，继续复用现有 worker。
