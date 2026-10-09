# 离线实验对照

当前批次使用 `evals/experiments/comparison-v1.json` 显式关联六条主运行，以及一条准备失败和一条停留在 preparing 的额外记录。所有路径相对于清单文件解析，因此换电脑时可保持目录结构复制；无需同步数据库即可读取历史材料。

运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.compare_experiments --manifest evals/experiments/comparison-v1.json
```

命令只读本地 JSON，在 `reports/comparisons/comparison_<随机ID>/` 导出 comparison.json 和 comparison.md，不调用模型、数据库、HTTP 或 Docker，也不读取当前工作副本。可以重复导出，不覆盖上一次结果。

## 数据流与分层

- `scripts/compare_experiments.py`：解析清单、读取明确指定的文件、记录文件 SHA256、保存报告。不会自动查找“最新”或“最佳”运行。
- `services/experiment_comparison_service.py`：核对用例与任务配置、TestRun 所属任务、终态证据及 diff 文件范围；重新关联导出中的原始工具/模型事件，生成逐例对比与 Markdown。它不导入 scripts，不访问外部服务，后续前端可复用输出或业务函数。
- 清单的 primary 是每个用例/策略明确选定的一条运行；additional 保留额外尝试。重复 experiment_id、复用 task_id、同一配对出现多个 primary 会报错，不静默覆盖。输入缺失或关联损坏时不跳过该行继续宣称完整对照。

JSON 保留查询、有序命中、上下文处理及其关联的模型调用；Markdown 提供概览、原始测试输出、逐查询结果和源文件链接。每条输入的 SHA256 表示本次读取内容，不是数字签名或不可篡改保证。Markdown 的本地链接依赖本机文件位置；换电脑后重新导出即可更新路径。

## 解释限制

- 主运行 completed 和测试进程退出 0 是保存的执行事实，不等同于自动验证所有需求。本轮六条都有人类审核，未触发 Reflection。
- 报告不计算通用成功率，不把准备失败或未完成记录藏起来。preparing 是记录中的状态，不代表该历史进程现在还活着；没有证据时不推断失败原因。
- 旧 task-list / Vector 的检索证据为 not_recorded，不是零次搜索。其余五份证据是规划阶段快照，序号小于最终完成序号是正常的。
- 原始 trace_status 和告警来自导出快照；工具/模型关联从已保存的相关事件重建。相关事件序号的自然间隔不作为新的缺口告警，其他关联问题单列 association_warnings。
- 对照检查已记录的用例声明、测试原始 hash、调用/重试预算、镜像标签、超时与观测到的模型标识。没有完整保存镜像 digest、生成参数和独立索引版本，不能据此认证所有实验条件完全相同。
- Prompt hash 保留在模型调用条目中，固定策略提示可能本来就不同；不把不同查询的排名直接当作同查询算法收益。
- pytest stdout 原样保存。结构化测试计数、token、成本缺失时为 null，不解析临时文本格式填成可靠指标，也不把人工等待时间称为模型耗时。

本批观察：deduplicate 的相同查询 `deduplicate.py` 在 Hybrid 中将实现从向量第 7、关键词第 1 融合到第 3；两组最终固定测试均通过。这支持该次查询的排序贡献，不能推广为通用任务成功率提升。

## 验证

`tests/test_experiment_comparison.py` 使用清单中的历史 artifacts 做离线集成及篡改回归，并禁止 socket 连接。运行需要这些已保存的文件，不需要数据库、镜像或 API Key；提交/搬迁项目时保留清单引用的报告文件。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_experiment_comparison.py
```

当前 13 项通过；没有重新运行模型、容器测试或全项目回归。

## 前端查看

已有离线工作台新增 `#/comparisons`，通过 `frontend/comparison-source.json` 明确选择上述汇总报告；不会自动找最新报告或挑选效果最好的一次。`npm run snapshots` 先生成历史详情，再从该报告投影对比页数据到 `public/data/comparison.json`，不把原始源码、日志及本机绝对路径整体转发到对比页。

在 `frontend` 目录执行 `npm run dev`，点击“策略对比”。可查看三组逐例结果、展开查询命中和工具上下文，并进入对应运行详情。另列失败及未完成准备记录，未记录指标不填零。详情的终态报告和 TestRun 不匹配时禁用跳转；只有证据导出选择不同时保留链接并明确提示，清单选定的数据不会被详情的最新导出覆盖。

换电脑保留 `comparison-source.json` 指向的报告及原实验 artifacts；没有文件时构建报错，不静默换一组对照。这一页面是历史展示，不是实时执行入口，不依赖数据库、Docker 或 API Key。
