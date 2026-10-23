# 小团队部署与维护

v0.3.0 支持同一服务上多个工作空间；各工作空间共享一个 SQLite 文件，但所有业务读取、写入、审核及图片访问均按已认证工作空间过滤。管理员也不能通过别人的 UUID 跨空间访问。旧数据迁移到 default。

## 创建账号

在服务器本机运行，输出的令牌只显示一次。通过安全渠道分别交给对应用户，不写进源码、前端包或 URL。

~~~powershell
.venv/Scripts/python.exe -m app.manage --user operator --role contributor --workspace default
.venv/Scripts/python.exe -m app.manage --user reviewer --role reviewer --workspace default
.venv/Scripts/python.exe -m app.manage --user reader --role viewer --workspace default
.venv/Scripts/python.exe -m app.manage --user administrator --role admin --workspace default
.venv/Scripts/python.exe -m app.manage --user operator --workspace default --set-password
~~~

最后一条命令在隐藏输入中设置或重置密码（12–256 字符），不会把密码放进命令参数或输出。新账号也可在创建命令中加 --set-password。修改已有账号的密码保留角色、个人令牌和启用状态。

网页注册只允许申请加入已经存在且有启用管理员的工作空间：POST /auth/register 保存待审批申请，不会立即创建可登录账号。管理员在网页「账号管理」中选择角色并批准或拒绝；批准后申请人的密码摘要才写入账号库。管理员可以停用/启用成员，并为启用中的成员签发有效 30 分钟、只能使用一次的重置码。成员登录后可在「账号管理」中修改自己的密码；修改或重置都会使旧登录会话失效。管理员账号的密码仍通过本机 app.manage --set-password 维护。

账号与注册申请默认保存在 data/access.json.accounts.db（账号库 schema 1）。data/access.json 仅用于首次升级时导入的旧配置种子，迁移后编辑该 JSON 不再生效；命令行 --config 与 DISASTER_ACCESS_CONFIG 仍使用原路径定位账号库。账号库含令牌 SHA-256 摘要及可选的 PBKDF2-HMAC-SHA256 密码摘要（600000 次迭代、随机盐），不存储明文密码。个人令牌采用 32 字节随机数。网页与命令行账号变更共享 SQLite 写事务，每次请求重新读取，因此撤销不依赖服务器重启。文件和整个 data 目录只应允许服务器账号及运维人员读取。

| 角色 | 权限 |
| --- | --- |
| viewer | 读取本工作空间数据；结构化/自然语言查询、寻路、推理、坐标转换 |
| contributor | 加上数据集、图片、候选、路网、配准、关系提交；AI 分析；背景检索和运行日志 |
| reviewer | 加上批准、拒绝、撤回；旧规划审批 |
| admin | 加上外部服务配置状态与真实探测；审批本空间注册、启停成员及签发重置码 |

团队模式的 reviewer、curator 和 created_by 从认证身份产生，无法通过请求体冒充他人。审核员可以审核自己提交的内容，当前没有强制双人复核制度。

## 启动

~~~powershell
$env:DISASTER_MODE = 'team'
$env:DISASTER_ACCESS_CONFIG = 'data/access.json'
$env:DISASTER_CORS_ORIGINS = 'https://your-frontend.example'
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2 --no-proxy-headers
~~~

把本机端口放在 HTTPS 反向代理后，由代理设置连接数、请求头大小与超时；不要把令牌通过明文 HTTP 传输。CORS 必须列出实际前端来源，禁止通配符。服务之间使用同一块本地磁盘上的数据库，不放在网络共享盘。首次升级先停止旧进程，再备份和启动新版本，不混跑 v0.2.0 与 v0.3.0。

API 请求头：Authorization: Bearer 用户令牌或登录会话。GET /auth/me 返回当前用户、角色和工作空间。GET /health 和 POST /auth/login、/auth/register、/auth/reset-password 允许匿名访问；包含 docs/openapi 在内的其他访问均要求身份。团队模式下 API 客户端或受控代理需为文档请求也携带令牌。local 模式可继续使用本机 Swagger 文档。

网页登录：POST /auth/login 接受 JSON：{"user_id":"operator","workspace":"default","password":"用户密码"}，成功返回 access_token、token_type、expires_at、identity。注册使用 POST /auth/register；审批和成员操作使用 GET/POST /auth/members；登录用户用 POST /auth/password 修改密码，管理员重置码用 POST /auth/reset-password 完成找回。会话有效期 8 小时，服务端 SQLite 仅保存令牌摘要，与原个人令牌共用角色与空间隔离。POST /auth/logout 撤销当前密码登录会话，所有角色均可退出。个人令牌连接时退出仅清除页面凭据，永久撤销仍由管理员完成。网页登录凭据和会话不写入浏览器存储；刷新页面需重新登录，没有刷新令牌或跨标签页单点退出。

默认 local 模式拒绝非回环地址，不适用于反向代理部署；代理通常把请求转为回环地址，因此必须显式改为 team。team 配置缺失时启动失败，运行中配置损坏时拒绝请求，不降级为匿名。

## 限流、并发与重试

- 默认每用户每分钟 120 次普通请求，另有 10 次模型/搜索请求额度；配置字段 requests_per_minute、model_requests_per_minute 可调整。SQLite 原子计数让多个 worker 共享额度。固定分钟窗口在边界附近允许短时突发，公网流量限制仍应由代理承担。
- 匿名登录、注册、密码重置共用每来源地址每分钟 30 次额度；每账号与工作空间的登录、注册、重置分别限每分钟 10、3、5 次（含成功请求）；账号请求体上限 4 KB。代理部署时按 ASGI peer 计数，不信任任意转发头；同一代理后的用户可能共享地址额度，可在可信代理层补充来源限流。登录错误不区分账号不存在、禁用或密码错误。
- 请求体实际接收上限 8 MB，包括无 Content-Length 的分块上传。图片 Base64 解码后文件上限 5 MB；PNG/JPEG 必须通过结构校验与完整像素解码，最多 2000 万像素、单边 10000 像素，拒绝动画与损坏/截断文件。保留原始字节与 SHA-256，不自动重编码或删除 EXIF；EXIF 不会自动成为可信测绘坐标。校验错误不回显原图 Base64。单请求限额不能替代磁盘容量管理；存储配额尚未实现。
- 审核和撤回有数据库唯一约束；并发重复操作一份成功，其余 409，不覆盖原记录。
- 团队模式 POST /spatial/images/{id}/analyze 必须提供 Idempotency-Key（1–128 个英文字母、数字、短横线或下划线）。同一工作空间、图片和 key 的成功请求返回原结果；pending/failed 返回 409。崩溃或上游超时可能已计费，先检查再用新 key 明确重试。不会自动再次调用供应商。local 模式可选该头。
- 图片分析幂等记录不自动清理，成功重放表示原分析结果，不代表候选仍处于待审核状态；最新审核状态通过 annotations 查询。
- 数据集、图片、标注、空间工件列表支持 limit/offset 和 next_offset，单页最多 200；检索内部仍完整扫描当前数据集有效标注。图片列表与证据查询不会把 Base64 全量返回或解析进 Python 对象。

## 撤销、轮换与备份

~~~powershell
.venv/Scripts/python.exe -m app.manage --user operator --workspace default --disable
.venv/Scripts/python.exe -m app.manage --user operator --workspace default --role contributor --rotate
~~~

轮换会替换原令牌，旧令牌及登录会话立即失效。重置密码也会令旧登录会话失效。网页或命令行禁用账号时永久作废旧个人令牌、登录会话及未使用的重置码；重新启用不会恢复这些旧凭据，需要重新登录或签发新令牌。正在执行的已认证请求不会被强行取消。前端收到 401 后清除身份、现场缓存和草稿并返回登录页；不自动重试。会话过期后不可使用，过期行在下次创建会话时清理。

升级和备份时停止所有后端 worker 及 app.manage 写操作，再备份业务库 data/disaster.db、账号库 data/access.json.accounts.db、旧 JSON 种子（如有）和本地供应商配置；这些文件都属于敏感资料。SQLite backup API 可生成单库一致快照，但分别在线备份两库不能保证同一时刻，完整恢复点须停写。不能只复制正在写入的 WAL 数据库主文件。恢复时先停服务，将整组备份恢复至原路径，再启动并核验身份、申请、审核记录与图片散列。不要删除账号库后用过时 JSON 重建账号，否则可能恢复已撤销凭据。

schema 1/2/3/4 → 5 的变更保留记录，旧数据默认属于 default；schema 3 新增审核租约表，schema 4 新增登录会话表，schema 5 新增注册申请表。迁移发现历史重复撤回会失败，应先保存备份、人工核对冲突，而不是删除历史。schema 5 数据库不能由只支持 schema 4 的旧版程序打开；回退程序时同时恢复升级前备份，不能仅修改 user_version。

账户配置总容量为 1000 个账号（所有工作空间合计）。达到容量后网页批准返回 409，申请保持待审批。注册与命令行修改共用账号库事务，并在写入前重新校验账号和工作空间管理员。批准时创建账号与删除申请在同一事务内提交，异常或进程被终止会一起回滚；同一申请并发批准只有一次成功。旧版本已经留下的同名申请仍可拒绝清理，不会删除或覆盖已创建账号。CLI 等待密码输入时不持有账号写锁。

图片候选支持五分钟审核租约：GET /spatial/annotations/{id}/lease 查询，POST /claim 领取或续期，POST /release 释放自己的租约。只有 admin/reviewer 可领取。另一审核员持有未过期租约时，提交审核返回 409；成功审核清除租约。领取与审核写入在 SQLite 事务内检查，跨进程生效。没有租约时仍保留先提交成功者生效的乐观并发机制。前端通过「刷新」获取最新状态，没有后台自动续期或在线成员广播。

当前适用于一个街区/园区、小团队和单机本地盘部署。没有 SSO、邮件找回密码、跨机器数据库、队列、自动业务存储清理或高并发性能承诺；网页注册仅是管理员审批制的工作空间申请，不是开放式自动注册。

## 从 JSON 账号存储升级

1. 停止所有旧后端及账号管理命令，备份上述文件。即使版本号仍为 v0.3.0，也禁止旧、新账号存储实现混跑。
2. 安装当前 requirements.lock.txt（新增 Pillow 13）。保持 DISASTER_ACCESS_CONFIG 和业务库路径不变，启动一个新 worker。启动事务将旧 JSON 和业务库中的注册申请导入账号库；已有账号库不会再次读取旧 JSON。
3. 使用管理员登录、查看成员和待审批申请；验证后再启动其他 worker。迁移以旧业务库绝对路径记录完成标记，重启不会恢复已经处理的申请。旧业务表保留作为迁移历史，新运行路径不再读写它。迁移冲突或未知账号库版本会使启动失败，先检查备份和冲突来源，不删除记录强行启动。
4. 核验成功后将旧 JSON 安全归档到配置路径之外，防止账号库意外丢失后从旧种子重建；DISASTER_ACCESS_CONFIG 仍保持原值，账号库不依赖 JSON 文件继续存在。运行中账号库缺失/损坏时请求返回 503，不降级匿名访问。
5. 回滚必须停止新进程并恢复升级前的整组备份，再使用旧代码。不能让旧程序读取迁移后但已过时的 JSON；不能只回滚代码而保留混合数据。
