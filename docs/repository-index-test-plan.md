# POST /api/v1/repositories/{repository_id}/index 测试方案（FastAPI Docs）

基于 2026-09-16 当前源码；以下预期描述当前实现，不代表尚未实现的产品功能。

测试入口：[FastAPI Docs](http://127.0.0.1:8000/docs)。所有 HTTP 请求均在页面中通过 **Try it out → Execute** 执行。已有测试仓库可直接使用；服务已启动、数据库已迁移时，从第 4 节开始即可。文件修改和数据库检查属于补充操作，Docs 页面本身不能完成。

## 1. 先明确接口行为

- 需要先 `POST /api/v1/repositories` 注册仓库，取得响应的 `id`。创建时要求：绝对路径、Git 工作区根目录、至少一次 commit、干净工作区（包括没有未跟踪文件）。只执行 `git init` 不够。
- 创建接口会 clone 并 detached checkout 到提交快照。`/index` 读取数据库中的 **workspace_path**，不读取 source_path，不执行 pull，也不要求先调用 `/scan`。
- `/index` 无必需请求体，同步执行，提交事务后返回 **200**，不是异步任务或 202。
- 仅处理小写扩展名 `.py`；每个模块顶层函数、异步函数、类各生成一个块；类方法、嵌套函数包含在外层块中，不单独生成。装饰器计入块内容和起始行。
- 合法的空文件、只有常量的文件计入 `file_count`，贡献 0 个块。`chunk_count` 是本次保存的块数，不是新增差额。
- 单文件过大、空字节、解码或语法错误会跳过，其他文件仍可成功；这些文件不计入 `file_count`。
- `.git/.venv/venv/node_modules/__pycache__` 目录、链接和非 `.py` 文件直接过滤，不进入 `skipped_files`。扫描器没有通用 `.gitignore` 过滤逻辑。
- 重复索引先删除各文件旧块再重建；文件 ID 可保持不变，块 ID 不要求不变。已删除或本次被跳过的旧文件及其块会清理。
- 当前不生成 embedding，不更新 `repositories.status` / `indexed_at`；索引成功后仍可为 `registered` / `null`。

源码入口：`backend/app/api/routes/repositories.py`；事务编排：`services/repository_indexing_service.py`；扫描/分块：`services/repository_scanner.py`、`services/repository_chunking_service.py`、`rag/parse.py`；持久化：`services/code_chunk_service.py` 及 `db/repositories/`。

## 2. 环境准备（服务已就绪可跳过）

建议本机运行 API、Docker 只运行 PostgreSQL。当前 compose 的 api 服务未注入 DB_*，Dockerfile 未安装 Git，也未挂载 Windows 源仓库；不能直接用容器 API 访问 `D:/...`。

使用专用测试数据库，在项目 `.env` 中配置 DB_HOST、DB_PORT、DB_NAME、DB_USER、DB_PASSWORD。不要覆盖其他环境已有数据。WORKSPACE_ROOT 必须位于测试源仓库之外。

```powershell
Set-Location D:\RepoPilot
git --version
python --version
# 如果没有可用虚拟环境，先安装 Python 3.11+，再创建：
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
docker compose up -d db
.\.venv\Scripts\python.exe -m alembic upgrade head
$env:WORKSPACE_ROOT = 'D:/RepoPilot/test-data/workspaces'
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

若已有本机 PostgreSQL，可跳过 Docker 命令。环境变量需在启动 API 的终端中设置；API 已启动则重启后生效。

打开 [FastAPI Docs](http://127.0.0.1:8000/docs)，分别展开 `GET /health` 和 `GET /ready`，点击 **Try it out → Execute**。

在 **Server response** 中检查实际 Code 均为 200，Response body 分别为 `{"status":"ok"}`、`{"status":"ready"}`。`/health` 不检查数据库；`/ready` 不检查迁移是否齐全，仍需执行 Alembic。

此前检查环境时，现有 `.venv` 指向的 Python 无法启动，`py -0p` 未发现已安装 Python。如果你已经能打开 Docs 且 ready 返回 200，则以当前运行环境为准，不必为本次测试重新创建环境。

## 3. 生成可重复的 Git 测试仓库

本次已在 `D:\RepoPilot\test-data\index-fixture` 生成并提交测试仓库，可直接使用并跳到第 4 节；下面的生成命令用于另建样例，已有目录不会被覆盖。

```powershell
Set-Location D:\RepoPilot
& .\scripts\new-index-test-repository.ps1
# 默认目录已存在时，使用新目录；脚本不会覆盖旧目录：
# & .\scripts\new-index-test-repository.ps1 -Destination D:\RepoPilot\test-data\index-fixture-02
git -C D:\RepoPilot\test-data\index-fixture status --porcelain
git -C D:\RepoPilot\test-data\index-fixture log -1 --oneline
```

脚本创建文件、初始化 Git 并提交一次；不修改全局 Git 用户配置。status 应无输出。

| 文件 | 预期 |
|---|---|
| app.py | add、ping 两个 function，Greeter 一个 class，共 3 块 |
| pkg/helpers.py | decorated 一个 function，内容从装饰器开始，共 1 块 |
| nested.py | outer 一个 function，包含 inner，共 1 块 |
| constants.py、empty.py | 各计一个文件，0 块 |
| bad/decode.py | source_decode_error（非法字节放在前两行之后） |
| bad/encoding.py | invalid_python_source（未知编码声明） |
| bad/large.py | file_too_large，1,048,577 字节 |
| bad/null.py | contains_null_byte |
| bad/syntax.py | invalid_python_source |
| 排除目录下的 ignored.py、README.md、ignored.txt、.gitattributes | 静默过滤 |

`@decorate` 未定义也不影响索引：只解析 AST，不执行文件。`.gitattributes` 禁用换行转换，保证 clone 后大小和内容字节稳定。故意损坏的 Python 文件是测试数据，不应作为应用代码执行或整体 compileall。

## 4. 在 FastAPI Docs 中逐步测试

### 第一步：注册测试仓库

1. 打开 [FastAPI Docs](http://127.0.0.1:8000/docs)，找到 **repositories** 分组。
2. 展开 **POST /api/v1/repositories**，点击 **Try it out**。
3. 将 Request body 全部替换为以下 JSON，然后点击 **Execute**：

```json
{
  "name": "index-api-fixture",
  "source_path": "D:/RepoPilot/test-data/index-fixture"
}
```

4. 查看 **Server response**：实际 Code 应为 **201**。
5. 从 Response body 复制保存 `id` 和 `workspace_path`；后续 `repository_id` 填这个 `id`，不带引号或大括号。不要填写仓库名称、路径或 Git commit hash。

JSON 路径使用 `/`，避免反斜杠转义问题。此路径必须是 API 所在机器能够访问的路径。每次重新执行注册都会创建新的仓库记录和工作区，测试重复索引时继续使用同一个 id。

如果注册返回 **422 / Cannot inspect the supplied Git working tree**，请在运行 API 的同一个 Windows 用户的终端中执行：

```powershell
git -C D:/RepoPilot/test-data/index-fixture rev-parse --show-toplevel
```

当前预生成仓库的所有者为 `CodexSandboxOffline`。如果 API 由你的用户运行，Git 可能报 `detected dubious ownership`。确认这是本方案生成的测试仓库后，在你的终端中仅信任这个具体目录：

```powershell
git config --global --add safe.directory D:/RepoPilot/test-data/index-fixture
git -C D:/RepoPilot/test-data/index-fixture rev-parse --show-toplevel
```

第二条命令应输出该仓库根路径。然后回到 Docs，重新 Execute 注册请求，预期 201；一般无需重启 API。此配置必须对运行 API 的用户生效，不要在其他用户的终端执行，也不要将 safe.directory 设置为 `*`。若 Git 的原始报错不是 dubious ownership，则根据实际错误排查路径和 `.git`，不要用信任配置掩盖其他问题。

### 第二步：执行索引

1. 展开 **POST /api/v1/repositories/{repository_id}/index**。
2. 点击 **Try it out**，在 `repository_id` 输入框粘贴第一步返回的 `id`。
3. 无需填写请求体，也无需先执行 `/scan`，直接点击 **Execute**。
4. 等待完成，查看 **Server response** 的实际 Code，应为 **200**，并核对 Response body。

注意：接口下方预先展示的 **Responses / Example Value** 是文档示例，不是执行结果；判断测试结果要看点击 Execute 后的 **Server response**。

索引响应应为（UUID 替换为实际值）：

```json
{
  "repository_id": "<实际 UUID>",
  "file_count": 5,
  "chunk_count": 5,
  "skipped_files": [
    {"path": "bad/decode.py", "reason": "source_decode_error"},
    {"path": "bad/encoding.py", "reason": "invalid_python_source"},
    {"path": "bad/large.py", "reason": "file_too_large"},
    {"path": "bad/null.py", "reason": "contains_null_byte"},
    {"path": "bad/syntax.py", "reason": "invalid_python_source"}
  ]
}
```

### 第三步：检查文件列表和仓库状态

1. 展开 **GET /api/v1/repositories/{repository_id}/files**，点击 **Try it out**，填入相同 id，点击 **Execute**。
2. 实际 Code 应为 **200**，Response body 数组应恰好包含 app.py、constants.py、empty.py、nested.py、pkg/helpers.py 共 5 条，language 全部为 python，path 使用 `/`。记录各文件的 `id` 和 `file_hash`，方便重复索引时比较。
3. 展开 **GET /api/v1/repositories/{repository_id}**，同样填入 id 并执行，期望 **200**。当前实现中 `status` 仍可为 `registered`，`indexed_at` 仍为 `null`，不能据此认定索引失败。

file_hash 应是实际文件原始字节的 SHA-256，size 是字节数；如需进一步校验，可在本机对第一步返回的 workspace 内文件计算 hash。块的内容和行号需通过第 5 节 SQL 检查。

### 第四步：重复索引与参数错误

| 场景 | Docs 中的操作 | 实际响应预期 |
|---|---|---|
| 重复索引 | 回到 POST index，保持原 id，再点 Execute | 200，仍为 5 文件 / 5 块 / 5 跳过；再执行 GET files，文件 id 不变 |
| 不存在的仓库 | 将 index 的 repository_id 改为 `00000000-0000-0000-0000-000000000000`（先确认测试库中不存在），点 Execute | 404，`{"detail":"Repository not found"}` |
| 非法 UUID | 将 repository_id 改为 `not-a-uuid`，点 Execute | 请求到达服务端时返回 422，detail 为参数校验错误列表；若页面先拦截，则只验证了前端校验，未验证服务端 422 |

完成负例后，将输入框恢复为第一步的真实 id。到这里已完成主要的 Docs 手工冒烟测试；修改、删除文件等场景按第 6 节继续。

## 5. 数据库验收

当前没有查询代码块的 HTTP 接口，因此这一节不能仅通过 Docs 完成。手工冒烟时可先完成第 4 节；完整验收时，使用数据库客户端执行以下只读 SQL。把所有 `<repository_id>` 替换为创建结果的 id，不要用 workspace 目录名。

```sql
SELECT id, status, indexed_at, source_path, workspace_path, commit_hash
FROM repositories WHERE id = '3032e1ed-3a93-4980-9b86-eadc69f20084'::uuid;

SELECT id, path, language, size, file_hash
FROM repository_files WHERE repository_id = '3032e1ed-3a93-4980-9b86-eadc69f20084'::uuid ORDER BY path;

SELECT file_path, symbol_name, symbol_type, start_line, end_line, content
FROM code_chunks WHERE repository_id = '3032e1ed-3a93-4980-9b86-eadc69f20084'::uuid
ORDER BY file_path, start_line;

SELECT (SELECT count(*) FROM repository_files WHERE repository_id = '3032e1ed-3a93-4980-9b86-eadc69f20084'::uuid) AS files,
       (SELECT count(*) FROM code_chunks WHERE repository_id = '3032e1ed-3a93-4980-9b86-eadc69f20084'::uuid) AS chunks;

-- 期望 0 行：检查块和文件归属、路径一致性。
SELECT c.id FROM code_chunks c
LEFT JOIN repository_files f ON f.id = c.file_id
WHERE c.repository_id = '3032e1ed-3a93-4980-9b86-eadc69f20084'::uuid
  AND (f.id IS NULL OR f.repository_id <> c.repository_id OR f.path <> c.file_path);
```

首次预期 5 条文件、5 条块。行号从 1 开始，结束行包含在块内：

| file_path | symbol_name | symbol_type | start_line | end_line |
|---|---|---|---|---|
| app.py | add | function | 1 | 2 |
| app.py | ping | function | 4 | 5 |
| app.py | Greeter | class | 7 | 9 |
| nested.py | outer | function | 1 | 4 |
| pkg/helpers.py | decorated | function | 1 | 3 |

同时核对 content 确实等于对应行切片，不包含相邻顶层符号。

## 6. 用例清单

每个修改/异常场景建议重新创建仓库记录，得到新的独立 workspace，避免累计修改改变后续预期。涉及磁盘修改时，只操作创建响应返回的测试 workspace；不要操作真实业务仓库。

下表中的“注册”“index”“scan”“查询文件”均在 Docs 中展开对应接口，点击 **Try it out**，填入该场景的 id / JSON，再点击 **Execute**。需要修改 workspace 时，用编辑器或文件管理器打开注册响应中的 `workspace_path` 完成修改，再回到 Docs 执行 index；数据库锁、故障注入、事务回滚验证仍需额外工具配合。

| ID / 优先级 | 操作 | 预期与检查点 |
|---|---|---|
| I01 / P0 | 新仓库直接 index | 200，5 文件 / 5 块 / 5 跳过；数据库与响应一致 |
| I02 / P0 | 不修改内容再次 index | 仍为 5/5，无重复块；文件 ID 稳定，块 ID 可以改变 |
| I03 / P0 | workspace 的 app.py 末尾新增一个顶层函数后 index | 5 文件 / 6 块；app.py hash、size 更新，旧块不残留 |
| I04 / P0 | 基线 workspace 的 app.py 改为合法常量后 index | 5 文件 / 2 块；app.py 文件记录保留，原 3 块删除 |
| I05 / P0 | 基线 workspace 删除 nested.py 后 index | 4 文件 / 4 块，nested.py 文件和 outer 块均消失 |
| I06 / P0 | 基线 workspace 的 app.py 改为语法错误后 index | 4 文件 / 2 块 / 6 跳过；app.py 旧文件记录和 3 块删除；HTTP 仍为 200 |
| I07 / P0 | 随机合法 UUID 调 index，确保库中不存在 | 404，detail=Repository not found，无数据变化 |
| I08 / P0 | 使用 not-a-uuid 作为路径 ID | 422，FastAPI 参数校验错误，未进入 service |
| I09 / P0 | 持有当前仓库数据库行锁时 index | 409，detail=Repository is busy；释放锁后重试成功 |
| I10 / P0 | workspace 不存在或 workspace_path=NULL | 503，detail=Repository indexing unavailable；旧文件、块保持不变，日志记录异常 |
| I11 / P0 | 保存第二个文件时注入异常 | 整个事务回滚，已处理文件的更新、删块、新增块均回滚；其他仓库不变 |
| I12 / P1 | 新建仅 README 的干净已提交 Git 仓库并注册、index | 200，0 文件 / 0 块 / 空跳过列表 |
| I13 / P1 | 已索引 workspace 中移走所有 .py 后 index | 200，0/0，清空该仓库旧文件和块；其他仓库不变 |
| I14 / P1 | 两个不同仓库分别索引，再让 A 变空并索引 | B 的文件及块完整保留，验证删除范围 |
| I15 / P1 | 单个 .py 恰好 1,048,576 字节，全部为一个合法注释 | 文件成功保存、0 块；加 1 字节后跳过 file_too_large，旧记录清理 |
| I16 / P1 | UTF-8 中文、UTF-8 BOM、合法声明的非 UTF-8 源文件 | 正确解码并分块，hash/size 仍基于原始字节 |
| I17 / P1 | workspace 中添加 .PY、非 Python 文件、排除目录中的 .py | 不增加文件/块/跳过数；补充普通目录 .py 则应被扫描 |
| I18 / P1 | workspace 中创建文件链接或目录链接（系统允许时） | 不遍历、不入库、不进入 skipped_files；根 workspace 本身是链接则 503 |
| I19 / P1 | 只修改源仓库并提交，然后对原 id 再 index | 原 workspace 和索引结果不变；重新注册源仓库才得到新快照 |
| I20 / P1 | 先 scan，再 index | scan 为 8 文件、2 跳过（large/null）；index 为 5/5、5 跳过，并清理 scan 留下的无效源码记录 |
| I21 / P1 | workspace 中新增未跟踪、且被 .gitignore 忽略的普通目录 .py | index 仍处理该文件，验证它按磁盘扫描而非 Git tracked 清单 |
| I22 / P1 | 数据库连接/写入发生非锁类错误 | 当前通常返回 500；不要误断言为 503；记录日志并验证事务无部分提交 |

I03–I06 等直接修改 workspace 的方式是对白盒同步/清理逻辑的测试；当前没有公开的拉取或刷新工作区接口。

### 可稳定复现的 409

在数据库客户端的会话 A 中执行，保持事务不提交（替换 UUID）：

```sql
BEGIN;
SELECT id FROM repositories WHERE id = '<repository_id>'::uuid FOR UPDATE;
```

回到 Docs 页面，展开 **POST /api/v1/repositories/{repository_id}/index**，点击 **Try it out**，填入被锁定的仓库 id，点击 **Execute**。

必须立即收到 409。也可调用同一仓库 `/scan`，它应同样返回 409。会话 A 执行 `ROLLBACK;` 释放锁，再调用 index 应成功。若用两个很快的 HTTP 请求并发，可能串行执行而都成功，不能据此判断行锁失效。

### 503 与回滚验证方式

- I10：先完成基线索引，暂停其他操作，将该测试 workspace 临时改名为同级新名字，再调用 index；检查 503 和数据库旧记录，最后改回原名。需先确认操作路径就是该测试记录返回的 workspace，且在测试 WORKSPACE_ROOT 内。NULL 场景仅在独立测试数据库中修改该记录并恢复。
- I11：建议后续使用真实 PostgreSQL 集成测试，在 `repository_indexing_service.save_chunked_file` 调用第二次时抛出 `RepositoryScanError`，第一次使用真实保存函数并确保待处理源码已变化。HTTP 应为 503，异常结束后用新 Session 比较完整前后数据快照（包括块 ID/content、文件 hash/size）；不能只比较总数。这里需在实际调用点替换函数，并在测试结束恢复。
- I22：非锁 DBAPIError 原样抛出，路由未将所有数据库错误转换为 503。使用 TestClient 测错误响应时设置 `raise_server_exceptions=False`；断言 500 时同时确认日志确实来自目标故障。

## 7. 创建仓库的前置负例

这些是 `POST /repositories` 的用例，失败时不会取得可用于 index 的新 id。

| 输入 | 预期 |
|---|---|
| 普通目录，没有 Git | 422，Cannot inspect the supplied Git working tree |
| git init 后未提交 | 422，Cannot resolve a committed HEAD |
| 已提交后修改文件、暂存未提交或新增未跟踪文件 | 422，Repository must have a clean working tree |
| 使用仓库子目录 | 422，Source path must be the Git working tree root |
| 相对路径 | 422，Source path must be absolute |
| 干净的 detached HEAD | 201，git_branch=null，可正常 index |

不要用 `scripts/check_repository.py` 替代注册接口准备正常数据：该脚本直接插入记录，没有创建 workspace，会触发 index 的 503 分支。

## 8. 执行顺序及通过标准

服务和迁移就绪后，先按第 4 节在 Docs 完成注册、索引、文件查询、重复索引与参数负例，再配合数据库验收，然后覆盖 I03–I11，最后执行 P1 和注册负例。仅完成 Docs 冒烟不等于已验证事务回滚和块内容；所有 P0 通过、跳过原因准确、重复索引无重复块、失败无部分写入、其他仓库无误删，才判定核心功能通过。

本次已执行生成脚本，确认源仓库工作区干净，并按应用的 clone + detached checkout 方式检查：17 个已跟踪文件在克隆前后 SHA-256 全部一致，超大样例恰为 1,048,577 字节。初始提交短 hash 为 `6e5522e`。

未执行真实 HTTP、Python 分块计算、数据库断言或故障注入；5/5/5 是基于源码和样例内容推导的预期，尚不是接口实测结果。建议记录：用例 ID、repository_id、commit_hash、HTTP 状态/响应、SQL 前后快照、是否通过、失败日志。
