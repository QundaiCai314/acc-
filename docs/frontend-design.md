# 指挥台设计对照

本次改版以用户提供的产品布局及交互为参考，使用本项目数据和自行实现的界面，没有复制产品商标、截图或商业代码。

视觉层级以地图为主：深灰中性表面、少量青色强调、琥珀待审与红色封闭状态。顶部工具与筛选浮于地图；左侧对象树单独滚动，检索操作固定在底部；右侧对象标题、原图、审核依据和问答输入分层。审核画布、缩略图和属性编辑器保留清晰工作区，其他页面统一标题、留白和表单样式。布局、文字对比度和实际截图分别验证。

| 参考 | 对应实现 | 检查方式 |
| --- | --- | --- |
| [Palantir Gotham](https://www.palantir.com/platforms/gotham/) | 紧凑实体树 + 地图 + 情报抽屉；关系图与地图同屏 | 现场态势选择对象、打开关系图；查看审核关系链高亮 |
| [Anduril Lattice C2](https://www.anduril.com/lattice/command-and-control) | 全局状态、悬浮图例、红/琥珀/青语义；道路虚线及方向箭头 | 路网页比较步行/车辆；封闭与未知使用文字及线型区分 |
| [Felt](https://felt.com/platform/web-gis) | 浮动工具条、图层开关、筛选胶囊、地图缓冲圈 | 改半径或开关对象/路网/相机图层 |
| [Kepler.gl](https://github.com/keplergl/kepler.gl) | 采集分布直方图、双端时间窗、播放 | 拖动两端，观察相机和观察数量变化 |
| [PIX4Dcloud](https://www.pix4d.com/product/pix4dcloud) | 2D/3D 分屏、控制点与独立检查点、残差和 RMSE | 点击残差表行，三维与平面同步聚焦 |
| [Skydio 3D Scan](https://www.skydio.com/software/3d-scan) | 有定位的相机视锥体、原图画中画 | 三维视口点击相机标记；没有位姿不生成视锥体 |
| [ArcGIS Oriented Imagery](https://experience.arcgis.com/experience/833f9aef788a45fd90b956b2ca341b36) | 地图上按相机朝向绘制 FOV，悬停及选择联动原图 | 使用含 camera_pose 的上传图片；演练数据含显式合成位姿 |
| [Roboflow Annotate](https://roboflow.com/blog/team-image-annotation-workflow) | 审核流程、候选框/人工框对照、属性编辑、角色与真实租约 | 待审记录拖框、填写说明、领取/释放、批准/撤回 |
| [FiftyOne](https://voxel51.com/curation) | 图片网格、标签和置信度筛选、审核页胶片条 | 图像数据集按标签筛选；审核页切换缩略图 |
| [Elicit](https://elicit.com/industries/edu) | 答案脚标、原始证据卡、审核来源 | 连接后端问答并点击 [1]；公开搜索单列未核实背景 |

已查看可访问的官方公开页面及产品展示图。ArcGIS 示例在检查期间停留于加载界面，该项根据用户提供的定向影像交互要求实现，未声称核验其完整产品流程。公开宣传页不等于产品全部操作界面，本项目也不声称逐像素复刻。

技术选择：MapLibre GL 负责影像地图和 GeoJSON 图层；Three.js 负责街区局部三维；原生模块及表单承接现有 FastAPI。版本、许可证、图源、启动方法、已验证路径与未实现能力见 [前端说明](../frontend/README.md)。
