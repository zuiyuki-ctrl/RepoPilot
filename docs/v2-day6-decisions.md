# Day 6 第三模块：冻结质量门槛与独立人工决定

2026-10-16。实现本批自动测试质量门槛与人工记录；不等于完整发布认证或 Day 6 全部完成。

## 规则在何时保存

新实验可选填 decision_policy，随 draft 进入启动预览与冻结 manifest。字段为版本 1、min_pairs、min_cases、max_regressions、min_pass_delta_pp。最少对子或 Case 超过该 Suite 的计划规模时拒绝预览。没有更新历史门槛的接口。

未填写时序列化仍省略该字段，保持旧请求的 hash 兼容。旧实验显示 no_preregistered_policy / not_assessed；不能看到好结果后补写规则，再标记为预先声明。

必须全部计划对子可比且无完整性问题，才评估四项门槛；否则 insufficient_evidence。达到规则显示 meets_quality_policy，未达到为 does_not_meet_quality_policy。相同 Case 的重复运行增加对子数，不增加不同 Case 数。状态明确限定 declared_automated_test_quality_only，成本、Token、延迟暂未纳入门槛，不自动推荐发布。

例如：预先要求 3 个不同 Case、0 次退化、通过率差至少 0 个百分点。一例重复 3 次即使全部通过，也不满足 3 个不同 Case；两例未完成则显示证据不足，而不是忽略它们后宣称通过。

## 人工决定与系统成绩分开

新增 experiment_reviews 表，迁移 d716a06b0001。记录请求键、实验 ID、比较 hash、当时完整比较投影快照、操作者、决定、理由和服务器时间。

- GET/POST `/api/v2/experiments/{id}/reviews`：读取历史或追加决定。列表支持 limit/offset，页面显示最近 20 条。
- 决定为 adopt_candidate / keep_baseline / continue_experiment；不改变 Run、Evaluation、门槛或比较结论。操作者可以与系统判定不同，必须留下理由。
- 页面点击核对时固定比较 hash；提交重新比较，过期返回 409。相同请求键和相同内容返回原记录，同键改内容拒绝。历史提交重试不会因后续证据变化而再次追加。
- 人工操作采用 repeatable-read 事务和提交锁；遇数据库并发快照冲突可能返回存储错误，可保留同一请求键重试。尚未进行多客户端并发压力测试。
- 每条记录保留当时快照；前端区分对应当前比较或历史比较。快照是比较投影，不包含完整 Diff 文件与所有 Trace，因此不冒充完整证据包导出。
- 操作者名称为本地可信使用者自填，并非登录身份认证。API 没有修改/删除记录入口，但数据库管理员仍可修改数据库，不声称加密不可篡改审计。

实现入口：schemas/platform_decision.py 定义协议；platform_decision_service.py 纯函数计算系统规则；platform_review_service.py 管理人工记录事务；实验页面负责冻结表单、判定展示与明确确认。

## 验证与迁移

- Day 1—6 集中离线 124 项通过，新增本模块 11 项。事务函数拆分后 11 项再次通过。覆盖门槛各分支、重复与不同 Case、旧数据不补门槛、非法数值/暂不支持资源条件、快照保存、过期拒绝和重复键幂等、HTTP 与迁移 SQL。
- 前端 vue-tsc 与 Vite 构建通过。
- 本机真实执行 Alembic d715a05b0001 → d716a06b0001，新增表，无历史记录回填/覆盖。另一台电脑拉取后需 `python -m alembic upgrade head`。
- 真实 TestClient 读取已有实验比较和 reviews 均 200，旧实验仍显示无预设门槛。真实 PostgreSQL 的最终回滚事务内验证快照写入、同键重复、改内容冲突及过期 hash 拒绝；事务外确认测试记录不存在。不声称测试决定已真实提交到历史。
- 没有运行模型/Embedding、容器、Agent 或新实验。未代表用户填写采纳决定。浏览器交互待用户确认。

## 简短页面验收

刷新 Experiments，打开旧 noop/fix 实验：系统应显示“未评估（没有预先声明门槛）”，下方可核对比较并填写独立人工决定。只有你确实希望保存判断时才点确认保存；无需为了测试重跑模型。新实验表单应有可选冻结质量门槛。

下一步补资源可比性和历史 JSON/Markdown 导出；当前门槛只覆盖质量，不把尚未记录的成本当成零。
