# AI Disaster Commander v0.3.0 · 审核交付

本包为可维护的前后端源码包，不是免安装 EXE。已验证 Windows x64、Python 3.14 和 Chrome。请先完整解压，再执行命令。不要双击 index.html：前端 ES Modules 需要 HTTP 服务。

## 先看前端

在解压后的项目根目录打开 PowerShell：

~~~powershell
py -3.14 -m http.server 8080 --bind 127.0.0.1 --directory frontend
~~~

打开 http://127.0.0.1:8080/ ，在登录页选择「进入离线演练」。无需账号或模型密钥，可检查地图、悬浮窗、图片审核、路网和三维示例。底图瓦片需要联网；演练操作仅保存在页面内存中，刷新清空。

## 启动完整项目

在项目根目录打开第二个 PowerShell：

~~~powershell
py -3.14 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
$env:DISASTER_CORS_ORIGINS = 'http://127.0.0.1:8080'
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
~~~

初次安装依赖需要联网。默认 local 模式仅供本机：在网页登录页展开「使用个人令牌 / 本机连接」，后端填 http://127.0.0.1:8000 ，令牌留空。接口文档为 http://127.0.0.1:8000/docs 。后端初次启动是空数据；前端离线示例不会自动写入数据库，可使用 examples/ 中的合成 JSON 或自己的数据导入。

## 启用账号登录和注册

停止刚启动的后端（Ctrl+C），在同一窗口创建本机管理员，再以 team 模式启动：

~~~powershell
.venv/Scripts/python.exe -m app.manage --user administrator --role admin --workspace default --set-password
$env:DISASTER_MODE = 'team'
$env:DISASTER_ACCESS_CONFIG = 'data/access.json'
$env:DISASTER_CORS_ORIGINS = 'http://127.0.0.1:8080'
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
~~~

命令隐藏输入密码（至少 12 字符），个人令牌仅显示一次，请自行保管。在登录页使用该账号、密码及 default 工作空间登录。其他用户可注册申请，由管理员在「账号管理」批准；忘记密码由管理员签发一次性重置码。没有预设密码，不含原电脑账号。远程部署必须配置 HTTPS、准确 CORS 和受控反向代理，详见 [多人部署](docs/team-deployment.md)。

## 模型与数据

图片模型、自然语言解析及 AnySearch 的配置说明见 [README](README.md) 和 [外部服务](docs/integrations.md)。包内不含供应商密钥；未配置时相关功能会明确报告不可用，结构化检索和离线演练可独立使用。项目不会自动读取 .env。

包内不含 .git、.venv、.env、data、现场数据库、账号配置、截图缓存或本机日志。迁移已有现场时，须另外安全备份数据库及配套配置；禁止在 WAL 写入期间只拷贝 .db 文件。

## 核对与维护

- [审核报告及未验证范围](docs/audit-2026-10-22.md)
- [前端启动、交互与浏览器验证](frontend/README.md)
- [三维、路网和复杂关系的边界](docs/spatial-extensions.md)

桌面 ZIP 旁的 .sha256.txt 是整包校验值，可用 Get-FileHash -Algorithm SHA256 检查。ZIP 内 DELIVERY-MANIFEST.json 记录源码提交号和每个交付文件的 SHA-256；清单本身不列入自身哈希。校验值用于发现意外损坏，不是数字签名。

关闭各启动窗口的服务使用 Ctrl+C。项目不会安装开机启动项。
