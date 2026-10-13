# 批次门槛、资源差额与人工采用记录

对应核心七天计划第 6 天。继续使用原来的离线对比入口，不增加数据库表，不连接模型、Docker 或在线任务接口。

## 数据流

历史文件 → 原有验收与可比性 → 配对分类 → 资源差额与门槛 → comparison JSON/Markdown → 前端白名单投影 → 原策略对比/运行详情页面。浏览器只显示后端已生成结论，不重算评分。

`decision.verdict` 仅为 `meets_batch_rules`、`does_not_meet_batch_rules`、`insufficient_evidence`。它们表示符合本批条件、不符合、证据不足，不是统计显著性、泛化能力或自动发布许可。

## 两种门槛来源

### 新运行：提前冻结

在第 4 天使用的 definition JSON 中新增 `decision_policy`。它随原实验约定一起计算 SHA256，准备/规划/执行/导出继续核对该约定。不修改已完成 preparation 追认门槛。

以下是 **synthetic 结构示例，不是推荐阈值，也不是已进行的真实实验**。请根据研究问题确定自己的任务批次和预算，再发起新实验：

```json
{
  "version": "synthetic-v1",
  "declared_at": "2026-10-13T09:00:00+09:00",
  "expected_pairs": [{"case_id": "synthetic", "case_version": "v1", "repeat_index": 1}],
  "min_pairs": 1,
  "min_classification_coverage": 1.0,
  "max_regressions": 0,
  "min_quality_delta_pp": 0.0,
  "min_resource_coverage": 1.0,
  "max_token_increase_percent": 20.0,
  "max_wall_time_increase_percent": 30.0,
  "max_cost_increase_percent": null,
  "cost_currency": null
}
```

- expected_pairs 必须包含全部预先声明的 case/version/repeat；对比不能通过只选择成功案例改变批次。不同配对的定义应携带同一份门槛。
- 当前运行必须属于声明范围，declared_at 不得晚于准备；混用不同门槛或部分缺失，不认证为预注册。
- min_pairs、分类/资源覆盖率、质量百分点下限、最大退化数均需明确填写。资源增幅上限可为 null，表示未对该项设门槛，不等于已经验证其可接受。
- 配置成本上限还须声明币种；真实单价继续通过 manifest 原有 pricing 提供。不联网抓价格，不内置实际价格。
- 新可选字段在为 null 时不参与旧定义的序列化，因此不会破坏第 4 天已有约定 hash。

### 历史结果：探索性分析

可在 comparison manifest 顶层临时提供同结构 `decision_policy`。**无论 declared_at 写什么时间，manifest 临时门槛都标为 exploratory**，不能包装为运行前门槛。即使符合规则，也只表示事后探索性分析满足这些条件。未提供任何门槛时返回 insufficient_evidence，不套用默认数值。

```powershell
python -m scripts.compare_experiments --manifest <明确选择的清单.json>
```

## 口径与缺失处理

- 每对资源差额：Candidate − Baseline；相对变化为差额 / Baseline × 100。基线为 0 时绝对差额仍可显示，相对变化为 null；相对增幅门槛因此证据不足。
- Token 只使用完整运行范围、usage 完备的总量，不把已知小计当总量。墙钟需要启动证据，包含人工等待，不代表纯模型速度。索引准备开销不混入任务查询开销。
- 成本是估算。对内与跨配对汇总必须使用相同计价快照和币种；缺单价、缺用量、币种不同不比较。不会把 USD 与 CNY 相加。
- 资源汇总取**相同完整配对**的两组均值，并显示有效配对数、占所选批次的覆盖率，不拿两组不同的样本集合做差。资源门槛检查所配置的 min_resource_coverage；不足为 unknown。
- 质量百分点变化 =（改善数 − 退化数）/ 已分类且有双方启动证据的配对数 × 100。始终标注范围和覆盖率，不称为未知样本被排除后的全批成功率。
- 声明批次缺失、条件不足/漂移、验收未决、启动证据不足时，整体保持 insufficient_evidence。即使用户设置较低分类覆盖率，也不把条件缺口变成全面符合。每项明确的未满足仍保留，供复核。
- 单项未知优先于整体“符合/不符合”。证据完整后，只要某项门槛未满足就是 does_not_meet_batch_rules；全部满足才是 meets_batch_rules。

## 独立人工采用记录

在不提供复核文件时先导出报告，实际复核人阅读 `decision` 后创建 JSON：

- `decision_sha256`：复制这份 decision 的绑定 hash，关联门槛、配对、指标及原始 artifact 内容指纹。不依赖导出时间和本机文件路径，可跨电脑搬移相同证据。
- `reviewer`、`recorded_at`：姓名/标识和带时区时间，时间不得早于批次中任何任务终态。
- `action`：adopt_candidate / keep_baseline / continue_experiment。
- `rationale`：这次人工决定的具体依据及适用范围。

在 manifest 顶层添加 `"decision_review": "reviews/<文件>.json"`，再导出。关联错误、证据变化或时间早于终态会拒绝导入。批次中尚有缺终态的运行不能填写该终态复核。这个记录与 acceptance_review、failure_review、计划审批相互独立；允许人表达自己的决定，但不会覆盖门槛结论，也不触发代码部署或策略切换。助手不替用户创建真实采用决定。

## 页面与现有演示数据

- 策略对比页：批次结论、来源（冻结/探索性/未配置）、分类数量、门槛逐项结果、资源差额、缺失原因、下一步验证方向、人工记录。
- 每对运行：重复序号、条件差异/缺失、独立验收、完整值与已知小计、失败事实与证据引用。
- 运行详情：仅在选定对比报告与详情终态/TestRun 匹配时展示分析；证据导出不同会明确提示，不混用。
- 总览：保留原来的运行列表，链接到选定批次决策；任务完成不等同于新版验收成功。

前端本轮选择的是旧六条真实运行的新离线派生报告：三对未决、门槛未配置、整体证据不足，资源未知保持未知。没有设置示例真实价格或伪造提升数字；没有重跑实验。可在 frontend 执行 `npm.cmd run dev` 查看，数据变化后运行 `npm.cmd run snapshots`。

本周下一步是第 7 天集中交付：核对数据库迁移，在用户具备环境并明确启用模型后，执行一对代表性新运行验证新采集链路。不是默认重跑六条，更不把单对结果当成通用策略优劣证明。
