# RepoPilot 前端

Vue 3 + TypeScript + Vite + Vue Router + Element Plus。当前交付实验总览、历史来源抽屉与运行详情；策略对比将在后续模块实现。

## 本地运行

在 `frontend` 目录执行（Windows PowerShell 可使用 `npm.cmd`）：

```powershell
npm.cmd install
npm.cmd run dev
```

打开终端打印的本地地址。无需 FastAPI、数据库、Embedding、模型或 Docker。服务仅监听本机；不会执行历史实验。

## 检查和构建

```powershell
npm.cmd run test:snapshots
npm.cmd run build
npm.cmd run preview
```

`build` 先整理快照，再执行 `vue-tsc` 和 Vite 构建。`dist` 可以独立静态展示；使用 hash 路由，无需服务器配置路由回退。Node 需要满足 Vite 7 的版本要求（本机 Node 22.17）。

## 数据流和事实边界

`reports/experiments` 中白名单 JSON → `scripts/build-snapshots.mjs` → `public/data/history.json` → `src/data/history.ts` → 总览／来源抽屉。

运行详情另由 `scripts/run-detail.mjs` 整理为 `public/data/runs/<experiment_id>.json`，通过 `src/data/run-detail.ts` 按需读取。总览不一次加载全部日志与 Diff。

只输出总览所需字段；不复制整个报告目录，不读取 `.env`、API Key 或本机工作区内容。`vite.config.ts` 将环境文件目录限定到前端的 `client-env`，不加载项目根目录服务端配置。

原始报告保持不变。生成 JSON 是本地派生文件，不提交 Git。启动和构建自动重新整理；服务运行期间若报告变化，执行 `npm.cmd run snapshots` 后刷新页面。浏览器不会轮询后端。

- 用准备记录中的实验 UUID 作为标识，不用父目录名称代替。
- 汇总前校验实验、任务、仓库与 TestRun 关联。错配文件保留在来源清单，排除其汇总并标记问题。
- 任务状态优先取历史终态报告，其次取最新计划快照。候选已保存不推断已经应用，不推断任务当前正在执行。
- 无终态报告时也展示已有测试结果，按 TestRun 完成时间选择；测试通过不会自动变成任务成功。
- 最新检索证据按 `exported_at` 选择，重复导出全部保留来源。`recorded` 只表示规划检索记录可关联，不代表全流程事件完整。
- pytest 汇总来自原始 stdout 的整行，不能当作 Agent 总耗时；没有计数字段时不补零。
- 同例重复运行会全部展示。没有 task_id 的准备记录独立列出，不计入任务运行。
- 当前数据集的全流程事件没有完整导出，因此总览显式提示该缺口。

`HistoryReader` 是页面的数据入口；后续接入 API 时可以提供另一个读取实现。在线实验汇总需要后端提供实验与任务关联契约；普通任务 API 不自动继承本地实验脚本的保护约束。本阶段没有副作用操作，也没有后端连接配置。

## 运行详情与 logo

从总览的“运行详情”进入 `#/runs/<experiment_id>`。顶部展示目标与独立的任务、测试、证据状态；配置与完整 ID 可展开。左侧默认展示关键记录，可切换全部事件；右侧查看选中记录。所选记录保存在 URL 的 `entry` 参数中，支持刷新与分享。

- 原始事件保留 ID、sequence 与事件时间；计划、审批、候选和报告明确标为文件快照，不伪造成原始事件。
- 应用结果缺时间时单列，不根据文件名或候选创建时间推断顺序。报告显示的是任务完成时间，明确区分报告导出时间。
- 终态报告可切换历史 Diff、关联 TestRun 和最终计划；候选正文与已应用结果独立展示，不读取当前工作区重建历史。
- 事件详情展示查询、排名、预算处理及导出文件中的后续模型关联。准备上下文、调用尝试、成功响应与语义上使用证据不是同一概念。
- 缺少新版证据的旧运行仍可看已有事件，不补造检索。无终态报告的运行展示候选，不产生测试或完成事件。
- 业务字段采用白名单投影，正文对常见凭据格式做展示脱敏；文本用 Vue 插值渲染，不执行报告中的 HTML。

侧栏使用项目根目录的 `assets/repopilot-logo.png`。保留原图，通过 CSS 显示反色与留白裁切以适配浅色背景；不生成新图片，也不修改用户资产。Vite 仅额外允许读取该 `assets` 目录，不把整个项目作为静态目录。

## 本轮验证

2026-10-09：历史数据检查核对到六条任务运行与两条未创建任务的准备记录。五条任务保存了终态报告，statistics / Hybrid 仅保存候选。旧 task-list / Vector 为 `not_recorded`，其余规划检索证据为 `recorded`；均未保存完整全流程事件导出。

验证范围为前端数据关联检查、类型检查、生产构建、浏览器总览／筛选／来源抽屉与 390px 窄屏排版。没有执行模型、Embedding、Docker、后端回归或实验。

第二轮新增运行详情数据检查，覆盖审批与候选不生成虚构事件、缺时间的应用记录、旧事件兼容、错配与重复序号拒绝、历史 Diff 归属、凭据展示脱敏及空输出与未记录的区分。浏览器验收核对真实 Hybrid 查询／上下文／历史 Diff／指定 TestRun、旧 Vector 证据缺失与未完成 statistics / Hybrid 运行。
