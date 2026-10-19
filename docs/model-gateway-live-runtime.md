# 显式真实模型模式：部署准备（D1）

当前代码已支持 `dashscope_live`。D2 已完成新镜像的实际容器/临时数据库无调用部署检查，以及隔离 TLS 假供应商和 C2 证据读取检查；没有配置或启动本机真实供应商请求。以下配置示例不是已生效配置。不要复用 B3b 旧网关镜像：它不包含 live 引导与新观测代码。新镜像 ID 和报告见[计划第 17 节](v2-model-gateway-plan.md#17-d2新镜像与无付费部署验收2026-10-19)。

## 1. 运行条件

继续保留实验/API `allow_model`、worker `--allow-model`、Run/attempt 所有权、期限、撤销与预算检查。额外要求操作者通过 `REPOPILOT_GATEWAY_RUNTIME_CONFIG` 指定独立的部署 JSON，明确 mode、enabled、北京地域和两个本地不可变镜像 ID。没有此配置仍拒绝运行，不自动读取 `.env` 或回退到普通直连。

```json
{
  "mode": "dashscope_live",
  "image": "sha256:<重建后的网关镜像64位ID>",
  "control_network": "<已配置的internal-isolated控制网络>",
  "database_file": "D:/RepoPilot-private/gateway-database.json",
  "live_provider": {
    "enabled": true,
    "region": "cn-beijing",
    "provider_key": "D:/RepoPilot-private/provider-key",
    "egress_image": "sha256:<固定代理镜像64位ID>"
  }
}
```

路径和 ID 必须由操作者填实；示例故意不可直接执行。DB 文件仍仅含 DB 配置，使用 B2 的受限网关角色，不能复用业务超级用户。TLS fixture 与 live_provider 互斥；不能给 live 添加任意 URL、CA、代理或请求头。

供应商 Key 由用户自行放入独立只读普通文件，限制宿主目录访问权限。不要把 Key 发到对话、写进 Git、argv 或日志。worker 仅检查路径/大小/权限，不读取内容；网关通过单文件只读挂载读取。文件为 ASCII、16—240 个可打印字符，可带一个末尾换行。Key 的地域、账号权限、额度及 qwen-plus 可用性仍须用户确认。

## 2. 网络和证据

每次尝试创建 Agent 内网、网关—代理内网及代理出站 bridge。只有固定代理接出站网络；Agent 仅连自己的内网，网关连接内网与受限 DB 控制网络。代理无任何 Key/DB/工作区挂载，只允许 `dashscope.aliyuncs.com:443` CONNECT；解析结果必须全部为公网 IPv4。网关校验固定 HTTPS 路径与 TLS 主机名，使用镜像 certifi CA，禁用环境 CA/代理、重定向和重试。

这是可信代理进程限制，不是宿主级防火墙或代理进程失陷后的完整隔离保证。D2 已验证实际容器拓扑与拒绝路径，真实公网 DNS/TLS 和账号尚未验证。不得宣称已经完成付费端到端验收。

取消/异常继续先撤销授权，再清理所有本次容器和网络；不删除操作者的控制网络、DB 配置或供应商 Key。出站网络也纳入所有权检查及重复清理。供应商收到请求后仍可能计费，取消不保证退款。

`dashscope_live` 的响应 usage 标记为 provider，并由账本去重。mock/fake 的 usage 仅为模拟小计。全部预留调用有已结算且合法的供应商用量、授权已撤销时，才给出网关范围完整 Token；未知调用保持未知，已知小计不丢失。成本仍未知，供应商 usage 不是已核销账单。

## 3. 下一轮集中验收

1. D2 镜像和无付费容器检查已完成，接下来准备持久化演示 Run；旧一次性探针 ID 不能用于业务页面。其他电脑须同步源码并重建镜像，不要假设本机 ID 在另一台电脑可用。
2. 用户确认部署环境和 Key 后，显式触发少量真实请求。首轮建议 max_calls=1、max_output_tokens=512、request_timeout_seconds=30；总 Token 阈值仍 advisory，不是严格费用上限。此时再完成独立小 Agent 的修复/测试流程。
3. 在 Run 页核对 provider 来源、请求预览、独立测试与 Diff，再查看对比/导出。修复失败也可用于验收，只要证据和失败结果真实。

官方协议核对（2026-10-19）：[Chat Completions](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions/) 表明北京旧域名仍可使用，推荐迁移业务空间域名。本阶段保持已限制的旧固定端点，不同时引入新域名或其他模型；非流式文本、`enable_thinking=false`、`max_tokens` 的现有请求契约保持不变。[qwen-plus 说明](https://help.aliyun.com/zh/model-studio/qwen-plus) 用于核对模型能力，别名不等于不可变快照版本。
