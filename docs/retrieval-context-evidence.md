# 检索与模型工具上下文证据 v1

本模块复用 task_events 和现有 `GET /api/v1/tasks/{task_id}/events`，不新增表或检索请求，不改变模型消息和检索策略。实现位于 `backend/app/agent/retrieval_trace.py` 和 `nodes.py`。仅新运行有这些字段，旧任务应显示“未记录”，不能读取当前索引补造历史。

## 三个关联点

| 事件 | 含义 | 关键字段 |
|---|---|---|
| RETRIEVAL_COMPLETED | search_code 已返回，尚未进行上下文预算判断 | call_id、tool_call_id、repository_id、query / effective_query、top_k、请求 / 实际策略、有序 hits、diagnostics、retrieval_parameters |
| TOOL_CONTEXT_PREPARED | 本次工具结果经过预算处理，已加入节点准备返回的 tool 消息 | 相同 call_id、tool_call_id、tool_message_index、disposition、content_sha256 / content_chars、sources、预算前后计数 |
| MODEL_CALL_STARTED | 即将尝试研究或计划模型调用，列出本次包含的工具消息 | 模型 call_id、tool_context 中每条消息的 tool_message_index / tool_call_id / content_sha256 / content_chars、系统提示 hash |

模型调用的 call_id 与工具调用的 call_id 是不同编号。先用同一个工具 call_id 连接检索与预算结果，再用 tool_message_index、tool_call_id 和 content_sha256 连接后续模型调用中的工具消息。索引从 0 开始，仅对 tool 消息计数，不是整个 messages 数组下标；保留顺序是为了区分模型重复使用相同 tool_call_id 的情况。

TOOL_CONTEXT_PREPARED 不等于模型已收到消息。查看后续 MODEL_CALL_STARTED 可确认调用尝试包含它，再通过模型 call_id 关联 MODEL_CALL_COMPLETED / FAILED。网络失败时不能宣称供应商收到或模型使用了证据；成功响应也不能证明模型语义上采纳了某项证据。这里不采集或推测模型内部思维链。

## 预算状态与示例

- accepted：正常结果加入消息，空检索也是 accepted，但 sources 为空。
- discarded：工具执行成功或返回错误后，输出超预算；加入的是完整预算错误 JSON，sources 为空。
- skipped：次数或输出预算耗尽，工具未执行，只准备预算错误消息；不生成 RETRIEVAL_COMPLETED。
- tool_error：可恢复工具错误加入消息，不生成成功检索事件。不可恢复异常沿用 TOOL_CALL_FAILED，终止节点。

例如 search_code 返回 A、B 两个代码块，但结果超过字符预算：RETRIEVAL_COMPLETED.hits 仍有 A、B；TOOL_CONTEXT_PREPARED.disposition 为 discarded、sources 为空；下一次模型调用关联的是预算错误消息的 hash。由此可以确定“搜到了，但没有作为代码证据加入下一次调用”。

prepared_result_chars 是分配候选证据编号后的预算检查长度；content_chars 是最后实际准备的 tool.content 长度；reserved_chars 为同批后续调用预留的错误消息空间。字符数不等于 token 数，统计不覆盖完整系统提示与模型消息。

## 内容、版本与范围

- hits 的 rank 为本次工具返回顺序，保留各策略本来的评分字段，不将 distance / score / rrf_score 混成正确率。
- result_scope 固定为 tool_returned_top_k：Hybrid 记录融合后的 Top-K 以及已有候选数量诊断，尚未记录两路融合前完整候选列表。
- 每个块保存 chunk_id、file_id、路径、行号、符号、UTF-8 源码字符串 hash 和字符数。检索阶段没有正式接纳的 source_id，预算后的 sources 才记录分配结果。
- read_source 的整个文件 file_hash 与返回片段 content_sha256 分开；检索块没有整个文件 hash 时为 null，不假造。
- 工具消息 hash 对应原始 JSON 字符串的 UTF-8 编码，包含空格和字段顺序。它与源码内容 hash 是不同对象。
- trace_version=1；任务事件公共 schema_version 和 sequence 仍由数据库事件仓储填写。记录 Embedding 模型 / 维度、Hybrid 候选上限与 RRF 常数；没有独立索引版本号，index_version 明确为 null，借助块 ID 与内容 hash 标识返回内容。仓库固定 commit 继续关联实验准备记录，不把当前 Git HEAD 当作历史版本。
- 事件不保存完整源码、向量、认证头或完整配置。查询受已有工具参数长度限制；chunk 摘要不额外查询数据库。hash 可用于核对，不能单靠 hash 重建已丢失的历史源码；需要完整内容重放时应另做受控快照，而不是假称已实现。
- 当前覆盖只读 / 规划 Agent 的研究工具与计划请求，不宣称编辑生成、Reflection 或其他模型调用都有相同轨迹。

## 验证与使用

只读报告入口已实现：`scripts/export_retrieval_evidence.py`。关联规则与 Markdown 渲染位于纯函数服务 `backend/app/services/retrieval_report_service.py`，不依赖模型、数据库连接或当前工作区。脚本只调用 GET 任务 / 事件接口，并分页直到空页；若返回错序、重复或其他任务事件则报错。超过 10000 个事件显式报错，不静默导出截断报告。

关联本次实验导出（PowerShell，D:\RepoPilot）：

```powershell
.\.venv\Scripts\python.exe -m scripts.export_retrieval_evidence --preparation "$experimentPreparation"
```

也可以独立查询任务，不要求实验准备文件：

```powershell
.\.venv\Scripts\python.exe -m scripts.export_retrieval_evidence --task-id f58111a3-4d12-49d9-8d04-665fd512f53a
```

可选 `--base-url`、`--output-dir`。带 preparation 时默认写入该实验目录的 evidence 子目录；每次创建独立导出目录，保存 evidence.json / evidence.md，不覆盖旧报告。请求失败只需重试导出，不重新运行任务。JSON 保留相关原始事件及其序号、关联结果、实验 / 配置快照和缺口说明；Markdown 提供相同事实的可读展示。

状态 not_recorded 表示未记录新版证据，partial 表示存在缺口或无法唯一关联，recorded 表示记录可关联，不是“模型已使用所有证据”或“任务成功”。运行中任务的事件可能继续追加，导出注明读取至空页时的可见快照，不保证任务结束或单一数据库事务快照。

2026-10-08 已只读导出原成功任务 f58111a3-4d12-49d9-8d04-665fd512f53a 的 25 个真实事件，得到 not_recorded，验证旧任务兼容；未调用模型或修改任务。该任务发生在采集功能加入前，此结果符合预期。新增完整证据的真实落库与关联仍待下一次新实验验证。下一次新实验前重启后端，避免仍由旧进程执行规划。

使用现有事件分页接口，按 sequence 顺序读取。调用 limit 上限沿用原接口；分页直到空列表，不能把第一页误当作全部事件。已有成功实验无需为了补字段重跑或改写报告，下一次真实运行再验收新增事件。

集中模拟验证覆盖三种策略评分与顺序、上下文 hash 与模型参数一致、结果丢弃、零命中、错误 / 跳过隔离、读取片段与整文件 hash、事件保存失败、重复工具 ID、模型超时，以及规划阶段消息引用。报告模块另覆盖分页、错配 / 错序拒绝、精确与歧义关联、旧记录 / 未知版本、模型失败或未完成、重复导出和 CLI 实验关联检查。六份相关测试文件共 59 项通过；没有付费调用或新版事件真实落库验收。
