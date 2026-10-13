# 配对变化与失败证据分析

本模块对应核心七天计划第 5 天。数据流沿用：历史 preparation/report/evidence 文件 → 第 4 天验收与可比性 → 配对分类、逐运行失败分析 → 对比 JSON/Markdown。不会访问当前工作区、调用模型、连接数据库或重新运行测试。

## 导出与阅读

在项目根目录使用现有入口；每次生成新的导出目录，不覆盖历史运行：

```powershell
python -m scripts.compare_experiments --manifest evals/experiments/comparison-v1.json
```

- `pairs[].analysis`：双方独立验收结果、测试进程结果、配对分类及原因。
- `paired_analysis_summary`：主配对总数、六类数量、已判定数量与覆盖率。额外准备失败/中断保留在 `additional_attempts`，不当作配对成功率的分母或分子。
- `pairs[].runs.<strategy>.failure_analysis`：失败事实、阶段、证据、假设、复核状态、缺失项；额外运行也具有该字段。
- `artifacts`：原始文件路径、URI、文件 SHA256。分析里的证据 `source` 指向这些文件中的字段，事件序号或 TestRun ID 用于定位；未保存的 Diff 不补造。

配对只使用原有 `acceptance`，不从 completed 或 stdout 另算成功：

| 分类 | 条件 |
|---|---|
| stayed_success | 可比且双方 passed |
| improved | 可比且 baseline not_passed、candidate passed |
| regressed | 可比且 baseline passed、candidate not_passed |
| both_not_success | 可比且双方 not_passed |
| undecided | 缺配对、条件证据不足或验收 unknown |
| non_comparable | 已知非实验变量差异（包括已观察到的模型差异） |

已知条件差异优先阻止严格分类；未知条件不视为相同。`both_test_processes_passed` 只是独立展示的进程事实，不能用来覆盖分类。配对改善不证明因果关系、统计显著或普遍收益。

**旧六条真实主运行**仍按原有证据展示三对测试进程均通过；没有事先声明的新验收定义，且运行条件不全，因此为 undecided，不补造改善或新成功率。退化、失败和完整可比情形在 `tests/test_experiment_analysis.py` 等测试中的 synthetic fixture 验证；模拟数据只在内存或临时目录使用，不写入真实清单或统计。

## 失败事实与根因的边界

- `termination_stage` 只表示有结构化终止依据的阶段。通用 TASK_FAILED 没有阶段证据时为 unknown；Reflection 停止和重试预算耗尽可定位 recovery。
- `observed_stages` 表示出现问题的阶段。终态报告的请求观测优先于检索导出的局部观测；调用业务校验失败可定位到 planning/edit 等已记录 phase，但不据此证明根因。
- JUnit 重新校验后才列具体 classname/name 与 failure/error/skipped；不从 stdout 解析计数。超时是事实，不自动变成 RETRIEVAL_FAILURE；断言 failure 或 setup/teardown error 也不能直接证明测试基础设施错误。
- 新任务报告保留终止事件的 `reason_code=retry_budget_exhausted`，可将终止类别标为 BUDGET_EXCEEDED；旧报告没有代码时不通过错误文字推断。预算耗尽仍不解释此前为什么失败。
- Reflection diagnosis 保留为 `source=model_reflection` 的未复核假设，绝不自动升级为已证明的根因。
- 未经复核的根因保持 UNKNOWN。Top K 和候选计数不能证明相关目标在完整候选中被排序排除。失败报告缺 Diff 时保持缺失。

## 可选人工失败复核

人工失败分析复核、`acceptance_review` 和计划审批是三件不同的事。失败复核只注释原因，不改变任务状态、验收结果、可比性或配对统计；没有自动批准候选或发布。

1. 先不提供 `failure_review`，导出报告并查看该运行的 `failure_analysis`。
2. 实际复核人读取证据后，创建 JSON：
   - `task_id`：该运行任务 UUID。
   - `analysis_sha256`：原样复制该分析的 hash，绑定实验、任务、终态、约定、测试证据、Diff 与可用检索证据。它不是原始文件 hash，也不是密码学签名。
   - `reviewer`、`recorded_at`：复核人和带时区时间，时间不得早于任务终止。
   - `primary_category`：沿用 PRD 失败类别；证据不够可明确选择 UNKNOWN。
   - `secondary_categories`：可选次要类别，默认空，不重复主类别。
   - `hypothesis`、`rationale`：人工提出的解释及判断依据，不是让模型自评。
   - `evidence_ids`：至少引用一个本次分析实际列出的 `evidence[].id`，如 terminal_event、final_test、test_report、final_diff 或 retrieval:序号。不能引用并不存在的证据。
3. 在对比 manifest 的对应 `runs` 项增加 `"failure_review": "reviews/<复核文件>.json"`。相对路径按 manifest 所在目录解析，再运行同一导出命令。

任务、hash、引用或时间不一致会拒绝导入；原始证据改变后应重新复核。失败复核只接受有终态报告且存在失败事实的任务，准备阶段没有任务终态时仍保留自动事实、不伪造人工绑定。保存的是人工陈述，不证明其内容绝对正确；UNKNOWN 复核后根因仍未知。

前端、资源差额展示及采用门槛仍在第 6 天完成。本模块不产生“推荐上线”或“应该增加 Reranker”的结论。
