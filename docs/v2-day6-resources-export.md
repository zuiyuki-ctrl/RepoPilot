# Day 6 第四模块：资源可比性与比较报告导出

2026-10-16。本模块不新增数据库迁移，不运行 Agent，不使用当前价格或配置回填历史。

## 资源口径

`platform_resource_service.py` 从已保存 RunEvent 提取 Native 调用关联和 Process model_call 上报，复用已有请求关联与资源小计函数。校验 Run 归属、调用 ID、重复调用和 Token 数值一致性；返回事件引用、调用记录、小计、覆盖率与总量。

- 调用开始/结束配对只能证明这些调用已记录，不能证明 Adapter 上报了全部请求。总 Token 还要求已校验的完整 model_usage 能力、匹配记录数/事件引用和连续 Run 事件。现有 Native/Process 通常为 partial，所以展示已知小计，总量继续为 null。
- 没有事件不等于零用量。外部上报来源保留 agent_reported，不升级为平台独立实测；零条已知用量的小计可为 0，但总量未知。
- 墙钟毫秒取 Run.started_at 到 completed_at，包含人工等待和平台验收。起止缺失或时间倒置时未知；human_wait_ms 尚未单独计量，不填 0。不把嵌套工具 span 累加成墙钟时间。
- 本范围不含准备阶段仓库 Embedding；没有历史价格快照时费用 pricing_missing / null，不用现在的价格估算历史成本。
- 比较时先筛选质量可比对子，再按每个指标取两边均有完整值的同一组对子。分别返回有效/可比/计划对子数、覆盖率、均值与差值；基线为零时相对变化未知，避免无穷大。
- Token 与时间可能具有不同覆盖对子，页面和报告明确给出各自范围。资源指标尚不参与冻结质量门槛；价格登记、资源门槛和 Adapter 完整调用范围证明仍需后续补齐。

例子：两组有两对运行，第二对 Candidate 缺 Token，则 Token 均值只使用第一对双方，而不是 Baseline 算两次、Candidate 算一次。

## 导出

`GET /api/v2/experiments/{id}/export?format=json|markdown` 使用同一个 PostgreSQL repeatable-read 只读快照，导出冻结 manifest、比较/资源、全部成员及人工历史。人工记录携带当时保存的 snapshot，并标注是否仍匹配当前比较；不会用当前计算替换旧决定。

JSON 包含 report_sha256：对删除该字段后的完整对象使用项目 canonical digest 计算。Markdown 中相同字段是源报告对象的指纹，不是 Markdown 文件字节 hash。所有数据文本在 Markdown 中缩进展示，防止查询/备注改变文档结构。

每次下载产生独立时点快照，exported_at 因此会变化；JSON 和 Markdown 分别点击时不是承诺相同时间。服务端不创建导出历史记录，请保存下载文件。报告是可携带的比较快照，不是包含原始 Trace、完整 Diff 和源码的全部证据包。比较 hash 本次开始包含资源投影，旧人工记录保持原快照，不改写。

前端 Experiments 新增资源均值表、Run 小计/覆盖详情和两个下载按钮。仅对已知指标显示数值，未知价格/Token 显式展示，不用 0 代替。

## 验证

- Day 1—6 **134 项离线回归通过**，本模块新增 10 项：缺用量、部分/完整范围、缺调用开始、错误用量、跨 Run、重复上报、同对子均值、零基线、历史决定保留、报告 hash/Markdown 和下载接口。禁用 dotenv/外网，DB、模型、Docker 为模拟。
- 前端 vue-tsc 和 Vite 构建通过。
- 真实数据库 TestClient 只读导出现有实验 `12955175-7643-45d4-9f18-8dfdf149e58d`，JSON/Markdown 均 HTTP 200；JSON canonical hash 核验通过。Token 有效对子 0/1，总量未知；墙钟有效对子 1/1，Baseline 30,657ms、Candidate 30,022ms，差 -635ms。仅一次 fixture，不支持性能优越结论。
- 取消实验 `e2cd826e-7574-4573-b7b6-2c609186be77` 时间有效对子为 0，均值 null，没有伪造零。
- 同一份真实 JSON 对象及其 Markdown 渲染已保存到本机忽略目录 `.platform-artifacts/day6-resource-export-fd492c6908564f8cafff3c5d17d7226c/`；report_sha256 为 `afa9e6e10e9cc136fac81d8cd03a7eb10655c1e649b0d1ca866381b2d5e22c6f`。没有改写历史文件或数据库记录，没有执行模型/Embedding/容器。
- 浏览器下载尚待用户确认：打开已有实验，查看资源表，再下载一种报告即可，无需新建实验。

## 接续边界

Day 6 已落地 Trace 浏览、质量比较、冻结质量门槛、人工决定、保守资源比较和比较报告下载。不能据此宣称完整 L2、真实成本统计、资源发布门槛或全部证据归档已实现。进入 Day 7 前按计划检查剩余交付与浏览器闭环，避免把这些局限写成已完成功能。
