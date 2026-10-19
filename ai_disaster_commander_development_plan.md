# AI Disaster Commander 完整开发方案

> 用途：交给 Cursor、Codex、Claude Code 或其他 Coding Agent 分步骤实施  
> 开发策略：契约先行、纵向切片、模块化单体、Mock 先行、持续集成  
> 第一阶段目标：完成可验证的产品原型，不用于真实救援决策

---

## 0. 使用方式

不要一次把整份文档交给 Coding Agent 并要求“全部实现”。正确方式是：

1. 先让 Coding Agent 阅读本方案和仓库说明；
2. 每次只执行一个阶段或一个任务编号；
3. 每个任务完成后运行对应验证；
4. 检查变更和测试结果；
5. 验收通过后再进入下一任务；
6. 不允许 Coding Agent 自行扩大产品范围。

推荐节奏：

```text
计划一个小任务
→ Coding Agent 实现
→ 自动测试
→ 人工查看页面/结果
→ 修复
→ 提交一个小版本
```

---

# 第一部分：目标澄清

## 1. 原始需求

使用 Coding 软件开始开发 AI Disaster Commander，并获得一套可以逐步执行、逐步验证的完整开发方案。

## 2. 显性目标

- 建立清晰的技术架构；
- 将产品拆解成可独立实施的开发任务；
- 明确前后端、AI、RDF 和规划器的实施顺序；
- 给每个步骤设置完成标准和验证方式；
- 提供可以直接复制给 Coding Agent 的阶段提示词。

## 3. 隐性期望

- 避免 Coding Agent 一次生成过多不可维护代码；
- 尽早得到一个可以运行的产品闭环；
- 后续更换模型、数据库或页面实现时不需要推倒重来；
- 让视频分析、知识图谱和救援规划真正联通；
- 保持产品输出可追溯、可人工修正、可安全演示。

## 4. 核心目标

> **先完成一个地震建筑坍塌场景的端到端产品原型：上传短视频，生成带证据的现场观察，更新 RDF 世界状态，在资源和道路约束下生成候选救援方案，并在人工纠错后重新规划。**

## 5. 当前采用的开发假设

为避免等待补充信息，方案默认采用以下假设：

| 项目 | 默认假设 |
|---|---|
| 开发人员 | 1 名开发者 + Coding Agent；也适用于 2–3 人小组 |
| 第一场景 | 地震后建筑局部坍塌 |
| 输入 | 30–90 秒离线 MP4 视频，不做实时直播流 |
| AI | 调用现成多模态模型，不训练基础模型 |
| 产品形态 | 桌面优先的 Web Command Center |
| 部署 | 本地 Docker Compose，可后续迁移云端 |
| 地图 | 先用简化地图和人工坐标，后续接真实 GIS |
| 用户 | 单用户原型，权限和多租户后置 |
| 安全定位 | 只生成候选方案，不自动下达真实救援指令 |
| 时间 | 先做 10 天 P0 原型，再扩展 4–6 周试点版 |

如果这些假设变化，只调整排期和 Adapter，不改变核心领域模型。

## 6. 上下文补全清单

| # | 需要确认的上下文 | 为什么需要 | 当前状态 |
|---|---|---|---|
| 1 | 使用哪款 Coding 软件 | 决定仓库指令和自动化方式 | 不影响开始 |
| 2 | 开发者人数和技能 | 决定是否并行和排期 | 默认单人 |
| 3 | 模型供应商与预算 | 决定 VideoModel Adapter | 待确认 |
| 4 | 是否有 NVIDIA GPU | 决定本地检测/SAM 2 能力 | 待确认 |
| 5 | 是否允许上传真实灾害视频 | 涉及隐私、合规和数据处理 | 待确认 |
| 6 | 是否要求离线运行 | 影响模型和部署选择 | 默认联网模型 API |
| 7 | 地图数据来源 | 决定路线和坐标精度 | 默认模拟路网 |
| 8 | 是否仍有 10 天时间约束 | 决定 P0/P1 范围 | 暂按 10 天 P0 |

---

# 第二部分：信息与数据摸底

## 7. 已知信息

- 产品名称为 AI Disaster Commander；
- 核心能力包含多模态现场理解、动态世界模型、RDF、风险分析、救援规划和人工确认；
- 第一场景可以聚焦地震建筑坍塌；
- 页面视觉设计可以后置，但主交互和数据契约必须提前；
- 市场已有视频汇聚、GIS、灾害数字孪生和应急调度等相邻能力；
- 产品差异点是视频证据、动态语义状态、约束规划和纠错后重规划。

## 8. 限制条件

| 类型 | 约束 |
|---|---|
| 范围 | 只做一个灾害场景和一条完整链路 |
| 数据 | 初期没有大规模标注灾害视频 |
| 模型 | 不训练基础模型，依赖现成模型和规则 |
| 安全 | 不输出未经验证的生存率、坍塌概率或自动命令 |
| 工程 | 不能一开始拆成过多微服务 |
| 页面 | 视觉可后置，主流程和状态展示不可后置 |
| 规划 | 必须区分 LLM 解释与确定性约束求解 |
| 测试 | 真实模型调用不能成为 CI 的硬依赖 |

## 9. 数据摸底

### 9.1 当前数据状态

| 数据 | 当前值 | 需要补齐 |
|---|---:|---|
| 主演示视频 | 0–1 条 | 准备 1 条 30–90 秒视频 |
| 测试视频 | 0 条 | 准备 6–10 条短片 |
| 标注 Observation | 0 | 人工标注视频时间片和预期事件 |
| 建筑/道路地图 | 0 | 创建一个虚构现场 GeoJSON |
| 救援资源清单 | 0 | 创建 2 支队伍、1 架无人机、1 辆救护车 |
| 救援规则 | 0 | 先定义 5–8 条可解释规则 |
| 验收查询 | 0 | 准备 15 个固定问题和正确结果 |

### 9.2 第一批 Golden Dataset

建立 `fixtures/golden/earthquake_demo/`：

```text
video.mp4
scene.geojson
resources.json
expected_observations.json
expected_world_state.json
expected_risk_assessments.json
expected_plan.json
queries.json
```

至少包含以下事件：

- Building A 二层出现 3 名疑似被困人员；
- Building A 存在局部损坏线索；
- North Road 已阻断；
- East Route 初始可通行；
- Rescue Team 1 具备结构搜救能力；
- Drone 1 可执行现场复核；
- 人工确认 East Route 阻断后，原方案必须失效并生成 Plan B。

### 9.3 目标量化

| 目标 | 指标 | P0 目标 | 衡量方式 |
|---|---|---:|---|
| 完整闭环 | E2E 主流程通过率 | 100% | 自动 E2E + 人工演示 |
| 证据完整 | 关键观察带 evidence | 100% | Schema/SHACL 校验 |
| 数据质量 | RDF SHACL 通过率 | 100% | pySHACL |
| 查询正确 | 固定问题正确率 | ≥80% | Golden Query Tests |
| 规划安全 | 硬约束违反数 | 0 | Planner Validator |
| 重规划 | 纠错后新方案生成 | <2 秒，不含模型调用 | 性能测试 |
| 稳定性 | 连续完整运行 | 5 次成功 | 演示检查 |

---

# 第三部分：开发范围

## 10. P0 必须完成

- 创建事件并上传一个视频；
- 异步显示分析进度；
- 输出结构化 Observation；
- Observation 关联时间码和关键帧；
- 建立 RDF 世界状态；
- 展示人员、建筑、道路、资源关系；
- 运行 5–8 条风险/任务规则；
- 根据路线、能力和资源生成候选方案；
- 展示主方案、备选方案和原因；
- 人工确认/驳回 Observation；
- 世界状态更新并重新规划；
- 支持 10–15 个模板化自然语言问题；
- 前端完成视频、地图、状态和计划联动。

## 11. P1 延后

- SAM 2 精细分割与跨帧 mask；
- 多视频实体融合；
- 真实道路网络和导航服务；
- 文档向量检索与完整 GraphRAG；
- 实时无人机流；
- 用户、角色和多租户；
- CAP/HXL 导出；
- 云端对象存储；
- 移动端；
- 多灾种规则包。

## 12. 明确不做

- 自训练灾害基础模型；
- 自动控制无人机、机器人或救援队；
- 真实生存率或坍塌概率预测；
- 同时覆盖地震、洪水、火灾等多个完整场景；
- 开放式、无限循环的自主 Agent；
- 为每个业务模块建立独立微服务。

---

# 第四部分：系统架构

## 13. 架构原则

### 13.1 模块化单体

第一版采用一个 FastAPI 代码库和一个异步 Worker 进程。它们可以作为两个进程部署，但共享同一套领域模块。

```text
Web Browser
    ↓
Next.js Web
    ↓ HTTP/SSE
FastAPI Application
    ├── Incident Module
    ├── Media Analysis Module
    ├── World Model Module
    ├── Risk Module
    ├── Planning Module
    └── Query Module
         ↓
Worker Process
    ↓
External Model / FFmpeg / Fuseki / Redis / PostgreSQL
```

不要把 `World Model`、`Risk`、`Planning` 立即拆成网络服务。它们首先是同一代码库中的深 Module，通过小 Interface 隐藏内部复杂度。

### 13.2 真实需要的 Seam

只为确实会变化或测试需要替代的依赖建立 Seam：

| Seam | 生产 Adapter | 测试 Adapter |
|---|---|---|
| Vision Model | Gemini/OpenAI/Qwen Adapter | FixtureVisionAdapter |
| Graph Store | FusekiGraphStore | InMemoryGraphStore |
| Blob Store | LocalBlobStore，后续 S3 | TempBlobStore |
| Task Queue | RedisRQAdapter | InlineTaskAdapter |
| Clock | SystemClock | FixedClock |

路线规划、风险规则、实体对齐等业务逻辑先作为具体 Module，不提前增加无实际替换需求的抽象层。

### 13.3 深 Module 设计

#### MediaAnalysisModule

Interface：

```text
analyze(asset, incident_context) -> AnalysisResult
```

内部隐藏抽帧、提示词、模型调用、JSON 修复、实体候选和关键帧生成。

#### WorldModelModule

Interface：

```text
apply(incident_id, observations, decisions) -> WorldUpdate
snapshot(incident_id, version?) -> WorldSnapshot
```

内部隐藏 RDF 映射、命名图、SHACL、实体合并、版本和溯源。

#### PlanningModule

Interface：

```text
plan(world_snapshot, resources, objective) -> PlanSet
```

内部隐藏任务生成、路线过滤、优先级、OR-Tools、备选方案和约束校验。

#### QueryModule

Interface：

```text
answer(question, world_snapshot) -> GroundedAnswer
```

内部隐藏问题分类、槽位抽取、模板选择、SPARQL 查询和回答组织。

### 13.4 删除测试

如果删除某个 Module 后，复杂逻辑会散落到多个调用方，说明该 Module 有深度；如果删除后只是少一次函数转发，它就是浅 Module，应当合并。

---

## 14. 推荐技术栈

| 层 | 选择 | P0 说明 |
|---|---|---|
| Web | Next.js + TypeScript | 单页面 Command Center |
| UI | Tailwind CSS + shadcn/ui | 先使用组件库，不做品牌系统 |
| 视频 | 原生 video 或 video.js | 支持按秒跳转 |
| 地图 | MapLibre GL | 加载虚构 GeoJSON |
| 关系图 | React Flow | 只展示当前局部子图 |
| API | FastAPI + Pydantic | 契约和 OpenAPI |
| ORM | SQLAlchemy/SQLModel | 业务元数据 |
| 数据库 | PostgreSQL | 原型可先 SQLite，提交前切 PostgreSQL |
| 任务队列 | Redis + RQ | 视频异步分析 |
| 媒体 | FFmpeg + OpenCV | 转码、抽帧、关键帧 |
| 图谱 | RDFLib + Apache Jena Fuseki | RDF 写入和 SPARQL |
| RDF 校验 | pySHACL | 入图质量门 |
| 规划 | NetworkX + OR-Tools | 路线与资源分配 |
| 测试 | pytest + Vitest + Playwright | 单元、契约、E2E |
| 部署 | Docker Compose | Web/API/Worker/Redis/Postgres/Fuseki |

P0 不引入向量数据库。救援手册检索在核心闭环稳定后再加入。

---

## 15. 仓库结构

```text
ai-disaster-commander/
├── AGENTS.md
├── README.md
├── .env.example
├── docker-compose.yml
├── apps/
│   └── web/
│       ├── app/
│       ├── components/
│       ├── features/
│       │   ├── incident/
│       │   ├── video-timeline/
│       │   ├── situation-map/
│       │   ├── world-state/
│       │   └── rescue-plan/
│       └── lib/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── domain/
│   │   │   ├── incidents/
│   │   │   ├── observations/
│   │   │   ├── world_model/
│   │   │   ├── risk/
│   │   │   ├── planning/
│   │   │   └── queries/
│   │   ├── adapters/
│   │   │   ├── vision/
│   │   │   ├── graph_store/
│   │   │   ├── blob_store/
│   │   │   └── task_queue/
│   │   ├── worker/
│   │   └── infrastructure/
│   └── tests/
├── contracts/
│   ├── openapi.json
│   ├── observation.schema.json
│   ├── world-snapshot.schema.json
│   └── plan.schema.json
├── ontology/
│   ├── ontology.ttl
│   ├── shapes.ttl
│   ├── rules/
│   └── queries/
├── fixtures/
│   └── golden/earthquake_demo/
├── docs/
│   ├── architecture.md
│   ├── domain-model.md
│   ├── api.md
│   ├── safety.md
│   └── adr/
└── scripts/
    ├── seed_demo.*
    └── verify_demo.*
```

`api` 和 `worker` 是不同运行进程，不是不同领域 Module；不要复制业务逻辑。

---

# 第五部分：核心数据契约

## 16. 领域对象

### 16.1 Incident

```text
id
name
disaster_type
status
created_at
location_context
current_world_version
```

### 16.2 MediaAsset

```text
id
incident_id
type
uri
sha256
duration_seconds
captured_at
geometry
status
```

### 16.3 EvidenceSegment

```text
id
asset_id
start_second
end_second
keyframe_uri
bounding_boxes_or_masks
```

### 16.4 Observation

```text
id
incident_id
subject
predicate
object
evidence_ids[]
confidence
verification_status
source_model
created_at
```

`verification_status`：

```text
UNVERIFIED | CONFIRMED | REJECTED | CONFLICTED
```

### 16.5 HumanDecision

```text
id
observation_id
decision
correction_payload?
reason?
actor
created_at
```

禁止覆盖原始 Observation。人工修改必须创建 HumanDecision，从而保留审计轨迹。

### 16.6 WorldSnapshot

```text
incident_id
version
entities[]
relations[]
active_observation_ids[]
inferences[]
conflicts[]
generated_at
```

### 16.7 RescueResource

```text
id
type
capabilities[]
capacity
location
available_from
status
```

### 16.8 RescueTask

```text
id
target_entity_id
task_type
required_capabilities[]
priority_score
risk_level
estimated_duration
evidence_ids[]
```

### 16.9 Plan

```text
id
incident_id
world_version
status
steps[]
unassigned_tasks[]
assumptions[]
unknowns[]
constraint_report
created_at
```

关键不变量：

- 每个 Plan 必须绑定 `world_version`；
- WorldSnapshot 更新后，旧 Plan 标记为 `STALE`；
- 每个关键 Task 必须能够追溯到 Observation/Evidence；
- `REJECTED` Observation 不得参与当前推理；
- 规划器不得返回违反硬约束的 Plan；
- 产品不得自动把 Plan 发送给真实执行设备。

---

## 17. P0 API

```text
POST   /api/incidents
GET    /api/incidents/{incident_id}

POST   /api/incidents/{incident_id}/assets
POST   /api/incidents/{incident_id}/analyses
GET    /api/analyses/{analysis_id}
GET    /api/analyses/{analysis_id}/events       # SSE

GET    /api/incidents/{incident_id}/observations
POST   /api/observations/{observation_id}/decisions

GET    /api/incidents/{incident_id}/world-state
GET    /api/incidents/{incident_id}/world-state/{version}

POST   /api/incidents/{incident_id}/plans
GET    /api/plans/{plan_id}

POST   /api/incidents/{incident_id}/queries
```

所有创建型请求支持 `Idempotency-Key`。错误统一返回：

```json
{
  "code": "WORLD_STATE_VALIDATION_FAILED",
  "message": "Human-readable message",
  "details": {},
  "trace_id": "..."
}
```

---

# 第六部分：逐步开发任务

## 18. 阶段 0：项目基线与决策记录

| ID | 子任务 | 输出物 | 完成标准 | 验证方式 | 依赖 |
|---|---|---|---|---|---|
| D001 | 创建仓库和目录骨架 | 可启动仓库 | 目录符合第 15 节 | 检查目录 | 无 |
| D002 | 创建 README 与本地启动说明 | README.md | 新开发者能按步骤启动 | 在干净目录演练 | D001 |
| D003 | 创建环境变量模板 | `.env.example` | 不包含真实密钥 | Secret scan | D001 |
| D004 | 建立格式化、Lint 和测试命令 | 脚本/配置 | 前后端命令可运行 | CI 本地执行 | D001 |
| D005 | 写 4 个 ADR | `docs/adr/*` | 记录模块化单体、RDF、队列、模型 Adapter 决策 | 文档 Review | D001 |
| D006 | 创建 Golden Dataset 目录和占位数据 | fixtures | JSON 均通过 Schema | Fixture tests | D001 |

### 里程碑 M0

仓库结构稳定，任何 Coding Agent 都能知道项目范围、启动方式和禁止事项。

---

## 19. 阶段 1：Walking Skeleton

目标：不接真实 AI，先打通一个“丑但完整”的端到端流程。

| ID | 子任务 | 输出物 | 完成标准 | 验证方式 | 依赖 |
|---|---|---|---|---|---|
| D101 | 建立 Incident 和 Asset 数据表 | Migration + Model | 可创建事件和资产记录 | Repository tests | D004 |
| D102 | 实现创建事件 Interface | Incident Module | 能创建/读取 Incident | API test | D101 |
| D103 | 实现本地文件 Adapter | LocalBlobStore | 上传 MP4 并返回安全 URI | Integration test | D102 |
| D104 | 实现 InlineTaskAdapter | 同步任务 Adapter | 测试中可立即执行分析 | Unit test | D102 |
| D105 | 实现 FixtureVisionAdapter | 固定 Observation 输出 | 对主演示 asset 返回 fixture | Contract test | D006 |
| D106 | 实现最小分析流程 | Analysis job | 上传后生成 mock observations | API integration test | D103–D105 |
| D107 | 建立 Next.js 页面骨架 | Command Center | 四个区域可显示占位内容 | Playwright smoke test | D102 |
| D108 | 接入上传和任务状态 | Web flow | 页面能上传并看到完成状态 | E2E test | D106–D107 |
| D109 | 接入 Mock Observation 时间轴 | 视频时间轴 | 点击事件跳到指定秒数 | Playwright test | D108 |
| D110 | 接入 Mock 地图和计划卡 | Map + Plan | 页面显示地点、路线和方案 | Visual/manual check | D107 |

### 里程碑 M1

```text
上传视频 → Mock 分析 → Observation 时间轴 → 地图 → Mock Plan
```

此时页面无需好看，但完整流程必须可以点击运行。

---

## 20. 阶段 2：真实媒体处理与模型 Adapter

| ID | 子任务 | 输出物 | 完成标准 | 验证方式 | 依赖 |
|---|---|---|---|---|---|
| D201 | 实现媒体探测 | Media metadata | 获取时长、编码、尺寸和 hash | Fixture test | D103 |
| D202 | 实现安全转码 | normalized MP4 | 非标准视频可转为统一格式 | FFmpeg integration test | D201 |
| D203 | 实现抽帧 | Frame set | 按场景或固定间隔输出帧和时间码 | Unit/integration test | D202 |
| D204 | 实现关键帧保存 | Evidence files | 每个 Observation 可引用关键帧 | File assertion | D203 |
| D205 | 定义 VisionModel Interface | Port | 输入/输出和错误模式稳定 | Contract review | D105 |
| D206 | 实现真实 Vision Adapter | Model adapter | 返回合法 Observation JSON | Contract test | D205 |
| D207 | 实现结构化输出修复 | Parser | 非法响应被拒绝或有限修复 | Property tests | D206 |
| D208 | 实现超时、重试和限流 | Reliability policy | 可区分超时、配额和内容错误 | Fault injection | D206 |
| D209 | 实现 Redis/RQ Adapter | Async jobs | API 与 Worker 分离运行 | Integration test | D106 |
| D210 | 接入 SSE 进度 | Progress events | 页面展示 preprocessing/analyzing/finalizing | E2E test | D209 |
| D211 | 保存原始模型响应 | Audit artifact | 每次调用可复现和排查 | Storage test | D206 |
| D212 | 建立模型评估脚本 | Evaluation report | 可对 Golden Dataset 输出指标 | Run report | D206 |

### 里程碑 M2

真实视频可以稳定生成符合 Schema 的 Observation，并且每条 Observation 至少有时间范围、证据帧、置信度和模型版本。

---

## 21. 阶段 3：RDF 动态世界模型

| ID | 子任务 | 输出物 | 完成标准 | 验证方式 | 依赖 |
|---|---|---|---|---|---|
| D301 | 定义最小 ontology | `ontology.ttl` | 覆盖人员、建筑、道路、危险、资源、任务和证据 | Ontology test | D006 |
| D302 | 定义 SHACL shapes | `shapes.ttl` | 缺来源、时间或状态的数据被拒绝 | pySHACL tests | D301 |
| D303 | 实现 Observation→RDF 映射 | Mapper | 固定 JSON 生成稳定 triples | Snapshot test | D301 |
| D304 | 实现 InMemoryGraphStore | Test adapter | 测试可读写命名图 | Unit test | D303 |
| D305 | 实现 FusekiGraphStore | Production adapter | 支持 query/update/transaction | Container test | D304 |
| D306 | 实现实体对齐 P0 | Grounding logic | 同一 track/location 不重复建实体 | Golden test | D303 |
| D307 | 实现命名图策略 | Named graphs | 区分模型、人工、推理和计划 | SPARQL assertions | D305 |
| D308 | 实现 WorldSnapshot | Snapshot builder | 可输出当前实体、关系、冲突和版本 | Interface test | D306–D307 |
| D309 | 实现 HumanDecision | Decision event | 确认/驳回不覆盖原始观察 | Audit test | D308 |
| D310 | 实现世界状态版本 | Versioning | 每次有效变化生成新 version | Version tests | D309 |
| D311 | 标记旧计划过期 | Plan staleness | world version 改变后旧计划为 STALE | Integration test | D310 |
| D312 | 实现局部图 API | Graph projection | 前端只获取当前问题相关子图 | API test | D308 |
| D313 | 前端接入真实 WorldSnapshot | World panel | Observation/实体/关系可联动 | E2E test | D312 |
| D314 | 实现历史版本回看 | Version selector | 能查看至少上一版本状态 | E2E test | D310 |

### 里程碑 M3

```text
真实 Observation
→ SHACL 校验
→ RDF 命名图
→ 当前 WorldSnapshot
→ 人工确认/驳回
→ 新 World Version
```

---

## 22. 阶段 4：风险规则、任务生成与规划器

| ID | 子任务 | 输出物 | 完成标准 | 验证方式 | 依赖 |
|---|---|---|---|---|---|
| D401 | 定义 5–8 条风险规则 | Versioned rules | 每条规则有输入、输出和说明 | Rule review | D308 |
| D402 | 实现 Risk Module | Assessments | 输出风险、依据、未知项 | Golden tests | D401 |
| D403 | 将推断写回命名图 | Inference graph | 每条推断引用规则与证据 | SPARQL test | D402 |
| D404 | 实现任务生成 | RescueTask list | 从状态生成搜救/核实/清障任务 | Unit test | D402 |
| D405 | 定义虚构路网 | GeoJSON/graph | 包含两条可替代路线和阻断边 | Fixture test | D006 |
| D406 | 实现可达性计算 | Route result | 排除阻断边并返回路径/不可达 | Unit test | D405 |
| D407 | 定义资源能力匹配 | Capability rules | 不具备能力的分配被拒绝 | Unit test | D404 |
| D408 | 实现 OR-Tools 分配 | Planner | 输出主方案和未分配任务 | Golden plan test | D406–D407 |
| D409 | 实现硬约束校验 | Constraint report | 任何违规方案被拒绝 | Mutation/property tests | D408 |
| D410 | 生成备选方案 | PlanSet | 至少返回一个有效备选或说明不存在 | Scenario tests | D408 |
| D411 | 绑定 world version | Plan metadata | Plan 与当前 WorldSnapshot 一致 | Integration test | D408 |
| D412 | 实现 Planning API | Plan endpoints | 能创建和读取 PlanSet | API test | D411 |
| D413 | 前端展示方案解释 | Plan panel | 显示步骤、证据、假设、未知和约束 | E2E test | D412 |
| D414 | 实现纠错后重规划 | Replan flow | 修改 East Route 后切换到 Plan B | Golden E2E | D309 + D412 |

### 里程碑 M4

这是核心产品闭环：

```text
世界状态 V1 → Plan A
→ 人工确认 East Route 阻断
→ 世界状态 V2
→ Plan A 过期
→ Plan B
→ 展示变化原因
```

---

## 23. 阶段 5：查询与 Commander Agent

| ID | 子任务 | 输出物 | 完成标准 | 验证方式 | 依赖 |
|---|---|---|---|---|---|
| D501 | 定义问题类型 | Query intents | 事实、原因、附近资源、变化、未知五类 | Classification tests | D308 |
| D502 | 定义 SPARQL 模板 | Query files | 模板均为白名单和参数化 | Security review | D501 |
| D503 | 实现槽位抽取 | Parsed query | 提取实体、范围、时间和状态 | Golden tests | D501 |
| D504 | 实现 Query Module | GroundedAnswer | 返回事实、路径和 evidence IDs | Interface tests | D502–D503 |
| D505 | 实现回答组织 | Explanation | 区分已知、推断、未知 | Snapshot tests | D504 |
| D506 | 建立 Agent 状态机 | Orchestrator | 只能走允许状态，禁止无限循环 | State tests | D504 + D412 |
| D507 | 注册只读工具 | Tool registry | Agent 能查询状态/证据/计划 | Tool tests | D506 |
| D508 | 注册规划工具 | Plan tools | 规划结果必须再过 validator | Integration test | D506 |
| D509 | 实现人工审批节点 | Approval state | 高风险方案只展示不执行 | E2E test | D506 |
| D510 | 实现查询页面 | Query UI | 回答可点击回到视频和图谱 | Playwright test | D505 |
| D511 | 建立 15 个问题评估集 | Query fixtures | 每个问题有预期实体和证据 | Evaluation run | D504 |
| D512 | 防提示注入 | Input policy | 视频 OCR/文档内容不能改变系统工具权限 | Adversarial tests | D506 |

### 里程碑 M5

用户能够用自然语言查询世界状态，但所有事实必须来自模板化图查询；语言模型只负责理解与解释。

---

## 24. 阶段 6：页面联动与体验完善

| ID | 子任务 | 输出物 | 完成标准 | 验证方式 | 依赖 |
|---|---|---|---|---|---|
| D601 | 完成四区布局 | Command Center | 视频、地图、状态、计划同屏 | Visual review | D313 + D413 |
| D602 | 实现事件时间轴 | Timeline | 状态和视频播放位置同步 | Playwright test | D109 |
| D603 | 实现地图实体选择 | Map interaction | 点击地点更新其他面板 | E2E test | D601 |
| D604 | 实现局部关系图 | Graph view | 只展示选择对象相关节点 | E2E test | D312 |
| D605 | 实现证据回跳 | Evidence interaction | 点击理由跳转视频时间码 | E2E test | D413 |
| D606 | 实现已知/推断/未知样式 | Visual language | 三类状态可清晰区分 | User review | D601 |
| D607 | 实现纠错对话框 | Decision UI | 确认、驳回和修正均可提交 | E2E test | D309 |
| D608 | 实现方案变化对比 | Plan diff | 展示 V1 与 V2 差异和原因 | E2E test | D414 |
| D609 | 完成加载/空/错误状态 | State UX | 所有异步状态有明确反馈 | UI state tests | D210 |
| D610 | 增加演示模式 | Demo preset | 一键加载 Golden Dataset | Manual/E2E | D006 |
| D611 | 统一视觉设计 | Theme | 信息层级清晰，不遮盖证据 | Visual review | D601–D610 |
| D612 | 键盘与基础无障碍 | Accessibility | 核心操作可键盘访问 | axe/Playwright | D611 |

页面视觉设计在 D611 才集中完成，但页面骨架和联动从 D107 开始存在。

---

## 25. 阶段 7：质量、安全和交付

| ID | 子任务 | 输出物 | 完成标准 | 验证方式 | 依赖 |
|---|---|---|---|---|---|
| D701 | 完善单元测试 | Unit suite | 领域规则和规划关键路径覆盖 | Coverage + review | 各阶段 |
| D702 | 完善契约测试 | Contract suite | Fixture/真实 Adapter 输出一致 | Contract run | D206 |
| D703 | 完善容器集成测试 | Integration suite | Postgres/Redis/Fuseki 正常协同 | CI containers | D305/D209 |
| D704 | 完善 E2E 主流程 | Playwright suite | Golden 主流程自动通过 | CI | D610 |
| D705 | 加入文件安全限制 | Upload policy | 类型、大小、时长和路径安全 | Security tests | D103 |
| D706 | 加入鉴权占位 | Auth seam | 原型默认本地用户，接口可扩展鉴权 | API review | D102 |
| D707 | 加入日志与 trace id | Structured logs | 一个任务可端到端追踪 | Log assertion | D209 |
| D708 | 加入幂等 | Idempotency | 重复提交不重复入图 | Integration test | D303 |
| D709 | 加入备份与数据清理脚本 | Ops scripts | 可以导出/清理单个 Incident | Dry run | D305 |
| D710 | 性能基准 | Benchmark report | 记录视频处理和重规划延迟 | Benchmark | D414 |
| D711 | 故障降级 | Fallback behavior | 模型/Fuseki 暂不可用时有明确状态 | Fault tests | D208/D305 |
| D712 | 创建安全说明 | `docs/safety.md` | 明确能力边界和禁止用途 | Review | D512 |
| D713 | 创建部署和演示指南 | Docs | 新环境可启动并加载示例 | Clean setup | D610 |
| D714 | 发布原型版本 | Version tag/artifact | 所有 P0 检查通过 | Release checklist | D701–D713 |

### 里程碑 M6

系统可以在干净环境部署，Golden Demo 连续运行五次，关键结果可追溯，硬约束无违规。

---

# 第七部分：关键路径与排期

## 26. 关键路径

```text
数据契约
→ Walking Skeleton
→ 真实 Observation
→ RDF WorldSnapshot
→ Risk/Task
→ Planner
→ HumanDecision/Replan
→ Query Agent
→ UI Polish
→ Hardening
```

以下任务可以并行：

- Golden Dataset 与仓库骨架；
- 前端 Mock 页面与后端领域契约；
- Ontology 与媒体处理；
- UI 视觉优化与质量文档；
- 模型评估与规划器单元测试。

## 27. 10 天 P0 排期

| 天 | 目标 | 任务 |
|---|---|---|
| Day 1 | 范围、契约、仓库 | D001–D006 |
| Day 2 | Walking Skeleton 后端 | D101–D106 |
| Day 3 | Mock 页面闭环 | D107–D110 |
| Day 4 | 媒体与真实模型 | D201–D208 |
| Day 5 | 队列、进度、模型评估 | D209–D212 |
| Day 6 | RDF 世界模型 | D301–D310，历史回看可后置 |
| Day 7 | 风险、任务和路线 | D401–D407 |
| Day 8 | 规划、纠错与重规划 | D408–D414 |
| Day 9 | 查询与页面联动 | D501–D510，先不做复杂 Agent |
| Day 10 | 测试、视觉和打包 | D601–D611 + P0 质量任务 |

十天内优先砍掉：SAM 2、历史回放、多视频、完整 GraphRAG、真实路网和复杂登录。

## 28. 4–6 周试点扩展

- Week 1–2：完成 P0 并建立真实评估数据；
- Week 3：加入多视频实体对齐和更稳定的感知；
- Week 4：接入真实 GIS/路网和组织资源台账；
- Week 5：权限、审计、离线/弱网和部署加固；
- Week 6：与目标用户完成桌面演练和迭代。

---

# 第八部分：Coding Agent 提示词包

## 29. 每次任务的通用前缀

将下面这段放在每个具体任务前面：

```text
你正在实现 AI Disaster Commander。请先阅读仓库中的 AGENTS.md、README.md、
docs/architecture.md 和与本任务相关的契约。

只实现本次指定任务，不扩大范围，不重构无关代码，不修改已有用户变更。
优先复用现有 Module 和 Interface；不要创建没有第二个 Adapter 的假设性抽象层。
所有外部模型输出都必须经过 Schema 校验。
所有规划结果都必须经过硬约束校验。
新增行为必须有测试，并运行与本任务相关的格式化、静态检查和测试。

完成后报告：
1. 修改了什么；
2. 为什么这样设计；
3. 运行了哪些验证；
4. 仍有哪些限制或风险；
5. 不要自动开始下一个阶段。
```

## 30. Prompt 1：仓库骨架

```text
执行任务 D001–D006：创建项目骨架、README、环境变量模板、开发命令、ADR 和
Golden Dataset 占位文件。不要实现业务功能。确保仓库中没有真实密钥，所有 JSON
fixture 有最小 Schema 并可被测试读取。
```

## 31. Prompt 2：Walking Skeleton

```text
执行任务 D101–D110。使用 FixtureVisionAdapter 和 InlineTaskAdapter 打通：
创建 Incident、上传视频、生成固定 Observation、在单个 Command Center 页面显示
视频时间轴、模拟地图和模拟 Plan。此阶段禁止接入真实模型、Fuseki 和 OR-Tools。
添加一条 Playwright 主流程测试。
```

## 32. Prompt 3：媒体处理

```text
执行任务 D201–D204。实现安全的视频探测、统一转码、抽帧和关键帧生成。
所有命令参数必须通过安全参数列表传递，不拼接 Shell 字符串。输出包含精确时间码，
并为异常编码、空视频、超大文件和 FFmpeg 失败添加测试。
```

## 33. Prompt 4：真实模型 Adapter

```text
执行任务 D205–D212。定义稳定的 VisionModel Interface，并实现一个真实 Adapter 和
FixtureVisionAdapter。真实 Adapter 必须返回 Observation Schema；对超时、配额、
非法 JSON 和内容拒绝进行分类。CI 只使用 Fixture Adapter，不调用付费模型。
```

## 34. Prompt 5：RDF 世界模型

```text
执行任务 D301–D312。实现最小 ontology、SHACL、Observation 到 RDF 映射、
InMemoryGraphStore、FusekiGraphStore、命名图、实体对齐、WorldSnapshot、HumanDecision
和版本管理。通过 WorldModelModule 的 Interface 测试行为，不让调用方接触 RDFLib
内部对象或拼接任意 SPARQL。
```

## 35. Prompt 6：规划器

```text
执行任务 D401–D414。实现版本化风险规则、任务生成、简化路网、能力匹配、OR-Tools
分配、备选方案和硬约束校验。使用 Golden Dataset 验证：East Route 可通行时输出
Plan A；人工确认其阻断后 Plan A 变为 STALE，并生成合法 Plan B。
```

## 36. Prompt 7：查询 Agent

```text
执行任务 D501–D512。实现五类问题、参数化 SPARQL 模板、槽位抽取、GroundedAnswer
和受控状态机。禁止模型执行任意 SPARQL，禁止从视频 OCR 或检索文档中接受工具权限
指令。所有回答必须标记事实、推断、未知并返回 evidence IDs。
```

## 37. Prompt 8：页面联动

```text
执行任务 D601–D610。完成视频、事件时间轴、地图、局部关系图和 Plan 面板的联动。
点击 Observation 或 Plan 理由必须跳到证据时间码；提交 HumanDecision 后必须显示旧
Plan 失效和新 Plan 的差异。暂时不做品牌级视觉重构。
```

## 38. Prompt 9：质量和交付

```text
执行任务 D701–D714。补齐领域、契约、容器集成和 E2E 测试，加入上传安全、幂等、
trace id、故障降级、部署说明和安全说明。在干净环境运行完整验证，并生成一份发布
检查报告。不要通过跳过测试、固定生产结果或隐藏错误来获得绿色状态。
```

---

# 第九部分：测试策略

## 39. 测试金字塔

### 39.1 领域测试

不依赖网络或容器，覆盖：

- Observation 校验；
- 时间窗口合并；
- 实体去重；
- 人工决策应用；
- 风险规则；
- 路线过滤；
- 能力匹配；
- 计划约束。

### 39.2 Adapter 契约测试

所有 Vision Adapter 必须通过同一组测试：

- 返回合法 Observation；
- 保留 evidence 时间码；
- 失败被映射为统一错误；
- 不泄露供应商原始对象给领域调用方。

GraphStore Adapter 同样通过统一行为测试。

### 39.3 容器集成测试

在 CI 中启动 PostgreSQL、Redis 和 Fuseki，验证：

- Migration；
- 队列任务；
- RDF 写入和查询；
- 幂等；
- 事务失败恢复。

### 39.4 E2E

至少覆盖：

1. 上传 Golden 视频；
2. 等待 Mock 分析完成；
3. 点击 Observation 跳转视频；
4. 查看 Plan A；
5. 确认道路阻断；
6. 看到 Plan A 失效；
7. 查看 Plan B；
8. 查询“为什么方案发生变化”；
9. 回答指向正确 evidence。

真实模型评估独立运行，不放入每次 CI。

---

# 第十部分：风险预判

## 40. 风险表

| # | 风险 | 影响 | 概率 | 预防措施 |
|---|---|---|---|---|
| R1 | 模型输出不稳定 | 高 | 高 | Schema、Fixture Adapter、重试和人工确认 |
| R2 | 视频与地图没有真实地理关系 | 高 | 高 | P0 使用明确的人工位置和虚构 GeoJSON |
| R3 | RDF 范围过大 | 高 | 中 | 只做最小 ontology 和固定查询 |
| R4 | OR-Tools 模型过度复杂 | 高 | 中 | 先解决 2 队伍/3 任务的小问题 |
| R5 | 页面最后才联调 | 高 | 高 | Day 2–3 建立 Walking Skeleton |
| R6 | Agent 产生危险建议 | 高 | 中 | 模板查询、硬约束、人工审批、无自动执行 |
| R7 | Coding Agent 过度重构 | 中 | 高 | 每次只给一个任务编号，保护无关变更 |
| R8 | 外部 API 不可用 | 高 | 中 | Fixture 数据、缓存结果和清晰降级 |
| R9 | 真实视频含隐私信息 | 高 | 中 | 使用公开/合成数据，限制保存和访问 |
| R10 | 过早追求视觉效果 | 中 | 高 | 视觉统一放到 D611，先完成闭环 |
| R11 | 误把语义描述当事实 | 高 | 高 | 已知/推断/未知分层和证据要求 |
| R12 | 计划引用旧状态 | 高 | 中 | Plan 强制绑定 world version |

## 41. 需提前拍板

- [ ] 第一款真实多模态模型和预算上限；
- [ ] 开发机器是否有可用 GPU；
- [ ] 主演示视频的版权和隐私是否允许；
- [ ] 第一版使用 SQLite 还是直接 PostgreSQL；
- [ ] 是否要求完全离线运行；
- [ ] 是否仍以 10 天为第一版时间限制；
- [ ] 是否需要中文和英文双语界面；
- [ ] 是否有应急领域人员可以审阅规则。

这些问题不阻塞 D001–D110，但必须在接入真实模型和规划规则前确认。

---

# 第十一部分：最终验收清单

## 42. 功能验收

- [ ] 可以创建 Incident 并上传视频；
- [ ] 可以看到异步处理进度；
- [ ] Observation 能跳转到正确视频时间片；
- [ ] 世界状态包含人员、建筑、道路和资源关系；
- [ ] 所有当前事实通过 SHACL；
- [ ] 可以生成合法 Plan A 和备选方案；
- [ ] 可以确认、驳回或修正 Observation；
- [ ] World Version 更新后旧计划自动过期；
- [ ] 可以生成 Plan B 并解释变化原因；
- [ ] 固定自然语言问题可以返回证据化回答。

## 43. 数据验收

- [ ] 每个关键 Observation 有来源、时间和证据；
- [ ] 原始模型响应被保留；
- [ ] 人工修改不覆盖原始 Observation；
- [ ] 所有推断指向规则版本和上游证据；
- [ ] Plan 绑定 World Version；
- [ ] 重复请求不生成重复实体或 triples。

## 44. 安全验收

- [ ] 文件类型、大小和时长有限制；
- [ ] FFmpeg 调用不拼接不可信 Shell 字符串；
- [ ] 密钥不进入仓库或日志；
- [ ] SPARQL 使用白名单模板和参数；
- [ ] 检索内容不能改变 Agent 权限；
- [ ] 高风险方案必须等待人工批准；
- [ ] 产品明确标注为辅助决策原型。

## 45. 性能与稳定性验收

- [ ] 纠错后重规划小于 2 秒；
- [ ] 查询响应在本地数据集上可接受；
- [ ] 连续运行 Golden Demo 五次成功；
- [ ] 模型超时后用户能看到失败原因并重试；
- [ ] Fuseki/Redis 临时不可用不会造成无提示的数据损坏；
- [ ] 干净环境可以按照 README 启动。

## 46. 用户验收

- [ ] 新用户在 1 分钟内理解四个主区域；
- [ ] 用户能找到建议对应的视频证据；
- [ ] 用户能理解“已知、推断、未知”的区别；
- [ ] 用户能完成一次确认和一次驳回；
- [ ] 用户能说出 Plan 改变的原因；
- [ ] 页面没有暗示系统已经自动下达真实行动命令。

---

# 第十二部分：第一步应该做什么

现在不要先接真实模型，也不要先设计精美页面。

第一轮只执行：

```text
D001–D006：项目基线
D101–D110：Walking Skeleton
```

第一轮结束时，你必须已经拥有一个可点击的产品雏形：

```text
上传一段视频
→ 固定 Mock Observation
→ 视频时间轴
→ 模拟灾害地图
→ 模拟救援方案
```

只要这个纵向闭环成立，后续所有真实能力都可以逐层替换 Mock；如果这条链路没有成立，继续增加模型、RDF 或规划功能只会扩大联调风险。

---

## 技术参考

- [FastAPI](https://fastapi.tiangolo.com/)
- [Next.js](https://nextjs.org/docs)
- [MapLibre GL JS](https://maplibre.org/maplibre-gl-js/docs/)
- [React Flow](https://reactflow.dev/)
- [Apache Jena Fuseki](https://jena.apache.org/documentation/fuseki2/)
- [RDFLib](https://rdflib.readthedocs.io/)
- [SHACL](https://www.w3.org/TR/shacl/)
- [GeoSPARQL](https://www.ogc.org/standards/geosparql/)
- [Google OR-Tools](https://developers.google.com/optimization)
- [SAM 2](https://ai.meta.com/research/sam2/)
