# 三维配准、路网和可追溯关系推理

接口位于 /spatial。输入模型在 OpenAPI 中可查看，完整请求样例见 examples/spatial_extensions.json。示例坐标、物体、路网和关系均为合成演练数据。

~~~powershell
.venv/Scripts/python.exe -m examples.demo_advanced
~~~

该演示使用临时数据库和团队账号，运行后清理；展示角色分工、260 米绕行、三维坐标转换、四种条件联合推理和路网撤回。不会调用外部模型。

## 空间工件的审核

| 接口 | 用途 |
| --- | --- |
| POST /datasets/{id}/networks | 提交不可变路网快照 |
| POST /datasets/{id}/registrations | 计算配准，合格后保存为待审核工件 |
| POST /datasets/{id}/relations | 提交带来源的关系集合 |
| GET /datasets/{id}/artifacts | 分页列出工件和审核状态 |
| GET /artifacts/{id} | 读取原始输入、计算结果、审核与撤回记录 |
| POST /artifacts/{id}/review | action=approve/reject，必须有 note |
| POST /artifacts/{id}/withdraw | 撤回批准，需要 note；重复操作 409 |

三类工件均带 source_note、valid_from、valid_until。正式检索需要当前批准、未撤回且 as_of 在有效时间内。修正需提交新快照，原快照可撤回；系统不会猜测哪个版本取代哪个版本，结构化查询显式指定工件 ID。自然语言存在多个无法区分的候选快照时要求澄清。所有审批身份来自团队账号。

关联 annotation_ids 必须属于同一数据集。待审、拒绝、撤回和未来图片证据会使依赖它的关系或道路失去可用支持。/reason 还按 max_age_hours 排除过旧图片；/route 的有效期以路网快照为准，不附加图片年龄窗口。工件本身可以基于人工测绘、现场调查提交，不强制每条关系都附照片，来源及审核人始终可追溯。

## 三维配准

POST /datasets/{id}/registrations 接受场景坐标到局部 ENU（东、北、上，单位米）的成对控制点。origin 使用 WGS84 经纬度，origin_altitude_m 使用椭球高，不是海拔正高。

- 至少 3 个不共线控制点，以及至少 1 个不重复的独立检查点。检查点不参与求解。
- scene_unit_m 声明原场景单位。默认估计刚体旋转和平移；solve_scale=true 时额外估计统一尺度，禁止反射。
- NumPy SVD 求解并返回 4×4 变换矩阵、控制点残差、检查点残差和 RMSE。共线、病态控制点、拟合或检查误差超过阈值返回 422，不保存合格工件。
- objects 把场景中已定位对象的三维包围盒与地图 entity_id 关联。8 个角点全部变换后计算垂直范围。原始坐标、关联和变换仍需审核。
- POST /registrations/{id}/transform 把 points 转成 ENU 和 WGS84 经纬度/椭球高，返回工件引用及检查误差。局部范围限制为原点 10 km 内；单次最多 10,000 点。
- 转换不会自动覆盖地图坐标。阈值和低 RMSE 不构成实地精度证明；控制点应来自可靠测绘。该功能是控制点配准，不包含自动点云对应、ICP、摄影测量重建、相机标定或 GLB/PLY/OBJ 文件解析。

## 道路网络

路网节点引用已有地图实体。每条边包含 id、source、target、length_m、bidirectional、modes、status 和 source_note。长度由测绘/道路数据提供；已知端点坐标时不能小于球面直线距离（允许 0.1 米计算容差）。

POST /datasets/{id}/route：

~~~json
{
  "network_id": "替换为已审核路网 UUID",
  "start_entity_id": "building-a",
  "end_entity_id": "entrance-far",
  "mode": "walk",
  "avoid_edge_ids": []
}
~~~

采用 Dijkstra，处理单向边、步行/车辆权限、用户指定避让以及 blocked/unknown 状态。返回完整节点/边序列、道路长度总和、排除边及原因和审核来源。没有路径返回 unreachable，不退回直线距离。起终点相同返回 0 米。

只有明确人工批准为 open 的边可用；图片“未见障碍物”不能单独把 unknown 改为 open。明确关联的有效图片记录若可见障碍物，也会排除该边。没有关联的图片不会自动关闭道路；应补上关联或提交新的道路快照。没有自动拉取 OSM、导航服务或实时交通，路网必须作为输入提供。结果是快照连通性，不是安全通行保证。

## 复杂关系

POST /datasets/{id}/reason 接受 all_of 条件数组，对同一个对象进行联合筛选：

~~~json
{
  "kind": "entrance",
  "relation_set_id": "替换为关系工件 UUID",
  "registration_id": "替换为配准工件 UUID",
  "network_id": "替换为路网工件 UUID",
  "all_of": [
    {"relation": "near", "reference_entity_id": "building-a", "distance_m": 100},
    {"relation": "part_of", "reference_entity_id": "building-a"},
    {"relation": "above", "reference_entity_id": "building-a"},
    {"relation": "reachable_from", "reference_entity_id": "building-a"}
  ]
}
~~~

- near、north_of、south_of、east_of、west_of 根据地图点位计算；经度差处理跨日期变更线。缺少坐标时列入 unknown_entities。方向只表示纬度/最短经差方向，不是相机视角左右。
- inside、part_of 按各自有向边做多跳；connects_to 对称并可多跳；blocks 仅沿声明方向、不传递。默认最多 8 跳，上限 20。包含与组成关系存在环时拒绝导入；不同谓词不擅自合成新事实。
- above、below 比较配准后物体的整个垂直范围，要求间隙超过 2×max_error_m；不表示水平投影重叠，也不表示“正上方”。
- reachable_from 使用已审核路网。可附 observation 与 max_age_hours，要求同一对象存在相应的近期已审核图片记录。
- matches 返回每个条件的计算或关系路径、工件引用和相关图片证据；无匹配为 insufficient_evidence。缺少必要工件 ID 返回 422，工件未批准或过期返回 409，不能将其当成“事实不存在”。

自然语言入口 POST /datasets/{id}/reason/ask，body 为 question。模型只解析上述受校验的条件，后端运行相同确定性推理；run_id 可追溯解析过程。常见显式方位、可达、组成和数值距离条件漏解析时返回 clarification_needed；必要工件缺失或失效时也要求澄清。关键词检查不是完整语义验证，回答和 interpreted_conditions 会列出实际执行的条件。原 /ask 继续服务“附近已审核图片观察”问题。两者都不支持任意空间逻辑、任意多边形相交、概率融合、冲突消解或开放世界规划。
