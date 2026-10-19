# AI Disaster Commander 前端

这是依据产品开发方案和现有原型整理的前端优先实现。当前使用原型数据层，不依赖后端服务，重点验证 P0 页面流程与响应式交互：

`事件导入 → 分析进度 → 现场态势 → 证据审核 → 方案比较 → 现场回报`

运行方式：直接打开 `index.html`；也可以用任意静态文件服务器托管 `frontend/` 目录。

页面路由使用 hash：`#import`、`#analysis`、`#command`、`#review`、`#plans`、`#field`。页面底部的 UI 方案切换器用于比较不同信息层级，后续接入真实 API 时可移除。
