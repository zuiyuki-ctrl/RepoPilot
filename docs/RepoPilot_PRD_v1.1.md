# RepoPilot — Repository-level Coding Agent & Evaluation System  
## Product Requirements Document v1.1

**项目周期：** 2026 年 9 月  
**项目类型：** AI Agent / AI Coding / Agent Evaluation / Backend Engineering  
**核心技术：** Python、FastAPI、LangGraph、LangChain、PostgreSQL、pgvector、Docker  
**项目目标：** 构建面向真实代码仓库的 Coding Agent + Evaluation System，实现代码检索、任务规划、工具执行、代码修改、测试反馈与失败恢复，并通过可复现的实验量化分析不同策略对成功率、成本与稳定性的影响。

---

# 1. 项目定位

RepoPilot 是面向真实代码仓库的 Coding Agent 与 Evaluation System，用于研究和实现代码理解、上下文构建、任务规划、工具调用、代码修改、测试反馈与失败恢复等核心机制。项目以可观测、可评测、可分析失败原因的单 Agent 系统为目标。

它的核心目标是实现：

```text
用户需求
   ↓
理解代码仓库
   ↓
检索相关代码
   ↓
制定修改计划
   ↓
用户确认
   ↓
修改代码
   ↓
执行测试
   ↓
失败分析与重试
   ↓
输出最终 Diff 与报告
```

最终形成：

> 一个具有状态、工具调用、环境反馈、自动修复和人工确认能力，并能通过 Baseline、Metrics 与 Agent Trace 解释成功和失败的 Repository-level Coding Agent & Evaluation System。

实验主线贯穿开发全过程：

```text
Baseline → 策略改进 → 固定评测集 → Metrics 对比 → Trace 分析 → 下一轮改进
```

本版保留原有工程骨架、技术栈和第一周开发主线；主要升级项目定位与评测要求。文中的验收项均是待完成要求，示例不代表已实现功能或实测成果。

---

# 2. 核心使用场景与能力评测载体

保留三个场景及其端到端功能，将它们作为不同 Agent 能力的评测载体。项目价值在于实现、比较并解释这些能力，而不是仅展示能够问答、修 Bug 或加功能。

| 场景 | 核心评测能力 | 主要验证方式 |
|---|---|---|
| Codebase Q&A | Repository Understanding / Retrieval / Context Engineering | 标注相关文件或符号，计算 Recall@K；按引用位置与答案要点评分 |
| Bug Fix | Tool Use / Test Feedback / Reflection | 修复前复现失败，修复后通过目标测试与既有回归测试；分析恢复过程 |
| Feature Development | Planning / Long-horizon Execution | 检查跨文件步骤覆盖、预定义行为验收与回归测试，分析步骤遗漏和执行成本 |

## 2.1 Codebase Q&A

用户输入：

```text
这个项目的用户认证逻辑在哪里？
```

Agent：

1. 分析问题；
2. 检索代码仓库；
3. 定位相关文件、类和函数；
4. 读取必要上下文；
5. 返回带文件路径和代码位置的解释。

示例输出：

```text
认证逻辑主要位于：

app/api/auth.py
app/services/auth_service.py
app/core/security.py

登录入口位于 auth.py 中，
JWT Token 的创建位于 security.py 中。
```

---

## 2.2 Bug Fix

用户输入：

```text
GET /users/{id} 在用户不存在时返回 500，
希望修改成 404。
```

Agent：

```text
分析任务
 ↓
定位相关代码
 ↓
生成修改计划
 ↓
等待确认
 ↓
修改代码
 ↓
运行测试
 ↓
失败？
 ├─ 是 → 分析错误 → 修改 → 再测试
 └─ 否
 ↓
输出结果
```

---

## 2.3 Feature Development

用户输入：

```text
给 Book 查询接口增加 min_price 和 max_price 参数。
```

Agent 应能够：

```text
分析 API
↓
寻找 Router
↓
寻找 Service
↓
寻找 Repository
↓
寻找 Tests
↓
制定计划
↓
修改代码
↓
补充测试
↓
运行 pytest
↓
输出 Diff
```

这是 RepoPilot 最核心的 Demo 场景，也是 Planning / Long-horizon Execution 的评测载体。验收覆盖 Router、Service、Repository 和 Tests 的必要改动；不能仅凭生成了 Diff 判定成功。

---

# 3. 产品功能范围

## P0：必须完成

一个月结束之前必须完成。

### Repository Management

支持：

- 注册本地 Git Repository
- 扫描代码目录
- 获取 Git Metadata
- 文件索引
- Repository 状态查询
- Repository 重新索引

---

### Code Parsing

支持：

```text
Python
```

第一版只做好 Python。

解析：

- Module
- Class
- Function
- Method

产生：

```text
CodeChunk
```

每个 Chunk 保存：

```text
repository_id
file_path
symbol_name
symbol_type
start_line
end_line
content
metadata
embedding
```

---

### Code Retrieval

至少支持两种搜索：

```text
Keyword Search
Vector Search
```

最终组合为：

```text
Hybrid Retrieval
```

第一阶段：

```text
Vector Search
```

后续加入：

```text
BM25 / PostgreSQL Full Text
        +
Vector Search
        ↓
RRF Fusion
```

---

### Agent Planning

Agent 根据用户需求输出结构化计划：

```json
{
  "summary": "增加价格区间查询功能",
  "steps": [
    {
      "id": 1,
      "description": "修改 Book Router",
      "files": ["app/api/books.py"]
    },
    {
      "id": 2,
      "description": "修改查询逻辑",
      "files": ["app/services/book_service.py"]
    },
    {
      "id": 3,
      "description": "补充测试",
      "files": ["tests/test_books.py"]
    }
  ]
}
```

---

### Human-in-the-loop

计划生成之后：

```text
Agent
 ↓
Plan
 ↓
interrupt()
 ↓
用户 Approve / Reject
```

只有批准后才能进入代码修改阶段。

---

### Code Modification

Agent 可以调用：

```text
read_file
search_code
write_file
replace_code
git_diff
git_status
```

修改只能作用于：

```text
Repository Workspace Copy
```

禁止直接修改用户原始 Repository。

---

### Test Execution

支持：

```text
pytest
```

执行必须发生在：

```text
Docker Sandbox
```

而不是宿主机直接执行未知代码。

---

### Reflection Loop

测试失败：

```text
pytest failed
     ↓
读取 stderr / traceback
     ↓
Reflection
     ↓
分析原因
     ↓
修改代码
     ↓
再次测试
```

限制：

```text
MAX_RETRIES = 3  # 产品上限；Baseline 配置为 1
```

禁止无限循环。retry_count 表示首次执行失败后追加的修复轮数，不包含首次执行；评测必须记录实际 max_retries，比较 Reflection 时应保持重试预算一致。

---

### Final Report

任务结束生成：

```text
任务摘要

修改文件

Git Diff

测试结果

Agent 执行步骤

失败与重试情况

Token 使用量

总耗时
```

---

### Evaluation Framework（P0）

必须随主链路交付：

- Eval Dataset：版本化用例，固定仓库 commit、输入、预期行为、相关文件/符号及验收规则。
- Eval Runner：批量执行固定用例，保存逐次结果，汇总指标，导出 Markdown / JSON 报告。
- Baseline Strategy：保留 Vector Retrieval + Simple Planner + Tool Calling + pytest + 最多一次简单 Retry 的可运行基线。
- Metrics：Task Success Rate、Test Pass Rate、Retrieval Recall@K、Tool Call Count、Retry Count、Latency、Token Usage、Cost。
- Failure Taxonomy：基于 Trace 和验收证据记录失败类别，允许人工复核。
- Agent Trace：以 task_events 为持久化数据源，支持时间线查询、失败定位和不同策略的逐例对比。

第一周先完成检索用例与离线报告；第二周接入 Agent 执行结果和 Trace；月底完成统一 Runner、数据库持久化及对比报告。复杂可视化不是 P0 前置条件，CLI 与结构化报告即可验收。详细要求见第 20～24 节。

---

# 4. P1 功能

核心链路完成后实现。

包括：

- AST-aware Retrieval
- Reranker
- Context Compression
- WebSocket Agent Streaming
- Task Checkpoint
- Agent 恢复
- Redis Cache
- MCP Tool Server
- 高级 Agent Trace Viewer（交互式筛选与对比；基础 Trace 查询、分析和报告属于 P0）
- Git Branch 自动创建

---

# 5. P2 功能

有余力再做。

包括：

- GitHub Repository URL 自动 Clone
- Pull Request 自动生成
- 多语言代码支持
- Java / TypeScript Parser
- Multi-Agent
- IDE Plugin
- GitHub App
- CI/CD Agent
- Kubernetes

原则：

> P0 没做完之前，禁止进入 P2。

---

# 6. 明确不做什么

RepoPilot v1.1：

```text
不做通用聊天机器人
不做网页搜索 Agent
不做多 Agent 辩论
不做自动合并代码
不直接修改 main/master
不执行宿主机任意 shell
不追求支持所有语言
```

先把 Python Coding Agent 做深。

---

# 7. 系统架构

```text
                     Frontend
                        │
                HTTP / WebSocket
                        │
                        ▼
                    FastAPI
                        │
                 Task Service
                        │
                        ▼
                ┌──────────────┐
                │  LangGraph   │
                │ Coding Agent │
                └───────┬──────┘
                        │
          ┌─────────────┼──────────────┐
          │             │              │
          ▼             ▼              ▼
       Tools          Retrieval      Checkpoint
          │             │              │
     ┌────┼────┐     PostgreSQL     PostgreSQL
     │    │    │      pgvector
     ▼    ▼    ▼
   File  Git  Docker
               │
               ▼
             pytest
```

---

Evaluation 作为旁路接入现有架构，不改变 Agent 执行主链：

```text
eval_cases → Eval Runner → Retrieval / Task Service → LangGraph / Sandbox
                  │                                  │
                  │                              task_events
                  │                                  │
                  └──────── Metrics / Failure Analysis┘
                                      │
                                  eval_runs
                                      │
                              Markdown / JSON Report
```

---

# 8. Agent 工具设计

v1 提供：

```python
list_files()
```

查看目录结构。

```python
read_file(path)
```

读取文件。

```python
search_code(query)
```

关键词搜索。

```python
semantic_search(query)
```

向量搜索。

```python
replace_code(...)
```

修改局部代码。

```python
write_file(...)
```

创建文件。

```python
git_diff()
```

检查修改。

```python
git_status()
```

查看工作区状态。

```python
run_tests(...)
```

运行测试。

---

# 9. LangGraph 工作流

```text
START
  │
  ▼
analyze_request
  │
  ▼
retrieve_context
  │
  ▼
create_plan
  │
  ▼
human_approval
  │
  ├──── Reject ────→ END
  │
 Approve
  │
  ▼
execute_plan
  │
  ▼
run_tests
  │
  ▼
tests_passed?
  │
 ┌┴───────────┐
 │            │
No           Yes
 │            │
 ▼            ▼
reflect      finalize
 │            │
 └── retry ───┘
              │
              ▼
             END
```

---

工作流执行约束：

- question 任务在检索与读取上下文后生成带引用的答案并进入 finalize，不进入代码修改和 pytest。
- 修改任务测试失败后，reflect 应回到 execute_plan，再次执行 run_tests；上图 retry 表示这个修复循环，不是直接跳到 finalize 宣告成功。
- 达到 max_retries 后记录 failed 并生成失败报告。
- 批量评测仍保留审批规则：仅对用户预先授权的评测仓库副本与工具范围使用固定审批策略，并写入 HUMAN_APPROVED 事件；其余任务等待人工确认。

---

# 10. LangGraph State 设计

```python
from typing import Annotated, Literal
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):

    # ---------- Identity ----------

    task_id: str
    repository_id: str

    # ---------- Evaluation Context ----------
    # 普通交互任务为 None；评测标签和预期答案不进入 Agent State。
    eval_run_id: str | None
    agent_version: str
    strategy_config: dict

    # ---------- Conversation ----------

    messages: Annotated[list[BaseMessage], add_messages]

    user_request: str

    # ---------- Requirement ----------

    task_type: Literal[
        "question",
        "bug_fix",
        "feature",
        "refactor"
    ]

    requirement_summary: str

    # ---------- Retrieval ----------

    search_queries: list[str]

    candidate_files: list[str]

    retrieved_chunks: list[dict]

    # ---------- Planning ----------

    plan: list[dict]

    current_step: int

    approved: bool | None

    # ---------- Execution ----------

    modified_files: list[str]

    diff: str | None

    # ---------- Testing ----------

    test_command: str | None

    test_stdout: str | None

    test_stderr: str | None

    tests_passed: bool | None

    # ---------- Reflection ----------

    retry_count: int
    max_retries: int

    reflection: str | None

    # ---------- Runtime ----------

    status: Literal[
        "created",
        "analyzing",
        "retrieving",
        "planning",
        "waiting_approval",
        "executing",
        "testing",
        "reflecting",
        "completed",
        "failed",
        "rejected"
    ]

    error: str | None

    # ---------- Output ----------

    final_report: str | None
```

这里有一个非常重要的原则：

> State 只保存“Agent 当前工作所需要的状态”。

不要把整个数据库对象全部塞进 State。

---

# 11. 数据库设计

数据库：

```text
PostgreSQL
+
pgvector
```

第一版核心表：

```text
repositories
repository_files
code_chunks
agent_tasks
task_events
eval_cases
eval_runs
```

---

## 11.1 repositories

保存代码仓库信息。

| 字段 | Python 类型 | 可空 | 用途 |
|---|---|---|---|
| `id` | `UUID` | 否 | 唯一标识 |
| `name` | `str` | 否 | 展示名称，不要求全局唯一 |
| `source_path` | `str` | 否 | 用户原始仓库路径 |
| `workspace_path` | `str` | 是 | 工作副本路径，创建前为空 |
| `git_branch` | `str` | 是 | 分支名；固定 commit 可能没有分支 |
| `commit_hash` | `str` | 是 | Git 信息读取完成前为空 |
| `language` | `str` | 否 | 第一版为 `python` |
| `status` | `str` | 否 | 初始为 `registered` |
| `created_at` | `datetime` | 否 | 创建时间 |
| `updated_at` | `datetime` | 否 | 最近修改时间 |
| `indexed_at` | `datetime` | 是 | 尚未索引时为空 |

`source_path`

表示用户原 Repository。

`workspace_path`

表示：

```text
RepoPilot Workspace Copy
```

Agent 永远修改 workspace。

---

## 11.2 repository_files

保存文件 Metadata。

| 字段 | 类型 | 用途 |
|---|---|---|
| `id` | UUID | 文件记录的唯一标识 |
| `repository_id` | UUID | 所属仓库 |
| `path` | Text | 仓库内相对路径，例如 `app/main.py` |
| `language` | String(32) | 文件语言 |
| `file_hash` | String(64) | 文件内容的 SHA-256 摘要 |
| `size` | BigInteger | 文件字节数 |
| `created_at` | 带时区时间 | 记录创建时间 |
| `updated_at` | 带时区时间 | 记录更新时间 |

关系：

```text
Repository
   │
   └── 1 : N
          │
          ▼
    RepositoryFile
```

---

## 11.3 code_chunks

这是 RAG 最核心的表。

| 字段 | Python 类型 | 数据库类型或配置 |
|---|---|---|
| `id` | `UUID` | 主键，`default=uuid4` |
| `repository_id` | `UUID` | 外键指向 `repositories.id` |
| `file_id` | `UUID` | 外键指向 `repository_files.id` |
| `file_path` | `str` | `Text` |
| `symbol_name` | `str` | `Text` |
| `symbol_type` | `str` | `String(32)` |
| `start_line` | `int` | `Integer` |
| `end_line` | `int` | `Integer` |
| `content` | `str` | `Text` |
| `created_at` | `datetime` | 带时区，数据库默认当前时间 |
| `updated_at` | `datetime` | 带时区，默认及更新方式参考文件模型 |

例如：

```text
symbol_name = get_book
symbol_type = function

file_path =
app/api/books.py

start_line = 42
end_line = 71
```

后续建立：

```text
HNSW INDEX
```

用于向量检索。

---

# 11.4 agent_tasks

每一次 Agent 工作都是一个 Task。

| 字段 | Python 类型 | 数据库与默认值 |
|---|---|---|
| `id` | `UUID` | 主键，`default=uuid4` |
| `repository_id` | `UUID` | 外键 `repositories.id`，非空 |
| `user_request` | `str` | `Text`，非空 |
| `task_type` | `str` | `String(32)`，默认 `"question"` |
| `status` | `str` | `String(32)`，默认 `"created"` |
| `created_at` | `datetime` | 带时区，`server_default=func.now()` |
| `started_at` | `datetime \| None` | 带时区，可空 |
| `completed_at` | `datetime \| None` | 带时区，可空 |
| `result` | `dict[str, Any] \| None` | PostgreSQL `JSONB`，可空 |
| `error` | `str \| None` | `Text`，可空 |

一个用户请求：

```text
修复 users API 返回 500 的问题
```

对应一个：

```text
AgentTask
```

---

# 11.5 task_events

保存 Agent 执行轨迹。task_events 是 P0 Agent Trace 的持久化数据源，同时服务任务状态展示、失败归因和 Evaluation；WebSocket 仅是事件的传输方式。

```text
task_events
──────────────────────────────
id                  UUID PK

task_id             UUID FK

event_type          VARCHAR

node_name           VARCHAR

message             TEXT

payload             JSONB

created_at          TIMESTAMP
```

例如：

```text
RETRIEVAL_STARTED

PLAN_CREATED

HUMAN_APPROVED

FILE_MODIFIED

TEST_FAILED

REFLECTION_STARTED

TEST_PASSED
```

以后前端：

```text
Agent 正在做什么
```

主要就是从这里获取。

这张表以后也非常适合：

```text
Agent Evaluation
Agent Trace Analysis
```

---

## 11.6 eval_cases

保存版本化评测用例。第一周可先以 JSON 维护，后续按相同字段导入数据库。

```text
eval_cases
────────────────────────────────────────
id                  UUID PK
repository_id       UUID FK → repositories.id
name                VARCHAR
task_type           VARCHAR       # question / bug_fix / feature
eval_scope          VARCHAR       # retrieval / end_to_end
user_request        TEXT
expected_behavior   TEXT
expected_targets    JSONB         # file_path + qualified symbol_name；或文件级目标
test_command        TEXT NULL
acceptance_config   JSONB         # 答案要点、测试 ID、行为约束、超时等
repository_commit   VARCHAR
dataset_version     VARCHAR
split               VARCHAR       # dev / held_out
tags                JSONB
created_at          TIMESTAMP
```

同一 dataset_version 内保持用例内容不变；修改标签或验收条件时创建新版本。expected_targets 不依赖会随重新索引变化的 chunk UUID，使用固定 commit 下的路径与限定符号名。每例统一匹配粒度，不混用文件和符号计算 Recall。

expected_behavior、expected_targets 和验收测试仅供评估器使用，不作为答案提示传给 Agent。验收测试由 Runner 在隔离环境中加载，Agent 新增的测试不能替代预先固定的验收测试。

---

## 11.7 eval_runs

一行表示“一个用例在一种策略下的一次执行”，不表示整个批次；重复执行追加记录。

```text
eval_runs
────────────────────────────────────────
id                  UUID PK
batch_id            UUID          # 同批次的聚合标识，无需新增批次表
eval_case_id        UUID FK → eval_cases.id
task_id             UUID FK → agent_tasks.id NULL
agent_version       VARCHAR       # 实现版本或 commit
strategy_config     JSONB         # 检索、模型、prompt 版本、预算与审批策略
environment_config  JSONB         # 仓库 commit、镜像、依赖、索引/Embedding 版本
status              VARCHAR       # queued / running / completed / error / cancelled
success             BOOLEAN NULL
tests_passed        BOOLEAN NULL  # 固定验收测试整体是否通过
tests_passed_count  INTEGER NULL
tests_total_count   INTEGER NULL
retrieval_metrics   JSONB         # recall_at_1 / recall_at_3 / recall_at_5
tool_calls          INTEGER
retry_count         INTEGER
latency_ms          BIGINT
input_tokens        BIGINT NULL
output_tokens       BIGINT NULL
cost                NUMERIC NULL
cost_currency       VARCHAR NULL
failure_type        VARCHAR NULL
failure_details     JSONB         # 证据 event IDs、次要原因、分类依据
artifacts           JSONB         # 排名结果、答案、Diff、测试报告路径等
created_at          TIMESTAMP
started_at          TIMESTAMP NULL
completed_at        TIMESTAMP NULL
```

端到端运行必须关联独立的 agent_tasks；纯检索运行允许 task_id 为空，但必须保存 query、完整 Top-5 排名、目标匹配和配置。Trace 通过 eval_runs.task_id → task_events.task_id 获取，不复制整条 Trace 到 eval_runs。

建议索引：eval_cases(repository_id, dataset_version)、eval_runs(batch_id)、eval_runs(eval_case_id, agent_version)、task_events(task_id, created_at)。事件 payload 额外携带 task 内递增 sequence，确保同时间戳事件也可稳定排序，并对 (task_id, sequence) 做唯一约束或等效校验。

success / tests_passed / token / cost 的未知或不适用值为 NULL，不伪装成 false 或 0；终态失败必须保留原因，运行中 success 为 NULL。

---

# 12. 数据关系

```text
repositories
     │
     ├───────────────┐
     │               │
     ▼               ▼
repository_files   agent_tasks
     │               │
     ▼               ▼
code_chunks       task_events
```

关系：

```text
Repository
1:N RepositoryFiles

RepositoryFile
1:N CodeChunks

Repository
1:N AgentTasks

AgentTask
1:N TaskEvents
```

---

新增评测关系：

```text
Repository 1:N EvalCases
EvalCase   1:N EvalRuns
AgentTask 1:0..1 EvalRun（端到端评测每次创建独立 Task）
EvalRun → AgentTask → TaskEvents（Trace）
```

纯检索 EvalRun 无需 AgentTask；同一批次通过 batch_id 聚合。

---

# 13. API 设计

## Repository

```http
POST /api/v1/repositories
```

注册代码仓库。

---

```http
GET /api/v1/repositories/{repository_id}
```

查看 Repository。

---

```http
POST /api/v1/repositories/{repository_id}/index
```

建立代码索引。

---

```http
GET /api/v1/repositories/{repository_id}/files
```

查看文件。

---

## Retrieval

```http
POST /api/v1/repositories/{repository_id}/search
```

测试代码搜索。

Request：

```json
{
  "query": "用户认证逻辑",
  "top_k": 5
}
```

---

## Agent Task

```http
POST /api/v1/tasks
```

创建任务。

---

```http
GET /api/v1/tasks/{task_id}
```

查看任务。

---

```http
POST /api/v1/tasks/{task_id}/approve
```

批准计划。

---

```http
POST /api/v1/tasks/{task_id}/reject
```

拒绝计划。

---

```text
WS /api/v1/tasks/{task_id}/stream
```

实时 Agent Event。

---

## Trace 查询（P0）

```http
GET /api/v1/tasks/{task_id}/events
```

按 sequence 分页返回持久化事件，支持离线分析和事件回放；实时 WebSocket Streaming 仍为 P1。

Evaluation P0 使用 scripts/run_eval.py 执行用例集、选择策略并输出报告，避免为第一周增加完整评测管理 API 的工作量。后续可增加用例与运行查询接口。

---

# 14. 项目目录结构

```text
repopilot/
│
├── backend/
│   │
│   ├── app/
│   │   │
│   │   ├── main.py
│   │   │
│   │   ├── api/
│   │   │   ├── dependencies.py
│   │   │   └── routes/
│   │   │       ├── repositories.py
│   │   │       ├── search.py
│   │   │       └── tasks.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   └── exceptions.py
│   │   │
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   ├── models/
│   │   │   │   ├── repository.py
│   │   │   │   ├── repository_file.py
│   │   │   │   ├── code_chunk.py
│   │   │   │   ├── agent_task.py
│   │   │   │   ├── task_event.py
│   │   │   │   ├── eval_case.py
│   │   │   │   └── eval_run.py
│   │   │   │
│   │   │   └── repositories/
│   │   │       ├── repository_repo.py
│   │   │       ├── chunk_repo.py
│   │   │       └── task_repo.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── repository.py
│   │   │   ├── search.py
│   │   │   └── task.py
│   │   │
│   │   ├── services/
│   │   │   ├── repository_service.py
│   │   │   ├── indexing_service.py
│   │   │   └── task_service.py
│   │   │
│   │   ├── rag/
│   │   │   ├── parser.py
│   │   │   ├── chunker.py
│   │   │   ├── embeddings.py
│   │   │   ├── vector_store.py
│   │   │   ├── keyword_search.py
│   │   │   └── retriever.py
│   │   │
│   │   ├── agent/
│   │   │   ├── state.py
│   │   │   ├── graph.py
│   │   │   │
│   │   │   ├── nodes/
│   │   │   │   ├── analyze.py
│   │   │   │   ├── retrieve.py
│   │   │   │   ├── planner.py
│   │   │   │   ├── executor.py
│   │   │   │   ├── tester.py
│   │   │   │   ├── reflection.py
│   │   │   │   └── reporter.py
│   │   │   │
│   │   │   └── prompts/
│   │   │       ├── planner.py
│   │   │       └── reflection.py
│   │   │
│   │   └── tools/
│   │       ├── filesystem.py
│   │       ├── git.py
│   │       ├── search.py
│   │       └── testing.py
│   │
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── fixtures/
│   │
│   ├── migrations/
│   │
│   ├── pyproject.toml
│   └── Dockerfile
│
├── frontend/
│
├── sandbox/
│   └── Dockerfile
│
├── evals/
│   ├── datasets/
│   ├── runners/
│   ├── metrics.py
│   ├── failure_taxonomy.py
│   ├── trace_analysis.py
│   ├── configs/
│   └── reports/
│
├── scripts/
│   ├── index_repo.py
│   └── run_eval.py
│
├── docs/
│   ├── architecture.md
│   └── decisions/
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

有一个设计原则：

```text
API
↓
Service
↓
Repository / RAG / Agent
↓
Infrastructure
```

不要：

```text
FastAPI Router
↓
直接 SQL
↓
直接调用 LLM
↓
直接操作文件
```

否则项目很快会变成一坨。

---

# 15. 第一周开发目标

第一周只解决：

> **让 RepoPilot 真正“认识一个代码仓库”。**

Agent 自动改代码放第二周。

---

# Day 1 — Project Bootstrap

完成：

```text
Git Repository
Python Environment
FastAPI
Configuration
PostgreSQL
pgvector
Docker Compose
```

建立：

```text
backend/
docker-compose.yml
.env.example
```

接口：

```http
GET /health
```

返回：

```json
{
  "status": "ok"
}
```

验收：

```text
docker compose up

FastAPI ✅
PostgreSQL ✅
pgvector ✅
```

---

# Day 2 — Database Layer

完成 SQLAlchemy Models：

```text
Repository
RepositoryFile
CodeChunk
AgentTask
TaskEvent
```

完成：

```text
Alembic Migration
Database Session
Repository Pattern
```

验收：

```text
migration 成功

可以创建 Repository

可以查询 Repository
```

---

# Day 3 — Repository Import

实现：

```python
register_repository()
```

完成：

```text
扫描目录
过滤 .git
过滤 .venv
过滤 node_modules
过滤 __pycache__
过滤 binary files
```

记录：

```text
path
size
hash
language
```

同时生成：

```text
Workspace Copy
```

验收：

给 RepoPilot 一个 FastAPI 项目：

```text
demo-project/
```

数据库可以看到：

```text
42 files indexed
```

---

# Day 4 — Python Code Parser

使用：

```text
Tree-sitter
```

或者第一版：

```text
Python ast
```

优先建议第一周使用：

```text
Python ast
```

原因：

简单、稳定、够用。

解析：

```text
Class
Function
AsyncFunction
Method
```

例如：

```python
class UserService:

    def get_user(self):
        ...
```

产生：

```text
UserService
UserService.get_user
```

验收：

```text
文件
↓
AST
↓
CodeChunks
```

数据库：

```text
code_chunks
```

出现真实数据。

---

# Day 5 — Embedding + Vector Search

完成：

```text
CodeChunk
↓
Embedding Model
↓
Vector
↓
pgvector
```

实现：

```python
semantic_search(
    repository_id,
    query,
    top_k
)
```

例如：

```text
query：

用户身份认证在哪里实现？
```

返回：

```text
auth.py
security.py
dependencies.py
```

并包含：

```text
score
file_path
symbol_name
content
```

---

# Day 6 — Search API

实现：

```http
POST /api/v1/repositories/{id}/search
```

支持：

```json
{
    "query": "JWT token 创建逻辑",
    "top_k": 5
}
```

响应：

```json
{
    "results": [
        {
            "file_path": "app/core/security.py",
            "symbol_name": "create_access_token",
            "start_line": 20,
            "end_line": 38,
            "score": 0.89
        }
    ]
}
```

同时完成：

```text
基本 Error Handling
Logging
Pydantic Schema
```

---

# Day 7 — First Demo + Tests + Code Retrieval Evaluation

第一周最终 Demo：

```text
启动 RepoPilot
       ↓
注册 FastAPI Repository
       ↓
扫描 Repository
       ↓
AST Parsing
       ↓
Code Chunking
       ↓
Embedding
       ↓
pgvector
       ↓
用户输入：

"用户认证逻辑在哪里？"

       ↓
返回相关代码
```

同时编写：

```text
parser tests
repository tests
retrieval tests
API integration tests
```

---

新增 Code Retrieval Eval Cases：

1. 基于 Demo 仓库的固定 commit，手工标注至少 10 个真实问题及其相关文件/符号。
2. 覆盖认证、数据库、路由、业务逻辑、异常处理等仓库实际存在的模块；下列仅为题型示例，路径必须按实际仓库核验。
3. 对每个问题执行 Vector Search，保存有序 Top-5 结果并计算 Recall@1/3/5。
4. 生成逐例明细和宏平均汇总，记录未命中的例子及初步原因，作为后续 Hybrid Retrieval 的对照基线。

| 示例问题 | 标注目标示意（需核验） |
|---|---|
| JWT token 在哪里生成？ | app/core/security.py:create_access_token |
| 数据库 session 在哪里创建？ | app/db/session.py |
| 404 异常在哪里处理？ | 实际异常处理文件或符号 |

文件级与符号级用例分别汇总，计算口径见第 21 节。第一周不要求构建完整 Agent Runner；scripts/run_eval.py 先支持 retrieval 模式即可。

交付：

```text
evals/datasets/code_retrieval_v1.json
evals/configs/vector_baseline.json
evals/reports/retrieval_baseline_v1.json
evals/reports/retrieval_baseline_v1.md
```

Day 1～6 主线不变；eval_cases / eval_runs 的数据库模型与迁移可在第二周接入，不阻塞第一周 JSON 评测。

---

# 16. 第一周验收标准

第一周结束必须满足以下全部条件。

### Repository

```text
✅ 可以导入真实 Python Repository
✅ 文件 Metadata 写入数据库
✅ 自动创建 Workspace Copy
```

### Parsing

```text
✅ Python 函数可以识别
✅ Class 可以识别
✅ Method 可以识别
✅ 保存行号
```

### RAG

```text
✅ Code Chunk Embedding
✅ pgvector 存储
✅ Top-K Search
```

### Backend

```text
✅ FastAPI 正常运行
✅ PostgreSQL 正常运行
✅ Docker Compose 一键启动
```

### Engineering

```text
✅ pytest
✅ logging
✅ .env
✅ migration
✅ README
```

---

### Retrieval Evaluation（新增，必须完成）

- 至少 10 个已核验的 Code Retrieval Eval Cases，每例有非空 expected_targets、固定 repository_commit 和 dataset_version。
- 可用同一条评测入口批量重跑，保存完整 Top-5 排名与参数。
- 报告包含逐例及按粒度分组的宏平均 Recall@1、Recall@3、Recall@5，核对 0 ≤ Recall@1 ≤ Recall@3 ≤ Recall@5 ≤ 1。
- 保留零命中与执行失败用例；执行失败在汇总中按 0 计分并另报数量，禁止删除失败例以抬高分数。
- 报告列出未命中案例和初步原因；固定索引与确定性配置下重跑应得到相同结果，若存在差异须记录来源。

第一周验收以“标注可信、计算正确、结果可重跑”为门槛，不预设未经验证的 Recall 数值目标。完成 Baseline 后，再据实设置下一阶段改善目标。

---

# 17. 第一周不允许做的事情

暂时不要碰：

```text
LangGraph Agent
Multi-Agent
MCP
Frontend
Redis
Reflection
Docker Sandbox
WebSocket
Reranker
BM25
```

这些都不是第一周的问题。

第一周只有一个问题：

> RepoPilot 能不能准确理解和检索一个真实代码仓库？

如果这个地基不稳，后面的 Agent 再聪明也没有意义。

---

# 18. 第二周入口条件

只有第一周验收全部通过以后才进入：

```text
LangGraph
```

第二周目标：

```text
User Requirement
      ↓
Agent
      ↓
Search Repository
      ↓
Plan
      ↓
Human Approval
      ↓
Code Modification
      ↓
pytest
      ↓
Reflection
```

这才正式进入：

> 可评测、可观测的 AI Software Engineering Agent。第二周需保留最简 Baseline 配置，接入 task_events 和逐次运行结果，再开展 Reflection 对照实验。

---

# 19. RepoPilot v1.1 的核心技术主线

整个九月开发过程中始终记住这一条：

```text
Repository Understanding
        ↓
Code Retrieval
        ↓
Context Engineering
        ↓
Planning
        ↓
Tool Calling
        ↓
Code Editing
        ↓
Sandbox Execution
        ↓
Feedback
        ↓
Reflection
        ↓
Evaluation
```

最终项目的真正卖点不是：

```text
用了 LangChain
用了 LangGraph
用了 FastAPI
```

而是：

> **构建面向真实代码仓库的 Coding Agent & Evaluation System，串联代码理解、上下文构建、计划执行、隔离测试与失败恢复，并用可复现的 Baseline 对照、指标和 Trace 证据分析不同策略对成功率、成本与稳定性的影响。**

最终展示重点：

- 完整工程闭环：保留 FastAPI、LangGraph、PostgreSQL/pgvector、Workspace Copy、Docker Sandbox 和 Human-in-the-loop。
- 可复现评测：用同一套版本化任务比较 Vector / Hybrid Retrieval、简单 Retry / Reflection。
- 可分析失败：从 eval_runs 追溯 task_events，定位失败节点并给出可核查证据。
- 可解释取舍：展示成功率与 Token、延迟、成本的共同变化，保留无提升和负向结果。

README 与简历中的数字必须来自实际报告，并注明用例规模、版本、配置与限制；不使用讨论中的示例成功率作为项目成果。
---

# 20. Baseline Strategy 与实验设计（P0）

## 20.1 最小可运行 Baseline

```text
Vector Retrieval
        ↓
Simple Planner（一次生成结构化计划）
        ↓
Human Approval
        ↓
Tool Calling / Code Editing
        ↓
pytest in Docker Sandbox
        ↓
最多一次 Simple Retry
        ↓
Final Report + Metrics + Trace
```

Simple Retry 将测试错误及必要代码交回执行节点，不增加专门的失败分类、重新规划或多轮 Reflection 策略。question 任务只运行检索、上下文读取与回答链路；纯 retrieval 用例不调用 Planner 或 pytest。

Baseline 是保留用于比较的配置，不替代 P0 的最终 Hybrid Retrieval 与 Reflection 功能。Baseline 的 max_retries=1；产品最多允许 3 次，但不得把更高重试预算带来的收益全部归因于 Reflection。

## 20.2 对照顺序

| 配置 | 变化 | 目的 | 优先级 |
|---|---|---|---|
| B0 | Vector + Simple Planner + Simple Retry，max_retries=1 | 建立最小端到端基线 | P0 |
| B1 | 仅将 Vector 换成 Hybrid，其他同 B0 | 评估检索改进 | P0 |
| B2 | 基于 B1，将 Simple Retry 换成 Reflection，max_retries 仍为 1 | 评估失败恢复策略 | P0 |
| B3 | 基于 B2，仅将 max_retries 增至 3 | 单独观察额外预算的收益与成本 | 可选实验 |
| 后续配置 | 分别加入 AST-aware Retrieval / Reranker / Context Compression | 逐项验证效果与代价 | P1 |

实现 AST 分块仍为 P0；利用依赖关系扩展检索的 AST-aware Retrieval 保持 P1。不要将已有 Python AST 解析误计为新增检索策略收益。

## 20.3 公平比较与可复现性

- 固定仓库 commit、用例版本、模型标识、温度、Prompt 版本、Embedding/索引版本、容器镜像和依赖。
- 除待研究变量外，保持 Top-K、上下文预算、Token/工具调用上限、超时、审批策略和重试预算相同。
- 每次代码任务从干净的独立 Workspace Copy 开始；执行前验证基线环境，运行后保存 Diff 和测试报告，避免上一次修改污染下一例。
- dev 用例用于调试，held_out 用例用于最终对比；禁止将保留集答案写入 Prompt。记录两部分结果，不把调参集成绩当作泛化结论。
- 每个案例每个配置至少执行一次；端到端关键对比建议重复 3 次并报告重复次数和波动。单次运行仅作为探索性结果。
- Runner 预先设定执行上限；达到上限记录失败和原因，禁止无限重试。
- 报告成功率变化的百分点、成本/延迟变化和逐例胜负；不预设每次改动一定提升。

---

# 21. Metrics 定义（P0）

## 21.1 Task Success Rate

```text
Task Success Rate = 达到预定义验收要求的运行数 / 已启动的端到端运行总数
```

按 question / bug_fix / feature 分组报告，并标注样本数。已启动后的超时、环境错误和取消保留在分母中、视为未成功；未启动的 queued 用例不进入分母，必须单独列出。若另报剔除基础设施错误的诊断指标，必须同时展示原始指标和剔除数量。

成功条件：

- question：满足用例预先定义的答案要点，引用路径/符号真实存在且支持回答。按固定 rubric 人工复核并保存依据；仅检索命中不等于答案正确。
- bug_fix：预定义目标测试在修改前能够复现问题，修改后目标测试及既有回归测试通过，且符合 expected_behavior。
- feature：固定功能验收测试及既有回归测试通过，必要行为、边界条件与交付项满足验收规则。
- 纯 retrieval 用例报告 Recall，不混入端到端 Task Success Rate。

Agent 自报 completed、生成 Diff 或自写测试通过都不是独立成功证据。

## 21.2 Test Pass Rate

对具有固定测试集且实际执行了测试的运行：

```text
单次 Test Pass Rate = passed / (passed + failed + errors + skipped)
```

skipped 不视为通过；只有用例事先明确排除的非必需测试才不进入固定测试集。汇总同时报告微平均（通过数总和 / 测试数总和）和用例级 tests_passed=true 的比例。

仅采用最终轮测试结果计算最终 Test Pass Rate，中间轮结果保存在 Trace，用于恢复分析。收集失败或测试未执行导致计数不可知时记为 NULL，并报告未完成测试的运行数；这些运行不能判为任务成功。tests_passed=true 要求所有必需测试实际执行且通过。

## 21.3 Retrieval Recall@K

每个用例 c 的人工标注相关目标集合为 G_c，检索前 K 条结果按预定文件/符号粒度映射后为 R_c,K：

```text
Recall@K(c) = |G_c ∩ R_c,K| / |G_c|
Macro Recall@K = 对同一粒度的全部用例 Recall@K(c) 取平均
K ∈ {1, 3, 5}
```

- G_c 不得为空；无效标签应在运行前校验并阻止该批次，不能静默跳过。
- 先截取前 K 个检索结果，再映射与去重；同一目标重复出现仅计一次命中，不从后续结果补足 K 个目标。
- 文件级目标使用规范化仓库相对路径；符号级目标使用路径与限定符号名精确匹配。
- 多目标用例命中任意一个只算部分召回；“至少命中一次”的 Hit@K 如需记录，应另列，不能叫 Recall@K。
- 返回少于 K 条时按实际结果计算；执行错误该例记 0，并保留 error 标记。
- 第一周评估 Search API 的首次 query 排名；后续 Agent 多轮检索分别记录各次查询，不能将多轮结果合集伪装成首次 Recall@K。

## 21.4 资源与效率

| 指标 | 口径 |
|---|---|
| Tool Call Count | 实际发起的工具调用次数，含参数错误和失败调用；以唯一 tool_call_id 去重，避免 started/completed 重复计数 |
| Retry Count | 首次执行后追加的修复轮数；同时记录 max_retries |
| Latency | 从运行开始至终态的墙钟时间，保存 latency_ms；单独记录人工等待时间以解释差异 |
| Token Usage | 全部模型调用的 input_tokens / output_tokens 总和，包含重试；Embedding 使用量另列 |
| Cost | 根据实际用量和保存的计价快照估算，记录币种、模型、计价日期；未知为 NULL |
| Failure Category | 终态失败的主要原因及证据；次要原因、恢复失败另存 failure_details |

延迟和成本均展示样本数、均值；样本足够时补充中位数、P95。Token/成本缺失时报告覆盖率，不按 0 填补。缓存 Token、Embedding 或其他费用若计入成本，需分项说明。

---

# 22. Failure Taxonomy（P0）

分类对象是未成功的运行。优先定位有证据支持的根因，不能仅按最后一个报错节点分类。

| 类别 | 定义 | 典型证据 |
|---|---|---|
| RETRIEVAL_FAILURE | 未检索到必要文件或符号 | 查询排名、人工标签、后续核验 |
| CONTEXT_FAILURE | 已找到目标，但送入模型的上下文遗漏、截断或过期 | 检索结果与实际上下文清单的差异 |
| PLANNING_FAILURE | 计划遗漏必要步骤或依赖关系 | 计划与固定行为验收的差异 |
| TOOL_FAILURE | 工具选错、参数无效或调用执行失败 | 工具参数、错误码、调用结果 |
| EDIT_FAILURE | 修改本身引入语法或逻辑错误，或改错位置 | Diff、语法检查、断言失败 |
| TEST_FAILURE | 测试基础设施、依赖、收集或容器环境失败 | pytest 收集错误、容器日志；通常断言失败不归此类 |
| REASONING_FAILURE | 上下文充分但输出判断与明确证据矛盾 | 正确上下文、可观察输出和人工复核；不能仅凭猜测 |
| RECOVERY_FAILURE | 重试或 Reflection 未有效修复问题 | 前后轮错误、修改与预算记录 |
| BUDGET_EXCEEDED | 达到时间、Token 或工具调用上限 | 限额事件与计数 |
| APPROVAL_REJECTED | 计划被拒绝导致任务未完成 | 审批事件 |
| CANCELLED | 已启动后被取消 | 取消事件 |
| UNKNOWN | 证据不足，尚不能可靠归因 | 缺失项和待复核说明 |

执行规则：

1. 每个失败运行设置一个主要 failure_type；允许记录多个次要原因。
2. 根因明确时以根因为主要类别。例如 EDIT_FAILURE 后多轮修复无效，RECOVERY_FAILURE 作为次要类别，避免重复计入主要失败分布。
3. 保存关联 event IDs、错误摘要、分类来源（规则/人工）、复核状态与说明。
4. 规则可先生成候选分类，人工复核代表性案例；禁止将模型猜测作为已验证根因。
5. 报告主要类别计数与占失败运行的比例，UNKNOWN 和环境错误不隐藏。

---

# 23. Agent Trace 分析（P0）

## 23.1 数据源与事件协议

task_events 是 Trace 的权威持久化来源；eval_runs 存汇总和证据引用，前端、CLI 和报告都读取相同事件。

保留已有事件，并补齐：

```text
TASK_STARTED / TASK_COMPLETED / TASK_FAILED
RETRIEVAL_STARTED / RETRIEVAL_COMPLETED
CONTEXT_BUILT
PLAN_CREATED
HUMAN_APPROVED / HUMAN_REJECTED
MODEL_CALL_STARTED / MODEL_CALL_COMPLETED / MODEL_CALL_FAILED
TOOL_CALL_STARTED / TOOL_CALL_COMPLETED / TOOL_CALL_FAILED
FILE_MODIFIED
TEST_STARTED / TEST_FAILED / TEST_PASSED
REFLECTION_STARTED / REFLECTION_COMPLETED
BUDGET_EXCEEDED / TASK_CANCELLED
```

payload 统一记录 sequence、schema_version、step_id、attempt、开始/结束时间或 duration_ms；按事件类型补充：

- Retrieval：query、检索策略、有序结果、score、路径/符号、索引版本。
- Context：实际选入的目标、内容 hash 或受控快照引用、Token 数、截断情况。
- Plan：结构化步骤、关联文件与计划修订。
- Tool：tool_call_id、工具名、参数摘要、返回状态、耗时与错误；文件修改关联 Diff。
- Model：call_id、模型/Prompt 版本、用量和计价快照引用。
- Test：测试命令、退出码、通过/失败/跳过数量、stdout/stderr 或报告引用。
- Reflection：观察到的错误、简要修复假设、下一步动作及重试轮数。

记录可观察的动作、输入输出摘要和证据，不要求模型输出内部思维链。日志中的凭据需要脱敏；大段输出放在受控 artifact 中，Trace 保存引用。为避免双重统计，模型/工具调用结束事件与开始事件使用相同 call_id。

## 23.2 必须支持的分析

- 按 task_id 重建从检索、计划、修改、测试到恢复的完整时间线。
- 从失败 eval_run 直接定位出错事件、相关上下文、Diff 和测试证据。
- 对同一用例的不同策略展示排名、计划、工具调用、重试和最终结果差异。
- 比较首次测试与最终测试，统计“首次失败后恢复成功”的数量。
- 输出主要失败分布及代表性案例，解释优化针对了哪类问题，以及带来多少额外成本。

P0 交付为事件查询接口与 Markdown/JSON 分析报告；P1 再实现交互式 Agent Trace Viewer。Trace 支持观察过程回放，不意味着无副作用地重新执行历史工具调用。

---

# 24. 最终验收标准（v1.1）

月底交付必须同时满足工程闭环与评测闭环。

## 24.1 工程闭环

- 保留并完成全部 P0 功能：Repository 导入与重索引、Python Parsing、Vector/Keyword/Hybrid Retrieval、结构化计划、人工确认、Workspace Copy 修改、Docker pytest、有限 Reflection、Diff 与报告。
- 三个场景均有可运行 Demo；Bug Fix 和 Feature 使用预定义验收与回归测试，Q&A 输出可核查引用。
- 失败和重试上限路径能够正常终止并生成报告；拒绝审批后不能修改代码。
- Docker Compose、迁移、配置样例和 README 足以重现核心流程。
- P1/P2 不作为 P0 的完成条件；为 human_approval 所必需的最小状态保存须随 P0 完成，通用恢复功能仍属 P1。

## 24.2 评测闭环

- 第一周至少 10 个检索用例和 Recall@1/3/5 报告全部交付。
- 月底端到端数据集最低 15 个用例，question / bug_fix / feature 各至少 5 个；每类至少 1 个 held_out 用例。检索级指标与端到端指标分开统计，可复用问题但须明确不同评测范围。
- B0、B1、B2 在同一版本端到端用例集上完成运行，记录模型、预算、环境与策略差异；检索实验使用固定检索用例集。
- 每次运行写入 eval_runs，端到端运行可关联 task_events；纯检索运行保存排名与匹配证据。
- 报告包含 Task Success Rate、Test Pass Rate、Recall@K、工具调用、重试、延迟、Token、成本及缺失覆盖率。
- 提供主要失败分布，至少深入分析 3 个实际失败案例；若真实失败不足 3 个，分析全部，并另用明确标记的故障注入验证分类和终止路径，注入案例不混入自然成功率。
- 交付至少一份 Baseline → Hybrid → Reflection 对比报告，结论有逐例结果和 Trace 支持。未发现提升也须如实交付分析，不以虚构增益验收。

## 24.3 最终展示材料

```text
README：定位、架构、运行方法、真实指标、限制
Demo：三个能力评测场景
Eval Dataset：版本、commit、标注、拆分、验收规则
Eval Report：Baseline 对照、样本量、配置、成本与延迟
Failure Analysis：类别分布、代表性 Trace、改进依据
```

最终项目应能够回答：

> Agent 在什么任务上成功或失败？问题发生在哪个环节？改进策略改变了什么？收益是否值得增加的成本？这些结论能否在固定配置下复查？