# 旧版救援规划说明（暂缓扩展）

当前版本是可运行的演练后端基础（0.1.0），不是完整的多模态救援系统。只用于模拟案例和路演，不用于现场派遣。技术栈：Python、FastAPI、SQLite、RDFLib、OR-Tools。

## 安装、启动与验证

已验证环境：Windows x64 / Python 3.14。其他系统尚未验证；部署前须重新运行测试。以下命令在项目根目录执行：

```powershell
py -3.14 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动后访问 http://127.0.0.1:8000/docs 交互调用接口；OpenAPI 契约在 /openapi.json。服务默认不启动后台进程。可用 DISASTER_DB_PATH 环境变量调整数据库位置，默认 data/disaster.db。无外部服务、无密钥也能运行。

## 前端对接顺序

1. POST /scenarios：提交 examples/scenario.json 内容，取得场景 id。
2. GET /scenarios/{id}：取得不可变输入快照。
3. GET /scenarios/{id}/graph：取得 Turtle 格式 RDF。
4. POST /scenarios/{id}/plans：生成三种策略方案，取得方案 id、分配、评分、依据、未分配原因和假设。
5. GET /plans/{id}：取得方案及人工决定。
6. POST /plans/{id}/decision：提交 reviewer、action（approve 或 reject）、note。只能决定一次，重复返回 409。确认只记录意见，不会派遣资源。

输入非法返回 422，资源不存在返回 404，求解未成功返回 503。方案与场景使用 UUID。当前响应契约由 OpenAPI 提供，后续应在前端联调前补充完整响应类型。

## 模型边界与可解释性

每个救援点必须链接证据。证据包括来源、带时区的时间、置信度和类型：observation（观察）、human_input（人工输入）、exercise_assumption（演练假设）。当前证据是点级关联，不是每个属性分别溯源；队伍和全局资源由场景输入给定。置信度仅展示，不用于约束放宽。

每队本轮最多一个任务，每点最多一队。技能满足、道路可达、风险不超阈值、旅行加工作时间不超过窗口、全局装备不超库存均为硬约束。装备在整轮中独占，不模拟任务先后和回收。旅行时间为每个点统一输入，尚未区分队伍出发地或道路网络。

三种策略均最大化公开评分：urgency 为人数乘紧急度；coverage 为覆盖人数；lower_risk 为人数乘 (6 - 风险)。这些只是演示权重，不是专业救援评分；lower_risk 不保证总风险最小。不同策略可能得到相同分配。只在求解器返回 OPTIMAL 时说明已证明最优，FEASIBLE 只表示找到可行解。覆盖人数不是获救人数。未分配解释是约束检查或资源竞争说明，不是完整反事实分析。

示例中 A、B、C 分别在三个目标下得分最高，D 因不可达且风险超限被排除。当前所有示例数据均为虚构，尚未使用真实画面。

SQLite 的 JSON 快照是当前唯一数据源，RDF 是按快照导出的语义视图，求解器直接读取同一快照。尚无 RDF 推理、空间网络、增量事件合并或动态世界模型。纠错时新建场景，再生成方案，旧场景及决定保持不变；当前没有版本链或“最新场景”判定。

## 维护约定

- app/models.py 定义输入契约；planner.py 定义约束与目标；store.py 负责持久化；graph.py 负责 RDF 映射；main.py 负责 HTTP。
- requirements.txt 记录直接依赖范围，requirements.lock.txt 固定本次验证的全部依赖。升级时在新虚拟环境安装、测试，再刷新锁文件。
- 修改数据结构须考虑历史 JSON 的读取兼容；SQLite user_version 当前为 1，未来改表须实现显式迁移，不能仅覆盖版本号。
- 测试覆盖策略差异、资源互斥、全部不可达、风险/技能/时间排除、输入校验、RDF 解析、决定冲突及重启持久化。
- 当前锁定版本的 Starlette 测试客户端使用 httpx 时会提示弃用警告，测试仍通过；升级测试工具时需处理此兼容性提醒。
- 数据库备份在停止服务后复制 data/disaster.db；本版本尚无在线备份或恢复自动化。
- 当前仅支持本机单用户演示，无鉴权、角色、跨域配置或请求限流。reviewer 是自报名称，不是已验证身份。网络共享部署前需要补齐访问控制；本地前端优先通过开发代理访问后端。

## 后续开发顺序

1. 核实模型网关的官方接口说明、可用模型和图片输入；接入图片观察提取并保留原始输出，人工确认后形成规划输入。模型不得自行编造不可见的人数、风险等级或道路可达性。
2. 取得 AnySearch 文档再接检索，只把结果作为资料来源，不直接当作现场事实。
3. 核实星云 3D SDK 的能力与前后端职责，明确实际用途后再接入。
4. 根据真实素材和前端需求扩展属性级证据、场景版本链、空间关系及 RDF 推理。

不保存聊天中的 API 密钥，也不调用付费接口。接入时使用已轮换的新密钥，通过环境变量或部署密钥管理服务注入。不要提交密钥、现场个人信息或数据库到仓库。
