import {
  state,
  entities,
  entity,
  effective,
  visibleAnnotations,
  activeArtifact,
  canReview,
  reviewedRelations,
} from './state.js';
import {
  icon,
  esc,
  badge,
  fmt,
  time,
  options,
  empty,
  observations,
  kinds,
  jsonDetails,
} from './ui.js';
import { evidencePhoto, answerView, referencesView, localTime } from './views.js';
import { relationGraph } from './map.js';

const rows = () =>
  state.annotations.filter(
    (a) =>
      (state.reviewFilter === 'all' || a.status === state.reviewFilter) &&
      (state.reviewLabel === 'all' || effective(a).observation === state.reviewLabel) &&
      effective(a).confidence >= state.minConfidence,
  );
export const reviewRows = rows;
export function analysis() {
  const status = state.galleryStatus || 'all',
    labels = state.galleryLabels || Object.keys(observations),
    confidence = state.galleryConfidence || 0;
  const images = state.images.filter((img) => {
    const anns = state.annotations.filter((a) => a.image_id === img.id);
    if (!anns.length) return status === 'all' || status === 'unassigned';
    return anns.some(
      (a) =>
        (status === 'all' || a.status === status) &&
        labels.includes(effective(a).observation) &&
        effective(a).confidence >= confidence,
    );
  });
  return (
    '<div class="page-content gallery-page"><div class="page-heading"><div><span class="eyebrow">VISUAL DATASET / MODEL OBSERVATIONS</span><h1>图像数据集</h1><p>按观察标签、审核状态与自报置信度定位需要复核的图片。</p></div><a class="button" href="#import">' +
    icon('upload') +
    '上传素材</a></div><div class="review-workflow">' +
    [
      ['all', '全部图片'],
      ['unassigned', '未生成候选'],
      ['pending_review', '待审核'],
      ['approved', '已审核'],
    ]
      .map(
        ([key, label]) =>
          '<button data-action="gallery-status" data-value="' +
          key +
          '" aria-pressed="' +
          (status === key) +
          '">' +
          label +
          '</button>',
      )
      .join('') +
    '</div><div class="gallery-layout"><section><div class="gallery-summary">显示 ' +
    images.length +
    ' / ' +
    state.images.length +
    ' 张图片 <span>AI 输出始终为候选</span></div><div class="image-grid">' +
    images
      .map((img) => {
        const anns = state.annotations.filter((a) => a.image_id === img.id);
        return (
          '<article class="image-card"><div class="image-preview">' +
          thumb(img) +
          '<span class="gallery-image-id">' +
          esc(img.id.slice(0, 8)) +
          '</span></div><div class="image-card-body"><h3>' +
          esc(img.name) +
          '</h3><p>' +
          time(img.captured_at) +
          ' · ' +
          esc(img.source) +
          '</p><div class="pills">' +
          [...new Set(anns.map((a) => effective(a).observation))]
            .map((k) => '<span>' + esc(observations[k]) + '</span>')
            .join('') +
          '</div><div class="gallery-card-actions">' +
          (anns.length
            ? '<button class="button" data-action="annotation" data-id="' +
              esc(anns[0].id) +
              '">' +
              icon('shield') +
              '审核 ' +
              anns.length +
              '</button>'
            : '<span class="meta">尚无候选</span>') +
          '<button class="button" data-action="analyze" data-id="' +
          esc(img.id) +
          '" ' +
          (state.identity.role === 'viewer' ? 'disabled' : '') +
          '>' +
          icon('scan') +
          '请求 AI 分析</button></div></div></article>'
        );
      })
      .join('') +
    '</div>' +
    (!images.length ? empty('没有符合条件的图片', '调整右侧标签开关，或上传新的现场素材。') : '') +
    '</section><aside class="gallery-filters"><h2>' +
    icon('settings') +
    '数据筛选</h2><h3>观察标签</h3>' +
    Object.entries(observations)
      .map(
        ([key, label]) =>
          '<label><input type="checkbox" data-gallery-label="' +
          key +
          '" ' +
          (labels.includes(key) ? 'checked' : '') +
          '>' +
          label +
          '<span>' +
          state.annotations.filter((a) => effective(a).observation === key).length +
          '</span></label>',
      )
      .join('') +
    '<h3>最低自报置信度</h3><label class="range-label"><output>' +
    Math.round(confidence * 100) +
    '%</output><input aria-label="数据集最低置信度" type="range" min="0" max="1" step=".05" data-control="galleryConfidence" value="' +
    confidence +
    '"></label><p>置信度未经校准；用于筛选复核，不作为事实依据。</p><h3>审核原则</h3><p>候选 → 人工修正 / 批准 → 可检索证据。任何模型输出都不能跳过人工审核。</p></aside></div></div>'
  );
}
export function thumb(img) {
  return img
    ? '<img ' +
        (img.url ? 'src="' + esc(img.url) + '"' : 'data-image="' + esc(img.id) + '"') +
        ' alt="' +
        esc(img.name) +
        '" loading="lazy">'
    : '<span class="no-photo">' + icon('image') + '</span>';
}
function objectRow(e, depth = 0) {
  const count = visibleAnnotations().filter((a) => effective(a).entity_id === e.id).length;
  return (
    '<button class="entity-row ' +
    (e.id === state.selected ? 'selected' : '') +
    ' depth-' +
    depth +
    '" data-action="select" data-id="' +
    esc(e.id) +
    '">' +
    icon(e.kind === 'building' ? 'cube' : e.kind === 'resource' ? 'plus' : 'map') +
    '<span>' +
    esc(e.name) +
    '</span>' +
    (count ? '<b>' + count + '</b>' : '') +
    '</button>'
  );
}
function tree() {
  const relations = reviewedRelations(),
    items = entities().filter((e) =>
      (e.name + ' ' + e.id).toLowerCase().includes(state.search.toLowerCase()),
    ),
    seen = new Set();
  const children = (id) =>
    relations
      .filter((r) => ['part_of', 'inside'].includes(r.predicate) && r.object === id)
      .map((r) => entity(r.subject))
      .filter(Boolean);
  function branch(e, depth = 0) {
    if (seen.has(e.id) || depth > 8) return '';
    seen.add(e.id);
    return (
      objectRow(e, Math.min(depth, 3)) +
      children(e.id)
        .map((c) => branch(c, depth + 1))
        .join('')
    );
  }
  if (state.search.trim()) return items.map((e) => objectRow(e)).join('');
  return (
    items
      .filter((e) => e.kind === 'building')
      .map((e) => {
        seen.add(e.id);
        const nested = children(e.id);
        if (!nested.length) return objectRow(e);
        const collapsed = state.collapsedBranches?.includes(e.id);
        const body = nested.map((child) => branch(child, 1)).join('');
        return (
          '<div class="object-branch"><div class="object-branch-heading"><button class="branch-toggle" data-action="toggle-branch" data-id="' +
          esc(e.id) +
          '" aria-expanded="' +
          !collapsed +
          '" aria-label="' +
          (collapsed ? '展开 ' : '收起 ') +
          esc(e.name) +
          '">' +
          (collapsed ? '▸' : '▾') +
          '</button>' +
          objectRow(e) +
          '<small>' +
          nested.length +
          '</small></div>' +
          (collapsed ? '' : body) +
          '</div>'
        );
      })
      .join('') +
    '<div class="tree-section-label">其他空间对象</div>' +
    items
      .filter((e) => !seen.has(e.id))
      .map((e) => objectRow(e))
      .join('')
  );
}
function sidebar() {
  return (
    '<aside class="entity-sidebar"><div class="side-heading"><div><span class="eyebrow">OBJECT EXPLORER</span><h2>空间对象</h2></div><span>' +
    entities().length +
    '</span></div><label class="search-box">' +
    icon('search') +
    '<input id="entity-search" aria-label="搜索空间对象" value="' +
    esc(state.search) +
    '" placeholder="名称、位置或对象 ID"></label><div class="sidebar-tabs"><span class="active">对象目录</span><span>' +
    badge('approved', '已审关系') +
    '</span></div><div class="entity-tree">' +
    tree() +
    '</div><div class="side-section"><h3>空间筛选</h3><label>中心对象<select data-control="center">' +
    options(
      entities().map((e) => [e.id, e.name]),
      state.center,
    ) +
    '</select></label><label class="range-label">缓冲半径 <output>' +
    state.radius +
    ' m</output><input aria-label="距离半径" type="range" min="25" max="500" step="25" value="' +
    state.radius +
    '" data-control="radius"></label><button class="button primary full" data-action="query">' +
    icon('search') +
    '检索已审核障碍物</button></div><div class="object-audit"><span>' +
    icon('shield') +
    '人工核验门槛</span><p>候选与已撤回记录不进入正式回答。</p></div></aside>'
  );
}
function layers() {
  return (
    '<div class="floating-layers"><div><h3>' +
    icon('layers') +
    '地图图层</h3><button data-action="toggle-layers" aria-label="关闭图层">' +
    icon('close') +
    '</button></div>' +
    Object.entries({
      objects: '建筑 / 入口 / 资源',
      roads: '有效审核路网',
      cameras: '拍摄位置与朝向',
      buffer: '空间检索缓冲圈',
    })
      .map(
        ([id, label]) =>
          '<label><input type="checkbox" data-layer="' +
          id +
          '" ' +
          (state.layers[id] ? 'checked' : '') +
          '>' +
          label +
          '</label>',
      )
      .join('') +
    '<label><input type="checkbox" data-control="basemap" ' +
    (state.basemap ? 'checked' : '') +
    '>Esri 影像底图</label><p>拍摄扇区表示朝向，显示长度不代表实际可视距离。</p></div>'
  );
}
function timeline() {
  const bins = Array(36).fill(0);
  for (const image of state.images) {
    const age = (state.timelineBase - new Date(image.captured_at)) / 3600000;
    if (age >= 0 && age < 72) bins[Math.min(35, 35 - Math.floor(age / 2))]++;
  }
  const max = Math.max(1, ...bins),
    left = ((72 - state.hours - state.endAge) / 72) * 100,
    right = ((72 - state.endAge) / 72) * 100;
  const bars = bins
    .map(
      (count, i) =>
        '<rect x="' +
        (i * 10 + 1) +
        '" y="' +
        (32 - (count / max) * 28) +
        '" width="7" height="' +
        Math.max(1, (count / max) * 28) +
        '" fill="' +
        ((i / 36) * 100 >= left && (i / 36) * 100 <= right ? '#58c9e3' : '#40515f') +
        '"/>',
    )
    .join('');
  return (
    '<section class="floating-timeline timeline" aria-label="观察时间筛选"><div class="timeline-head"><button class="timeline-play" data-action="play-time" aria-label="' +
    (state.playing ? '暂停时间播放' : '播放时间窗口') +
    '">' +
    (state.playing ? 'Ⅱ' : '▶') +
    '</button><span>' +
    icon('clock') +
    '采集时间</span><output>' +
    time(new Date(state.asOf) - state.hours * 3600000) +
    ' — ' +
    time(state.asOf) +
    '</output><span class="timeline-count">' +
    visibleAnnotations().length +
    ' 条观察</span><button data-action="time-now" class="text-button">回到现在</button></div><div class="histogram"><svg viewBox="0 0 360 36" preserveAspectRatio="none" aria-label="最近 72 小时图片采集分布">' +
    bars +
    '</svg><div class="time-window" style="left:' +
    left +
    '%;width:' +
    (right - left) +
    '%"></div></div><div class="range-pair"><input aria-label="时间窗起点：回溯小时数" type="range" min="1" max="72" value="' +
    (state.hours + state.endAge) +
    '" data-control="windowStart"><input aria-label="时间窗终点：距现在小时数" type="range" min="0" max="71" value="' +
    state.endAge +
    '" data-control="endAge"></div><div class="ticks"><span>72 小时前</span><span>48h</span><span>24h</span><span>现在</span></div><details class="exact-time"><summary>精确时间 · 最近 ' +
    state.hours +
    ' 小时</summary><label>截止时刻<input aria-label="查询截止时间" type="datetime-local" data-control="asOf" value="' +
    localTime(state.asOf) +
    '"></label><label>回溯小时<input type="range" min="1" max="72" aria-label="回溯小时数" value="' +
    state.hours +
    '" data-control="hours"></label></details></section>'
  );
}
function pip() {
  const image = state.images.find((i) => i.id === state.cameraImage),
    ann = state.annotations.find((a) => a.image_id === image?.id);
  if (!image) return '';
  return (
    '<div class="camera-pip"><div class="pip-title">' +
    icon('image') +
    '<span>定向影像 / ' +
    esc(image.name) +
    '</span><button data-action="close-pip" aria-label="关闭图片画中画">' +
    icon('close') +
    '</button></div>' +
    thumb(image) +
    '<div class="pip-meta"><span>' +
    time(image.captured_at) +
    '</span><span>' +
    (image.camera_pose
      ? fmt(image.camera_pose.heading_deg) +
        '° / ' +
        fmt(image.camera_pose.horizontal_fov_deg) +
        '° FOV'
      : '相机朝向未知') +
    '</span></div>' +
    (ann
      ? '<button class="pip-review" data-action="annotation" data-id="' +
        esc(ann.id) +
        '">' +
        badge(ann.status) +
        '核对原图与标注 ' +
        icon('arrow') +
        '</button>'
      : '') +
    '</div>'
  );
}
function intel() {
  const e = entity(state.selected),
    ann = visibleAnnotations().find((a) => effective(a).entity_id === state.selected),
    network = activeArtifact('road_network');
  return (
    '<aside class="intel"><div class="panel-heading"><h2>' +
    icon('chat') +
    '现场情报</h2><button data-action="toggle-intel" aria-label="收起情报抽屉">' +
    icon('close') +
    '</button></div><div class="intel-scroll"><div class="intel-tabs"><strong>查证结果</strong><span>证据与来源</span></div>' +
    answerView() +
    (e
      ? '<section class="object-summary"><div class="eyebrow">' +
        esc(e.id.toUpperCase()) +
        ' / ' +
        esc(kinds[e.kind]) +
        '</div><h2>' +
        esc(e.name) +
        '</h2><div class="object-coordinates">' +
        icon('map') +
        (e.coordinates
          ? e.coordinates.latitude.toFixed(6) +
            '° N · ' +
            e.coordinates.longitude.toFixed(6) +
            '° E'
          : '暂无坐标') +
        '</div><div class="object-stats"><span><b>' +
        visibleAnnotations().filter((a) => effective(a).entity_id === e.id).length +
        '</b> 条观察</span><span>' +
        badge(
          state.dataset.snapshot.coordinate_basis === 'exercise' ? 'pending_review' : 'approved',
          state.dataset.snapshot.coordinate_basis === 'exercise' ? '演练坐标' : '实测坐标',
        ) +
        '</span></div>' +
        (ann
          ? evidencePhoto(ann) +
            '<div class="evidence-description"><div>' +
            badge(ann.status) +
            '<span class="confidence">' +
            fmt(effective(ann).confidence * 100) +
            '% 自报置信度</span></div><p>' +
            esc(effective(ann).description) +
            '</p><button class="button full" data-action="annotation" data-id="' +
            esc(ann.id) +
            '">打开审核工作台 ' +
            icon('arrow') +
            '</button></div>'
          : empty('当前时间窗内无观察', '拖动时间窗或上传现场资料。')) +
        '</section>'
      : '') +
    referencesView() +
    '<div class="source-health"><span>' +
    icon('shield') +
    '查询边界</span><p>只引用有效审核记录。' +
    (network ? '已加载审核路网。' : '当前无有效审核路网。') +
    '</p></div></div><form id="ask-form" class="dock-question"><label for="question">' +
    icon('chat') +
    '向现场证据提问</label><textarea id="question" name="question" minlength="2" maxlength="1000" required placeholder="A 楼 100 米内，哪些入口有障碍物？"></textarea><div class="ask-actions"><select name="kind" aria-label="问答类型"><option value="ask">图片证据</option><option value="reason/ask">复杂空间关系</option><option value="references/search">未核实背景搜索</option></select><button class="icon-button primary" aria-label="提交问题">' +
    icon('arrow') +
    '</button></div><small>' +
    (state.client ? '请求已配置模型，可能产生费用' : '离线演练 · 连接后可调用模型') +
    '</small></form></aside>'
  );
}
export function command() {
  const reviewed = visibleAnnotations().filter((a) => a.status === 'approved'),
    obstacles = reviewed.filter((a) => effective(a).observation === 'obstacle_visible');
  return (
    '<div class="command-layout v2 ' +
    (!state.showIntel ? 'intel-collapsed' : '') +
    '">' +
    sidebar() +
    '<section class="operating-map"><div class="map-heading"><div><span class="eyebrow">COMMON OPERATING PICTURE</span><h1>现场态势</h1></div><div class="hud-stats"><span><i class="dot red"></i>' +
    obstacles.length +
    ' 障碍物记录</span><span>' +
    reviewed.length +
    ' 已审观察</span></div></div><div id="gis-slot"></div><div class="gis-floatbar"><div class="segmented"><button data-action="map-view" data-value="map" aria-pressed="' +
    (state.mapView === 'map') +
    '">' +
    icon('map') +
    '地图</button><button data-action="map-view" data-value="graph" aria-pressed="' +
    (state.mapView === 'graph') +
    '">' +
    icon('link') +
    '关系图</button></div><button class="floating-tool" data-action="toggle-layers" aria-expanded="' +
    state.showLayers +
    '">' +
    icon('layers') +
    '图层</button><button class="floating-tool" data-action="fit-map">' +
    icon('scan') +
    '全域</button>' +
    (!state.showIntel
      ? '<button class="floating-tool" data-action="toggle-intel">' + icon('chat') + '情报</button>'
      : '') +
    '</div><div class="filter-pills"><button data-action="focus-center">' +
    icon('map') +
    esc(entity(state.center)?.name || '未选中心') +
    '</button><button data-action="reset-radius">' +
    state.radius +
    ' m 缓冲圈 ×</button><button data-action="time-now">最近 ' +
    state.hours +
    ' 小时 ×</button><span>' +
    badge('approved', '正式检索仅已审核') +
    '</span></div>' +
    (state.showLayers ? layers() : '') +
    (state.mapView === 'graph'
      ? '<div class="relation-inset"><div>' +
        icon('link') +
        '实体关系 · 已审核<button data-action="map-view" data-value="map" aria-label="关闭关系图">' +
        icon('close') +
        '</button></div>' +
        relationGraph() +
        '</div>'
      : '') +
    '<div class="map-compass"><b>N</b><span>↑</span><button data-action="gis-zoom" data-value="1" aria-label="放大地图">+</button><button data-action="gis-zoom" data-value="-1" aria-label="缩小地图">−</button></div>' +
    pip() +
    '<div class="floating-legend"><span><i class="dot cyan"></i>资源 / 审核路网</span><span><i class="dot amber"></i>候选</span><span><i class="dash"></i>封闭 / 未知</span></div>' +
    timeline() +
    '<div id="basemap-status">' +
    (state.client ? 'WGS84 · 数据依赖现场录入' : '演练图层 · 不代表底图所在地发生灾情') +
    '</div></section>' +
    (state.showIntel ? intel() : '') +
    '</div>'
  );
}

function reviewWorkflow() {
  return (
    '<div class="review-workflow">' +
    [
      ['all', '全部'],
      ['pending_review', '候选待审'],
      ['approved', '已入库'],
      ['rejected', '已驳回'],
      ['withdrawn', '已撤回'],
    ]
      .map(
        ([id, label]) =>
          '<button data-action="review-filter" data-value="' +
          id +
          '" aria-pressed="' +
          (state.reviewFilter === id) +
          '">' +
          label +
          ' <b>' +
          (id === 'all'
            ? state.annotations.length
            : state.annotations.filter((a) => a.status === id).length) +
          '</b></button>',
      )
      .join('') +
    '</div>'
  );
}
function leasePanel(a) {
  if (a.status !== 'pending_review') return '';
  const held =
      state.leaseKey === a.id && state.lease && new Date(state.lease.expires_at) > new Date(),
    mine = held && state.lease.user_id === state.identity.user_id;
  return (
    '<div class="lease-panel">' +
    icon('shield') +
    '<span>' +
    (held
      ? esc(state.lease.user_id) + ' 占用至 ' + time(state.lease.expires_at)
      : state.leaseKnown && state.leaseKey === a.id
        ? '当前未占用'
        : '占用状态待刷新') +
    '</span><button type="button" class="text-button" data-action="lease" data-value="' +
    (mine ? 'release' : 'claim') +
    '" ' +
    (!canReview() ? 'disabled' : '') +
    '>' +
    (mine ? '释放' : held ? '刷新状态' : '领取审核') +
    '</button><small>租约 5 分钟；另一审核员占用时后端拒绝提交。</small></div>'
  );
}
export function review() {
  const filtered = rows();
  let a = filtered.find((a) => a.id === state.annotationId) || filtered[0];
  if (a) state.annotationId = a.id;
  const v = a ? effective(a) : null;
  const list =
    '<aside class="review-list"><div class="side-heading"><h2>图像队列</h2><span>' +
    filtered.length +
    '</span></div><label>观察标签<select data-control="reviewLabel">' +
    options([['all', '全部标签'], ...Object.entries(observations)], state.reviewLabel) +
    '</select></label><label class="range-label">最低自报置信度 <output>' +
    Math.round(state.minConfidence * 100) +
    '%</output><input type="range" min="0" max="1" step=".05" aria-label="最低自报置信度" data-control="minConfidence" value="' +
    state.minConfidence +
    '"></label><div class="review-queue">' +
    filtered
      .map(
        (r) =>
          '<button class="review-item ' +
          (r.id === a?.id ? 'selected' : '') +
          '" data-action="review-select" data-id="' +
          esc(r.id) +
          '">' +
          thumb(state.images.find((i) => i.id === r.image_id)) +
          '<span><strong>' +
          esc(entity(effective(r).entity_id)?.name || '待关联对象') +
          '</strong><small>' +
          time(state.images.find((i) => i.id === r.image_id)?.captured_at) +
          '</small>' +
          badge(r.status) +
          '</span></button>',
      )
      .join('') +
    '</div><p class="meta">低置信度不等于错误；高置信度不等于核实。</p></aside>';
  if (!a)
    return (
      '<div class="page-content"><h1>证据审核</h1>' +
      reviewWorkflow() +
      empty('没有符合筛选条件的候选', '切换审核状态或降低置信度筛选阈值。') +
      '<button class="button" data-action="review-reset">清除筛选</button></div>'
    );
  return (
    '<div class="annotation-workspace"><header class="review-page-head"><div><span class="eyebrow">ANNOTATION / HUMAN IN THE LOOP</span><h1>证据审核</h1></div>' +
    badge('approved', state.identity.user_id + ' · ' + state.identity.role) +
    '<span class="review-progress">' +
    state.annotations.filter((a) => a.status !== 'pending_review').length +
    ' / ' +
    state.annotations.length +
    ' 已处理</span></header>' +
    reviewWorkflow() +
    '<div class="review-layout v2">' +
    list +
    '<section class="review-main"><div class="canvas-toolbar"><span>' +
    icon('image') +
    esc(state.images.find((i) => i.id === a.image_id)?.name || '现场图片') +
    '</span><button data-action="image-zoom" data-value="-0.25" aria-label="缩小图片">−</button><output>' +
    Math.round(state.imageZoom * 100) +
    '%</output><button data-action="image-zoom" data-value="0.25" aria-label="放大图片">+</button><button data-action="draw-box" aria-pressed="' +
    state.drawBox +
    '" ' +
    (a.status !== 'pending_review' ? 'disabled' : '') +
    '>' +
    icon('scan') +
    '框选</button><button data-action="compare-boxes" aria-pressed="' +
    state.compareBoxes +
    '">' +
    icon('layers') +
    '原始对照</button></div><div class="annotation-canvas ' +
    (state.drawBox ? 'drawing' : '') +
    '"><div class="image-transform" style="width:' +
    state.imageZoom * 100 +
    '%">' +
    evidencePhoto(a) +
    '<div class="annotation-label">' +
    esc(observations[v.observation]) +
    ' · ' +
    fmt(v.confidence * 100) +
    '% ' +
    badge(a.status) +
    '</div></div></div><div class="canvas-status"><span>归一化坐标 · 拖动框选可修正候选区域</span><span>' +
    icon('shield') +
    '保留原始标注</span></div><div class="filmstrip">' +
    filtered
      .map(
        (r, i) =>
          '<button class="' +
          (r.id === a.id ? 'selected' : '') +
          '" data-action="review-select" data-id="' +
          esc(r.id) +
          '">' +
          thumb(state.images.find((img) => img.id === r.image_id)) +
          '<span>' +
          String(i + 1).padStart(2, '0') +
          ' · ' +
          esc(entity(effective(r).entity_id)?.name || '待关联') +
          '</span></button>',
      )
      .join('') +
    '</div><div class="keyboard-help"><kbd>←</kbd><kbd>→</kbd> 切图 <kbd>1–3</kbd> 标签 <kbd>Space</kbd> 批准 <kbd>Backspace</kbd> 驳回 · 需先填写审核说明</div></section><aside class="review-editor"><div class="panel-heading"><h2>标注属性</h2>' +
    badge(a.status) +
    '</div><div class="panel-body">' +
    leasePanel(a) +
    '<form id="review-form"><fieldset ' +
    (a.status !== 'pending_review' || !canReview() ? 'disabled' : '') +
    '><label>关联对象<select name="entity_id" required>' +
    options([['', '待关联'], ...entities().map((e) => [e.id, e.name])], v.entity_id) +
    '</select></label><label>观察类别<select name="observation">' +
    options(Object.entries(observations), v.observation) +
    '</select></label><label>观察描述<textarea name="description" maxlength="2000" required>' +
    esc(v.description) +
    '</textarea></label><div class="bbox-fields">' +
    Object.entries(v.bbox)
      .map(
        ([key, value]) =>
          '<label>' +
          key +
          '<input name="' +
          key +
          '" type="number" min="0" max="1" step=".001" value="' +
          value +
          '" required></label>',
      )
      .join('') +
    '</div></fieldset><label>审核 / 撤回说明<textarea name="note" maxlength="2000" required placeholder="记录核验依据、纠正原因或撤回理由"></textarea></label><div class="button-row"><button class="button primary" name="decision" value="approve" ' +
    (a.status !== 'pending_review' || !canReview() ? 'disabled' : '') +
    '>' +
    icon('check') +
    '批准 / 修正</button><button class="button danger" name="decision" value="reject" formnovalidate ' +
    (a.status !== 'pending_review' || !canReview() ? 'disabled' : '') +
    '>驳回</button></div>' +
    (a.status === 'approved'
      ? '<button class="button danger full" name="decision" value="withdraw" ' +
        (!canReview() ? 'disabled' : '') +
        '>撤回批准</button>'
      : '') +
    '</form>' +
    jsonDetails('原始候选 · 只读', a.annotation) +
    (a.review ? jsonDetails('审核记录', a.review) : '') +
    '<div class="meta">' +
    (a.origin === 'ai' ? 'AI 候选' : '外部导入') +
    ' · ' +
    esc(a.id) +
    '</div></div></aside></div></div>'
  );
}
