# Day 4 登记示例

在前端 Agents / Benchmarks 页面选择对应 JSON 文件。导入只填写编辑框，检查后点击保存；保存后点击显式校验，独立 worker 执行，刷新查看结果。

- `native.json`：可直接登记。校验仅检查本地实现与配置，不调用模型；不是一次真实任务验收。
- `process-demo.json`：先将全零 image 替换为本机 `docker image inspect repopilot-protocol-demo:v1 --format '{{.Id}}'` 返回的完整镜像 ID。
- `task-list-suite.json`：将全零 repository_id 替换为已注册、干净且处于清单 commit 的 task-list 仓库 ID；将全零 test_image 替换为本地 pytest 镜像完整 ID。页面可展开已注册仓库清单。不使用 RepoPilot 主项目仓库替代 Demo。

占位值不能通过实际环境校验。缺失仓库会在登记时返回 404，缺镜像会使校验失败，不会下载或构建镜像。不要在 argv 或任何 JSON 字段填写密钥；当前 Process profile 无网络，不接入模型凭据。

每个版本标签绑定固定内容。修改镜像、参数、Case 或规则时升级 version，不能覆盖原版本。

校验 worker：在项目根目录执行 `.\.venv\Scripts\python.exe -m scripts.platform_worker`。不要添加 `--allow-model`，本模块不需要付费调用。已验证能力与声明能力分开：协议 fixture 只证明执行协议可用，不证明通用任务成功或完整 L2 轨迹。
