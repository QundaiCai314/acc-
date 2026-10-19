# AI Disaster Commander · 灾害空间 RAG 后端

当前版本 0.2.0。面向一个街区或园区的地震救援演练，优先支持**现场图片与地图联合查证**，采用 **AI 候选标注 → 人工审核/修正 → 空间和时间检索 → 带图片证据的回答**。

当前完成结构化查询闭环、自然语言空间问答与可配置的图片模型请求适配器；不是已完成实地验证的救援系统。原有约束规划保留兼容，暂缓扩展，见 [旧版规划文档](docs/legacy-planner.md)。

## 运行

已验证 Windows x64 / Python 3.14。使用现有依赖，无新增依赖。

```powershell
py -3.14 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

交互文档：http://127.0.0.1:8000/docs 。不会自动启动常驻服务。

离线契约演示（不调用外部服务）：

```powershell
.venv/Scripts/python.exe -m examples.demo_spatial
```

该演示生成合成示意图片，导入明确标为外部未核实来源的测试候选，展示“审核前无结果，审核后返回证据，撤回后无结果”。它不是 AI 识别效果展示；数据仅存临时数据库，执行后清理。

## 首个验收问题

“A 楼 100 米内，哪些入口有已审核的障碍物记录？展示地图位置、现场图片和观察时间。”

自然语言入口为 POST /spatial/datasets/{dataset_id}/ask：模型只把问题解析成校验后的查询意图，缺少地图中心、中心无坐标或没有明确半径时返回 clarification_needed 要求补充；未指定时间范围默认最近 24 小时。每次解析保存为运行记录（返回 run_id，含原问题与解析结果，可经 GET /spatial/runs/{id} 排查）。距离、审核状态、时间过滤和证据回答均由后端确定性完成，不让模型编造证据。结构化入口 POST /spatial/datasets/{dataset_id}/query 仍可直接使用。

## 前端接口流程

| 步骤 | 接口 | 用途 |
| --- | --- | --- |
| 1 | POST /spatial/datasets | 建不可变地图快照，参考 examples/spatial_dataset.json |
| 2 | POST /spatial/datasets/{dataset_id}/images | 上传图片及来源、拍摄时间、真实/演练属性 |
| 3 | POST /spatial/images/{image_id}/analyze | 调用配置模型，保存运行记录及待审核候选 |
| 4 | GET /spatial/datasets/{dataset_id}/annotations | 读取原始候选、审核修正及状态 |
| 5 | POST /spatial/annotations/{annotation_id}/review | 批准、拒绝或修正后批准 |
| 6 | POST /spatial/datasets/{dataset_id}/query | 联合检索，返回 citations 与中文回答 |
| 7 | POST /spatial/annotations/{annotation_id}/withdraw | 撤回错误批准，后续检索排除 |

辅助接口：GET /spatial/datasets/{id}、GET /spatial/images/{id}、GET /spatial/images/{id}/content、GET /spatial/runs/{id}。运行记录含模型原始内容，用于排查，不应视为可信指令。

外部候选导入：POST /spatial/datasets/{id}/annotations，提交 image_id、annotation、source_note。来源固定为 imported_unverified，调用者不能自行伪装为 ai；用于离线演练或已有工具输出导入。所有来源均须审核。

查询示例（as_of 应调整到素材拍摄时间之后）：

```json
{
  "center_entity_id": "building-a",
  "radius_m": 100,
  "kind": "entrance",
  "observation": "obstacle_visible",
  "as_of": "2026-10-18T12:00:00+08:00",
  "max_age_hours": 24
}
```

图片字段：name、captured_at（带时区）、source、evidence_basis（exercise/field_image）、mime_type（image/png 或 image/jpeg）、content_base64。单张解码后至多 5 MB；仅检查 Base64、格式签名和大小，不做完整图片解码、EXIF 读取或自动定位。

annotation 字段：entity_id（候选允许 null）、observation、description、bbox、confidence。bbox 为归一化 x_min、y_min、x_max、y_max，原图左上角为原点；observation 为 obstacle_visible、no_obstacle_visible 或 unknown。

审核字段：reviewer、action（approve/reject）、note，可附 corrected_annotation。批准必须关联本数据集实体。原始候选不覆盖，人工修正版单独保存。审核后不能直接改写；修改需撤回原批准、新建候选、重新审核。重复撤回返回 409。

## 模型配置与验证状态

启动前设置以下环境变量（不会自动读取 .env）：

- VISION_CHAT_URL：服务方确认的完整 HTTPS Chat Completions 地址，不自动拼接。
- VISION_API_KEY：轮换后的密钥，不要使用已在聊天中公开的旧值。
- VISION_MODEL：服务方确认支持图片输入的模型标识，不预设或猜测型号。

适配器采用 Chat Completions 风格的 messages、image_url data URI 和 choices[0].message.content；内容若被 ``` 代码围栏包裹会先剥离。模型输出须符合候选 JSON Schema；非法输出、未知地图实体或请求错误返回 502，不生成可检索记录。缺少配置返回 503。不自动重试，避免重复费用；每次 /analyze 均独立调用，尚无幂等键。

**第三方网关尚未实测。** 测试使用 httpx.MockTransport，不发真实图片/密钥、不产生调用费用。读取 [OpenAI 官方图片文档](https://platform.openai.com/docs/guides/images-vision) 时返回 403，在线协议核实未完成，该链接不是网关兼容性证明。AnySearch 和星云 3D 尚未接入。

## 结果边界

- 只接受 WGS84 点位。高德/腾讯等地图常用其他坐标系，须确认并转换，不能仅改名称。
- 地图快照由人工提供，保留 curator 与 map_source；AI 不生成真实坐标。地图录入本身无独立审批流，录入者负责核实。
- Haversine 计算近似球面距离，不是道路距离或建筑边界距离；范围筛选在四舍五入前执行。
- 演练坐标和演练图片在回答中标记。真实图片配模拟坐标不能据此声称真实距离。
- 未审核、拒绝、撤回、范围外、无坐标及时间窗外记录不进入 citations。中心无坐标返回 422，其他未知点列入 missing_coordinates。
- as_of 限制图片时间，使用当前有效审核状态，不是历史回放。默认最近 24 小时，可调整。
- query 返回 older_evidence_count，按标注条数统计早于时间窗、且符合其余查询条件的有效已审核记录（不按图片或地点去重）；ask 在 evidence 中返回同一字段。没有窗内证据时，回答会提示旧记录数量、最新采集时间和扩大时间范围的建议。未来记录不计入；旧记录不会自动进入 citations，也不会将 insufficient_evidence 改为 evidence_found。时间窗起止时刻均包含在内。
- 返回的是观察记录，不是当前状态汇总，不解决冲突证据、不判断通行安全。“未见明显障碍物”不等于“可通行”。
- confidence 为模型/录入者自报，未校准；人工审核也不保证事实绝对正确。
- 无匹配明确回答无法判断。回答中 [1]、[2] 对应 citations 顺序。

## 维护

- spatial_models.py 定义输入与查询输出，spatial.py 负责审核和空间查询，vision.py 隔离外部模型，store.py 持久化。
- SQLite 版本仍为 1，旧场景和计划保持可读。复用 decisions 表的 plan_id 存 annotation ID；未来拆表须迁移。
- 测试覆盖原有规划、审核门槛、人工修正、撤回、持久化、跨数据集引用、时间窗、未知坐标、距离边界和模型协议错误。
- requirements.lock.txt 固定版本；Starlette 测试客户端仍有 httpx 弃用提醒，测试通过。
- 默认 data/disaster.db，可用 DISASTER_DB_PATH 调整。停止服务后复制数据库备份。
- 图片 Base64 存入 SQLite，JSON 扫描只面向小型演示，扩展时采用文件/对象存储及空间索引。
- 仅本机单用户，无鉴权、审核者身份验证、分页、限流、流式上传限额或跨域配置；reviewer 为自报身份。多人或公网部署前必须补齐访问控制。
- 新空间数据尚无 RDF 导出/推理，RDF 当前只适用于旧规划场景。自由问答、视频、三维配准及道路网络是后续开发项。
