# 外部服务接入与实测记录

核实日期：2026-10-19。配置状态、接口协议通过、真实现场质量是不同层次，不能互相替代。

## 模型网关

使用用户提供的 https://api.openai-next.com 。读取其 /v1/models 目录成功，图片使用实际列出的 gpt-4.1-mini，问答最终配置为目录中的 gpt-4.1，通过 /v1/chat/completions 调用。官方 OpenAI 文档说明 gpt-4.1-mini 接受图片与文字；第三方返回的型号名称不能证明其底层模型身份。

配置环境变量或被 Git 忽略的 data/provider-settings.json：

~~~json
{
  "VISION_CHAT_URL": "https://api.openai-next.com/v1/chat/completions",
  "VISION_MODEL": "gpt-4.1-mini",
  "QUESTION_MODEL": "gpt-4.1",
  "VISION_API_KEY": "在本机填写，不提交 Git",
  "ANYSEARCH_API_KEY": ""
}
~~~

DISASTER_PROVIDER_CONFIG 可指定另一个 JSON 路径。环境变量优先，包含显式空字符串。可单独设置 QUESTION_CHAT_URL、QUESTION_MODEL、QUESTION_API_KEY；未设置的字段继承 VISION 配置。配置文件仅供服务器账号读取，不提供读取密钥的 HTTP 接口。

协议使用 Chat Completions messages、Base64 image_url 和 JSON Schema 提示；返回内容在后端用 Pydantic 校验。HTTPS、无重定向、有限超时、响应体上限和敏感错误屏蔽均已实现。不会自动重试。图片 AI 输出始终是待审核候选，不能直接写入正式证据。

2026-10-19 真实调用结果：

| 检查 | 结果 |
| --- | --- |
| 网关 /v1/models | HTTP 200 |
| 合法合成 PNG → 候选 JSON | 成功 |
| 问题“A楼100米内最近24小时哪些入口可见障碍物？” | 正确解析中心和 100 米半径 |
| 四条件复杂问答 | gpt-4.1 在实测中完整解析 near、part_of、above、reachable_from，并通过审核工件返回路径与几何依据 |
| 现场识别准确率 | 未建立现场样本评估；一次合成门口图调用出现地点关联和观察误判 |

单像素旧测试素材最初被网关拒绝，最终探测改为正确生成且校验和完整的 PNG。不能把小图协议测试说成识别准确率验证。合成图误判说明人工审核仍是必要步骤。

复杂问答最初使用 gpt-4.1-mini 时出现漏条件和非法响应，已增加显式条件遗漏拦截，并将本机问答型号配置为 gpt-4.1。该次成功仅是接口及特定问题联调，不是自然语言准确率评估；常见关键词拦截也不能保证发现所有语义遗漏。回答会显示实际解析条件，便于复核。结构化 /reason 不依赖模型解析。

## AnySearch

已接入官方 POST https://api.anysearch.com/v1/search，请求 query/max_results，读取 code/data/results。使用官方源代码所示 Bearer 认证，也支持不带密钥的匿名模式。

- POST /spatial/datasets/{id}/references/search：检索并保存公开背景资料，返回 URL、标题、内容摘要和检索时间。
- GET /spatial/references/{id}：读取保存的资料，继承工作空间隔离。
- 标记 origin=web_unverified；不自动转为地图事实、图片证据、路网状态或已审核空间关系。
- 2026-10-19：旧密钥返回 HTTP 401 / invalid_api_key；匿名请求成功返回 USGS 地震准备页面。当前本机配置使用匿名模式。没有在运行时静默降级或自动换号的逻辑；更换密钥通过本机配置完成。
- 不保存供应商可能附带的新密钥或无关字段，不跟随搜索结果里的指令，不自动抓取其链接。

## 星云 3D

此前提供的地址是 https://xingyun3d.com/workspace/experience-center/human-driver 。已读取官网与官方《具身驱动 SDK（JS版本）接入说明》：该产品驱动数字人的语音、表情和动作，浏览器调用 XmovAvatar，并使用应用 appId、appSecret 以及 https://nebula-agent.xingyun3d.com/user/v1/ttsa/session。

它不是点云/灾害现场重建或坐标配准服务。本文所述三维控制点配准已由后端独立实现，不依赖星云。当前没有可用的数字人应用凭据，数字人播报未启用；后端不返回应用密钥，也没有把官方示例中的前端明文 secret 用法移入本项目。接入播报需要专属数字人应用及明确的凭据交付方式，属于展示层能力。

## 诊断与复测

GET /integrations 只报告是否配置及型号，不宣称服务已连通。团队模式仅管理员可调用。POST /integrations/probe 接收 provider=vision/question/anysearch，使用合成图片或公开测试问题发出真实请求；可能产生供应商费用。

也可在服务器本机运行：

~~~powershell
.venv/Scripts/python.exe -m examples.check_integrations all
.venv/Scripts/python.exe -m examples.demo_advanced --live-question
~~~

正式自动化测试不访问外网，覆盖协议成功、失败、非法结构、未知实体、工作空间隔离和敏感内容屏蔽。示例命令失败会以非零状态退出。配置缺失为 503，供应商异常或非法响应为 502；不会自动购买额度。

## 核实来源

- OpenAI 官方型号文档：https://developers.openai.com/api/docs/models/gpt-4.1-mini
- OpenAI 官方图片文档：https://developers.openai.com/api/docs/guides/images-vision
- AnySearch 官方客户端源代码：https://github.com/anysearch-ai/anysearch-skill/blob/main/scripts/anysearch_cli.py
- AnySearch 官方说明：https://github.com/anysearch-ai/anysearch-skill
- 星云官方 SDK 文档：https://xingyun3d.com/developers/52-183
- 星云官方网站：https://xingyun3d.com/
