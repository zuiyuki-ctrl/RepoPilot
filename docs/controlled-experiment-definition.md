# 受控实验定义与验收

本说明对应第 4 天模块。旧准备记录仍可读取，但不能补写规则后当作预声明实验。

新实验在准备前确定一个定义 JSON，并传给 `scripts.start_experiment --definition <定义文件>`。修复类用例还需要 `--allow-baseline-tests`，它允许准备阶段执行一次 Docker 测试；原 `--allow-embedding` 仍独立控制向量化授权。这里不要求现在重跑旧六组实验。

下面是**结构示例，不是真实用例或实验结果**。测试的 `classname` 和 `name` 需按目标测试报告填写；参数化用例保留完整后缀。每个必需测试必须属于 case 中的受保护测试文件。

```json
{
  "schema_version": 1,
  "suite_id": "demo-controlled",
  "suite_version": "v2",
  "config_version": "v1",
  "repeat_index": 1,
  "changed_parameter": "retrieval_policy",
  "baseline": "vector",
  "candidate": "hybrid",
  "max_tool_calls": 4,
  "max_retries": 1,
  "test_timeout_seconds": 120,
  "intervention_policy": "approve_generated_candidate_only",
  "acceptance": {
    "version": "v1",
    "required_tests": [
      {"classname": "tests.test_example", "name": "test_example"}
    ],
    "baseline_failure_tests": [
      {"classname": "tests.test_example", "name": "test_example"}
    ],
    "manual_criteria": []
  }
}
```

同一对 Vector/Hybrid 使用相同定义、case 和 repeat_index；不同重复次数在运行前声明新的 repeat_index。不要修改完成后的 preparation.json 来改变分组或验收规则。当前实现只支持上述固定策略变量与干预约定；它声明人工只批准生成候选，不等于系统已证明没有任何外部人工修改。

bug_fix 准备时会验证指定测试确实失败；收集错误、超时或测试已通过会停止准备并保留 baseline_tests 阶段证据。feature 不要求失败基线。实际执行仍走已有规划、人工批准、生成、应用、测试及完成流程。

如果规则包含 manual_criteria，对比清单的相应 runs 项可新增 `acceptance_review` 文件路径。该 JSON 由实际复核人记录，字段为：

- `task_id`、`test_run_id`：最终报告引用的任务和测试运行。
- `contract_sha256`：准备记录 run_config.experiment_contract_sha256。
- `test_report_sha256`：最终 TestRun.test_report.sha256。
- `reviewer`、`recorded_at`：复核人和带时区时间，时间不得早于任务终止。
- `decision`：approved 或 rejected。
- `checked_criteria`：完整、无重复地列出声明的 manual_criteria。
- `evidence`：实际复核依据，不填写无证据的泛泛通过说明。

这份记录是人工提供的验收证据，不是原计划审批，不是密码学签名。缺失保持 unknown；绑定错误拒绝导入。对于仅自动测试的约定，passed 只表示声明的测试已满足。

对比报告新增 `comparability`：

| 状态 | 含义 |
|---|---|
| different | 已知输入条件出现差异，列出具体字段和值 |
| insufficient_evidence | 配对或定义、模型内部版本等必要条件缺失 |
| recorded_conditions_match | 已核对的条件相同，不是统计显著性或自动发布许可 |

模型生成的查询、上下文和答案是输出，不因为它们不同就认定实验输入违规。当前供应商内部版本没有可靠记录，保持未知，不填假值让对比变绿。前端展示仍待第 6 天，本模块结果可在对比 JSON/Markdown 查看。

第 5 天已在上述输出基础上增加配对变化、失败事实及可选人工原因复核，使用方法见 [配对变化与失败证据分析](paired-failure-analysis.md)。

第 6 天支持在新定义中提前冻结可选 decision_policy，旧定义序列化及约定 hash 保持兼容。门槛、探索性分析和独立人工采用记录见 [批次决策说明](experiment-decision.md)。
