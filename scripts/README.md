# 脚本入口与用途

从项目根目录以 `python -m scripts.<模块名>` 运行。这里既有平台入口，也有历史实验工具和验收夹具；并不是所有脚本都能无副作用地直接运行。不要批量执行此目录来“检查是否可用”。参数、权限与环境要求以各入口和对应文档为准。

## 平台运行与诊断

| 文件 | 用途与边界 |
| --- | --- |
| `platform_worker.py` | 处理已排队的准备、目录校验与执行工作；模型调用需显式授权，不是只读诊断 |
| `check_db.py` | 连接本机配置的数据库执行 SELECT 1；不写数据，不验证表结构或迁移版本 |
| `prepare_platform_run.py` | 可信 Process 开发入口，冻结并入队；会创建平台记录，不是普通 Agent 上报接口 |
| `enqueue_native_run.py` | 可信 Native 开发入口，创建并入队；请求需由可信准备器产生 |

通常优先使用前端的 Agent / Benchmark / 实验入口；保留开发 CLI 供诊断及已记录流程复现。详见 [worker 与恢复](../docs/v2-day2-native-worker.md)、[Process 评测](../docs/v2-day3-process-evaluation.md)。

## 历史 Native 实验与报告

| 文件 | 用途 |
| --- | --- |
| `prepare_experiment.py` | 检查固定用例、源仓库提交与受保护文件 |
| `start_experiment.py` | 准备实验；依授权可能涉及数据库、基线测试及 Embedding |
| `plan_experiment.py` | 分阶段规划，涉及模型调用 |
| `review_experiment.py` | 保存显式计划审批决定 |
| `execute_experiment.py` | 分阶段生成候选、检查和应用；依阶段可能调用模型或修改工作副本 |
| `test_and_complete_task.py` | 调用测试/完成流程并导出；不是 pytest 测试模块，也不是可删的测试残留 |
| `export_task_report.py` | 读取历史任务报告，导出 JSON / Markdown |
| `export_retrieval_evidence.py` | 读取并导出已保存的检索证据 |
| `compare_experiments.py` | 按显式清单离线汇总历史实验，并写出新报告 |
| `eval_retrieval.py` | 检索评测，可能访问数据库及 Embedding 服务，不是纯离线工具 |
| `render_retrieval_report.py` | 检索评测报告的渲染及相关入口 |

这些入口仍被回归测试或既有实验说明使用，不能因已有实时页面就直接删除。参见[分阶段实验说明](../docs/experiment-first-run.md)与[实验比较](../docs/experiment-comparison.md)。

## 网关验收入口与配套夹具

入口：`probe_gateway_network.py`、`probe_gateway_egress.py`、`probe_gateway_runtime.py`。

它们创建明确标记的一次性 Docker 资源，检查网络、代理、账本和清理。运行前需准备对应镜像并阅读参数；网络探针含固定公网连通性对照，不能把所有 probe 都描述成完全断网。runtime 探针使用临时数据库，不是已有业务数据库迁移工具。

配套文件：`gateway_probe_runtime.py`、`gateway_egress_fixture.py`、`gateway_smoke_agent.py`、`gateway_fault_checks.py`。这些文件被入口导入或装入验收容器，并非独立生产入口；删除会破坏既有验收流程。

参见[网关运行说明](../docs/model-gateway-mock-runtime.md)、[真实模式部署](../docs/model-gateway-live-runtime.md)和[验收范围记录](../docs/v2-model-gateway-plan.md)。不使用验收通过代替真实模型效果结论。

## 收尾清理记录

2026-10-22 删除两份未被业务代码或测试依赖的手工学习脚本：`check_repository.py`（直接插入固定路径学习记录）、`try_readonly_agent.py`（固定仓库 UUID 和问题的模型试跑）。需要追溯时从 Git 历史恢复；不在本轮执行它们，也不删除它们过去可能创建的数据。

`tests/` 的回归代码保留，尤其 `test_platform_day*.py` 是功能测试而非开发日志，且网关测试复用其中夹具。缓存可重建，不代表测试源码可删除。
