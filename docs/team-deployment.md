# 小团队部署与维护

v0.3.0 支持同一服务上多个工作空间；各工作空间共享一个 SQLite 文件，但所有业务读取、写入、审核及图片访问均按已认证工作空间过滤。管理员也不能通过别人的 UUID 跨空间访问。旧数据迁移到 default。

## 创建账号

在服务器本机运行，输出的令牌只显示一次。通过安全渠道分别交给对应用户，不写进源码、前端包或 URL。

~~~powershell
.venv/Scripts/python.exe -m app.manage --user operator --role contributor --workspace default
.venv/Scripts/python.exe -m app.manage --user reviewer --role reviewer --workspace default
.venv/Scripts/python.exe -m app.manage --user reader --role viewer --workspace default
.venv/Scripts/python.exe -m app.manage --user administrator --role admin --workspace default
~~~

配置默认保存在 data/access.json，仅含令牌 SHA-256 摘要。令牌采用 32 字节随机数。账号管理命令应由单个本机管理员执行，配置文件原子替换，每次请求重新读取，因此撤销不依赖服务器重启。文件和整个 data 目录只应允许服务器账号及运维人员读取。

| 角色 | 权限 |
| --- | --- |
| viewer | 读取本工作空间数据；结构化/自然语言查询、寻路、推理、坐标转换 |
| contributor | 加上数据集、图片、候选、路网、配准、关系提交；AI 分析；背景检索和运行日志 |
| reviewer | 加上批准、拒绝、撤回；旧规划审批 |
| admin | 加上外部服务配置状态与真实探测；账号变更由本机命令完成 |

团队模式的 reviewer、curator 和 created_by 从认证身份产生，无法通过请求体冒充他人。审核员可以审核自己提交的内容，当前没有强制双人复核制度。

## 启动

~~~powershell
$env:DISASTER_MODE = 'team'
$env:DISASTER_ACCESS_CONFIG = 'data/access.json'
$env:DISASTER_CORS_ORIGINS = 'https://your-frontend.example'
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2 --no-proxy-headers
~~~

把本机端口放在 HTTPS 反向代理后，由代理设置连接数、请求头大小与超时；不要把令牌通过明文 HTTP 传输。CORS 必须列出实际前端来源，禁止通配符。服务之间使用同一块本地磁盘上的数据库，不放在网络共享盘。首次升级先停止旧进程，再备份和启动新版本，不混跑 v0.2.0 与 v0.3.0。

API 请求头：Authorization: Bearer 用户令牌。GET /auth/me 返回当前用户、角色和工作空间。除 GET /health 外，包含 docs/openapi 在内的访问均要求身份；团队模式下 API 客户端或受控代理需为文档请求也携带令牌。local 模式可继续使用本机 Swagger 文档。

默认 local 模式拒绝非回环地址，不适用于反向代理部署；代理通常把请求转为回环地址，因此必须显式改为 team。team 配置缺失时启动失败，运行中配置损坏时拒绝请求，不降级为匿名。

## 限流、并发与重试

- 默认每用户每分钟 120 次普通请求，另有 10 次模型/搜索请求额度；配置字段 requests_per_minute、model_requests_per_minute 可调整。SQLite 原子计数让多个 worker 共享额度。固定分钟窗口在边界附近允许短时突发，公网流量限制仍应由代理承担。
- 请求体实际接收上限 8 MB，包括无 Content-Length 的分块上传。图片原有解码后 5 MB 限制仍保留。单请求限额不能替代磁盘容量管理；存储配额尚未实现。
- 审核和撤回有数据库唯一约束；并发重复操作一份成功，其余 409，不覆盖原记录。
- 团队模式 POST /spatial/images/{id}/analyze 必须提供 Idempotency-Key（1–128 个英文字母、数字、短横线或下划线）。同一工作空间、图片和 key 的成功请求返回原结果；pending/failed 返回 409。崩溃或上游超时可能已计费，先检查再用新 key 明确重试。不会自动再次调用供应商。local 模式可选该头。
- 图片分析幂等记录不自动清理，成功重放表示原分析结果，不代表候选仍处于待审核状态；最新审核状态通过 annotations 查询。
- 数据集、图片、标注、空间工件列表支持 limit/offset 和 next_offset，单页最多 200；检索内部仍完整扫描当前数据集有效标注。图片列表与证据查询不会把 Base64 全量返回或解析进 Python 对象。

## 撤销、轮换与备份

~~~powershell
.venv/Scripts/python.exe -m app.manage --user operator --workspace default --disable
.venv/Scripts/python.exe -m app.manage --user operator --workspace default --role contributor --rotate
~~~

轮换会替换原令牌，旧令牌立即失效。正在执行的已认证请求不会被强行取消。客户端收到 401 后重新配置新令牌；不要无限自动重试。

升级前备份数据库、账户配置和本地供应商配置，备份视为敏感文件。可停止全部服务后复制数据库，或使用 SQLite 的 backup API 生成一致性备份；不能在 WAL 模式下只复制一个正在写入的 .db 文件。恢复先停服务，把数据库和配套配置恢复到同一路径，再重新启动并运行只读检查。

schema 1 → 2 的变更保留记录，旧数据默认属于 default。迁移发现历史重复撤回会失败，应先保存备份、人工核对冲突，而不是删除历史。schema 2 数据库不再由旧版程序打开。

当前适用于一个街区/园区、小团队和单机本地盘部署。没有 SSO、网页登录、跨机器数据库、队列、自动存储清理或高并发性能承诺；这些限制不影响已实现的身份隔离与并发唯一性。
