# 固定实验用例

三个 JSON 均使用已经核对的完整基线提交。

| 用例 | 本机样例目录 | 初始验收结果 |
| --- | --- | --- |
| task-list | `D:\RepoPilot-demo-tasklist` | 2 失败、6 通过 |
| deduplicate | `D:\RepoPilot-demo-deduplicate` | 2 失败、4 通过 |
| statistics | `D:\RepoPilot-demo-statistics` | 7 失败、5 通过 |

初始失败是后续 Agent 修复或实现功能的验收依据，不应降低测试要求使基线通过。
task-list 当前基线已移除源码中的解题提示，需求只描述异常现象；配置中的提交指向此版本。

从 RepoPilot 根目录执行：

```powershell
python -m scripts.prepare_experiment `
  --case evals/experiments/cases/task-list-v1.json `
  --source-path D:\RepoPilot-demo-tasklist
```

本机路径通过命令行传入，不保存在用例定义中。`bug_fix`、`feature` 是实验分类，
后续创建业务任务时仍应使用 `TaskCreate.task_type="plan"`。

成功摘要只表示准备检查通过，尚未创建实验运行，也不保证 Docker 镜像已经可用。
注册仓库后仍需再次核对提交，防止检查后源仓库发生变化。
文件范围和测试 hash 目前只是配置及准备依据，后续执行入口必须实际强制执行测试保护。
