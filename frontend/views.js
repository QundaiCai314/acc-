import {
  state,
  entities,
  entity,
  effective,
  canReview,
  canWrite,
  visibleAnnotations,
  activeArtifact,
} from './state.js';
import {
  esc,
  icon,
  badge,
  empty,
  fmt,
  time,
  options,
  kinds,
  observations,
  jsonDetails,
  safeURL,
} from './ui.js';
import { cameraFields } from './camera.js';
import { sceneControls } from './scene.js';
import { mapPanel } from './map.js';

const entityOptions = (selected) =>
  options(
    entities().map((e) => [e.id, e.name]),
    selected,
  );
const disabled = (allowed) => (allowed ? '' : 'disabled');
const title = (over, heading, detail) =>
  '<div class="page-heading"><div><span class="eyebrow">' +
  over +
  '</span><h1>' +
  heading +
  '</h1><p>' +
  detail +
  '</p></div><span class="version">SPATIAL RAG / 0.3.0</span></div>';
const panel = (name, body, sub = '') =>
  '<section class="panel"><div class="panel-heading"><h2>' +
  name +
  '</h2><small>' +
  sub +
  '</small></div><div class="panel-body">' +
  body +
  '</div></section>';
export function shell(content) {
  const pending = state.annotations.filter((a) => a.status === 'pending_review').length;
  const modes = [
    ['command', 'map', '地图工作台', ['command']],
    ['analysis', 'image', '素材与审核', ['analysis', 'import', 'review', 'field']],
    ['plans', 'route', '空间分析', ['plans', 'reason']],
    ['registration', 'cube', '三维核验', ['registration']],
  ];
  return (
    '<header class="topbar"><a href="#command" class="brand"><span class="brand-mark">△</span><span>DISASTER<span class="brand-light">COMMANDER</span></span></a><nav class="primary-modes" aria-label="工作流程">' +
    modes
      .map(
        ([id, symbol, name, routes]) =>
          '<a href="#' +
          id +
          '" ' +
          (routes.includes(state.screen) ? 'aria-current="page"' : '') +
          '>' +
          icon(symbol) +
          '<span>' +
          name +
          '</span>' +
          (id === 'analysis' && pending ? '<b>' + pending + '</b>' : '') +
          '</a>',
      )
      .join('') +
    '</nav><div class="top-right"><div class="art-switcher" role="group" aria-label="界面主题">' +
    [
      ['vellum', '纸本测绘'],
      ['brutalist', '粗野档案'],
      ['mineral', '矿物岩彩'],
    ]
      .map(
        ([id, label]) =>
          '<button type="button" data-action="art-theme" data-value="' +
          id +
          '" aria-pressed="' +
          (state.artTheme === id) +
          '">' + label + '</button>',
      )
      .join('') +
    '</div>' +
    badge(state.client ? 'approved' : 'pending_review', state.client ? '后端已连接' : '离线演练') +
    '<button class="connection" data-action="connect" aria-label="连接设置">' +
    icon('settings') +
    '<span>连接设置</span></button><span class="user-avatar">' +
    esc(state.identity.user_id.slice(0, 1)) +
    '</span><span class="user-name">' +
    esc(state.identity.user_id) +
    '<small>' +
    esc(
      { admin: '管理员', reviewer: '审核员', contributor: '采集员', viewer: '观察员' }[
        state.identity.role
      ],
    ) +
    '</small></span></div></header><div class="workspace-body"><div class="contextbar"><div><span class="live-dot"></span><strong>' +
    esc(state.dataset?.snapshot.title || '尚未选择现场') +
    '</strong></div><div><span class="workspace-label">' +
    esc(state.identity.workspace) +
    '</span><button class="text-button" data-action="refresh" ' +
    disabled(!state.busy) +
    '>' +
    icon('refresh') +
    '刷新</button><button class="text-button" data-action="datasets">切换现场 ↓</button></div></div>' +
    (state.error
      ? '<div class="error-banner" role="alert">' +
        esc(state.error) +
        '<button data-action="dismiss-error" aria-label="关闭错误提示">' +
        icon('close') +
        '</button></div>'
      : '') +
    '<main id="main" tabindex="-1" aria-busy="' +
    state.busy +
    '">' +
    content +
    '</main><footer class="statusbar"><span>' +
    icon('shield') +
    (state.client
      ? '审核由后端校验 · 当前工作空间 ' + esc(state.identity.workspace)
      : '演练沙盒 · 操作仅在当前页面内生效') +
    '</span><span>观察证据 ≠ 当前通行安全</span></footer></div>'
  );
}
export function evidencePhoto(ann) {
  const img = state.images.find((i) => i.id === ann?.image_id) || ann?.imageMeta;
  if (!img) return empty('暂无原图', '选择一条观察记录查看。');
  const box = effective(ann).bbox;
  return (
    '<div class="evidence-photo"><img ' +
    (img.url ? 'src="' + esc(img.url) + '"' : 'data-image="' + esc(img.id) + '"') +
    ' alt="' +
    esc(img.source + '；' + img.name) +
    '"><svg class="box-overlay" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="' +
    (ann.status === 'approved' ? '已审核标注框' : '待审核候选框') +
    '"><rect x="' +
    box.x_min * 100 +
    '" y="' +
    box.y_min * 100 +
    '" width="' +
    (box.x_max - box.x_min) * 100 +
    '" height="' +
    (box.y_max - box.y_min) * 100 +
    '" class="' +
    (ann.status === 'approved' ? 'approved' : 'candidate') +
    '"/></svg><span class="photo-label">' +
    (img.evidence_basis === 'exercise' ? '演练素材' : '现场图片') +
    '</span></div>'
  );
}
function citationCard(c, i) {
  const ann = {
    annotation: c.annotation,
    image_id: c.image_id,
    status: 'approved',
    imageMeta: {
      id: c.image_id,
      name: c.entity_name || '引用图片',
      source: c.source,
      evidence_basis: c.evidence_basis,
    },
  };
  return (
    '<article class="citation ' +
    (state.activeCitation === i ? 'active' : '') +
    '" data-index="' +
    i +
    '"><div class="citation-title"><button data-action="select" data-id="' +
    esc(c.entity_id || c.annotation.entity_id) +
    '">[' +
    (i + 1) +
    '] ' +
    esc(c.entity_name || entity(c.annotation.entity_id)?.name || '图像证据') +
    '</button>' +
    badge('approved') +
    '</div>' +
    evidencePhoto(ann) +
    '<p>' +
    esc(c.annotation.description) +
    '</p><div class="meta">' +
    time(c.captured_at) +
    ' · ' +
    esc(c.reviewer) +
    '<br>' +
    esc(c.source) +
    '</div><button class="text-button" data-action="annotation" data-id="' +
    esc(c.annotation_id) +
    '">核对审核记录 ' +
    icon('arrow') +
    '</button></article>'
  );
}
export function answerView() {
  const result = state.answer;
  if (!result) return '';
  const evidence = result.evidence || result,
    citations = evidence.citations || evidence.matches?.flatMap((m) => m.image_citations) || [];
  return (
    '<section class="answer"><div class="answer-heading">' +
    icon('chat') +
    '查证结果 ' +
    badge(
      result.status === 'clarification_needed' || evidence.status === 'insufficient_evidence'
        ? 'pending_review'
        : 'approved',
      result.status === 'clarification_needed'
        ? '待补充'
        : evidence.status === 'insufficient_evidence'
          ? '信息不足'
          : '查询完成',
    ) +
    '</div><p>' +
    esc(
      result.answer ||
        (evidence.matches?.length
          ? '匹配对象：' + evidence.matches.map((m) => m.entity_name).join('、')
          : '没有满足全部条件的对象。'),
    ).replace(/\[(\d+)\]/g, (match, n) =>
      Number(n) <= citations.length
        ? '<button class="inline-citation" data-action="citation" data-index="' +
          (Number(n) - 1) +
          '">' +
          match +
          '</button>'
        : match,
    ) +
    '</p>' +
    (result.interpreted_conditions
      ? '<div class="pills">' +
        result.interpreted_conditions.map((c) => '<span>' + esc(c) + '</span>').join('') +
        '</div>'
      : '') +
    jsonDetails('查看实际查询条件', result.interpreted_query || evidence.query || {}) +
    (result.run_id ? '<small class="meta">运行 ' + esc(result.run_id) + '</small>' : '') +
    (evidence.matches || [])
      .map(
        (m) =>
          '<div class="proof"><button data-action="select" data-id="' +
          esc(m.entity_id) +
          '">' +
          esc(m.entity_name) +
          '</button>' +
          jsonDetails('空间关系依据', m.proofs) +
          '</div>',
      )
      .join('') +
    (evidence.artifact_citations?.length
      ? jsonDetails('空间工件来源与审核', evidence.artifact_citations)
      : '') +
    citations.map(citationCard).join('') +
    (evidence.limitations
      ? '<details><summary>结果使用边界</summary><ul>' +
        evidence.limitations.map((l) => '<li>' + esc(l) + '</li>').join('') +
        '</ul></details>'
      : '') +
    '</section>'
  );
}
export function referencesView() {
  return state.references
    ? '<section class="references"><h3>公开背景资料 ' +
        badge('pending_review', '未核实背景') +
        '</h3><p class="meta">不参与现场事实推理 · ' +
        time(state.references.retrieved_at) +
        '</p>' +
        state.references.results
          .map(
            (r) =>
              '<article><a href="' +
              safeURL(r.url) +
              '" target="_blank" rel="noopener noreferrer">' +
              esc(r.title) +
              '</a><p>' +
              esc(r.content) +
              '</p></article>',
          )
          .join('') +
        '</section>'
    : '';
}
export function localTime(value = new Date()) {
  const d = new Date(value);
  return new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
export function uploadForm() {
  return (
    '<form id="image-form" class="form-grid"><label class="upload-zone">' +
    icon('upload') +
    '<strong>选择现场图片</strong><span>PNG / JPEG · 单张不超过 5 MB</span><input name="file" type="file" accept="image/png,image/jpeg" required></label><label>采集时间<input name="captured_at" type="datetime-local" value="' +
    localTime() +
    '" required></label><label>素材性质<select name="evidence_basis"><option value="exercise">演练素材</option><option value="field_image">真实现场图片</option></select></label><label class="wide">来源说明<input name="source" required maxlength="2000" placeholder="采集人员、设备或原始来源"></label>' +
    cameraFields() +
    '<button class="button primary wide" ' +
    disabled(canWrite() && !state.busy) +
    '>' +
    icon('upload') +
    '上传至当前现场</button></form>'
  );
}
export function importPage() {
  return (
    '<div class="page-content">' +
    title('DATA INTAKE', '把现场资料放到同一张图上', '先建立地图快照，再上传带时间与来源的图片。') +
    '<div class="two-columns">' +
    panel(
      '01 / 地图快照',
      '<p class="muted">包含建筑、入口和资源的 WGS84 点位。快照提交后不可覆盖。</p><form id="dataset-form"><label class="upload-zone">' +
        icon('map') +
        '<strong>导入地图 JSON</strong><span>地图来源、录入者、坐标性质与对象列表</span><input type="file" name="file" accept=".json,application/json" required></label><button class="button primary" ' +
        disabled(canWrite() && !state.busy) +
        '>建立新现场</button></form><button class="text-button" data-action="download" data-kind="dataset">下载地图模板 ↓</button>',
    ) +
    panel('02 / 现场图片', uploadForm(), state.dataset ? '当前现场已选择' : '请先建立现场') +
    '</div>' +
    panel(
      '03 / 空间数据',
      '<div class="artifact-shortcuts"><a href="#registration">' +
        icon('cube') +
        '<span><strong>三维控制点与配准</strong><small>独立检查点、误差阈值、对象范围</small></span>' +
        icon('arrow') +
        '</a><a href="#plans">' +
        icon('route') +
        '<span><strong>道路网络</strong><small>方向、状态、通行方式与有效时间</small></span>' +
        icon('arrow') +
        '</a><a href="#reason">' +
        icon('link') +
        '<span><strong>空间关系</strong><small>包含、从属、连接、阻挡</small></span>' +
        icon('arrow') +
        '</a></div>',
    ) +
    '<div class="boundary">' +
    icon('shield') +
    '当前接收图片与结构化空间数据，不包含视频抽帧或照片自动重建。</div></div>'
  );
}
function artifactImport(kind, label) {
  return (
    '<form id="artifact-form" data-kind="' +
    kind +
    '"><label>导入' +
    label +
    ' JSON<input type="file" name="file" accept=".json,application/json" required></label><div class="button-row"><button class="button" ' +
    disabled(canWrite() && !state.busy) +
    '>' +
    icon('upload') +
    '导入待审快照</button><button type="button" class="text-button" data-action="download" data-kind="' +
    kind +
    '">模板 ↓</button></div></form>'
  );
}
function artifactReview(a) {
  return (
    '<div class="artifact-review">' +
    badge(a.status) +
    '<span class="meta">有效至 ' +
    time(a.snapshot.valid_until) +
    '</span><form class="artifact-review-form" data-id="' +
    esc(a.id) +
    '"><label>审核或撤回依据<input name="note" required maxlength="2000" placeholder="填写核验说明"></label><div class="button-row">' +
    (a.status === 'pending_review'
      ? '<button class="button primary" name="decision" value="approve" ' +
        disabled(canReview() && !state.busy) +
        '>批准快照</button><button class="button" name="decision" value="reject" ' +
        disabled(canReview() && !state.busy) +
        '>驳回</button>'
      : a.status === 'approved'
        ? '<button class="button danger" name="decision" value="withdraw" ' +
          disabled(canReview() && !state.busy) +
          '>撤回快照</button>'
        : '') +
    '</div></form>' +
    jsonDetails('快照与来源', a.snapshot) +
    (a.review ? jsonDetails('审核记录', a.review) : '') +
    '</div>'
  );
}
function artifactList(kind) {
  const rows = state.artifacts.filter((a) => a.artifact_type === kind);
  return rows.length
    ? rows
        .map(
          (a) =>
            '<details class="artifact-detail"><summary>' +
            esc(a.id.slice(0, 8)) +
            ' · ' +
            esc(a.snapshot.source_note.slice(0, 60)) +
            '</summary>' +
            artifactReview(a) +
            '</details>',
        )
        .join('')
    : empty('暂无空间快照', '导入后需要审核，才能参与正式查询。');
}
export function registration() {
  const regs = state.artifacts.filter((a) => a.artifact_type === 'registration'),
    r = regs.find((a) => a.id === state.artifactId) || regs[0];
  const points = r
    ? [
        ...r.snapshot.control_points.map((p, i) => ({
          ...p,
          kind: '控制点',
          error: r.computed?.fit_residuals_m[i],
        })),
        ...r.snapshot.check_points.map((p, i) => ({
          ...p,
          kind: '独立检查点',
          error: r.computed?.check_residuals_m[i],
        })),
      ]
    : [];
  return (
    '<div class="page-content">' +
    title(
      'SPATIAL REGISTRATION',
      '三维配准与误差核验',
      '用控制点建立对应关系，以独立检查点检验配准结果。',
    ) +
    '<div class="boundary">' +
    icon('cube') +
    '需要输入控制点、检查点和对象范围。当前显示几何范围，不生成实景三维模型。</div><div class="two-columns scene-columns"><section class="panel"><div class="panel-heading"><h2>局部三维视图</h2><label><span class="sr-only">配准快照</span><select data-control="registration">' +
    options(
      regs.map((a) => [a.id, a.snapshot.scene_name]),
      r?.id,
    ) +
    '</select></label></div>' +
    (r ? sceneControls(r) : empty('暂无三维配准数据', '上传控制点、独立检查点和对象范围后查看。')) +
    '</section>' +
    panel(
      '精度核验',
      r
        ? '<div class="metric-row"><div><span>拟合 RMSE</span><strong>' +
            fmt(r.computed?.fit_rmse_m) +
            '<small> m</small></strong></div><div><span>检查点 RMSE</span><strong>' +
            fmt(r.computed?.check_rmse_m) +
            '<small> m</small></strong></div></div><div class="table-scroll"><table><thead><tr><th>点位</th><th>类别</th><th>场景坐标</th><th>ENU / m</th><th>残差 / m</th></tr></thead><tbody>' +
            points
              .map(
                (p) =>
                  '<tr class="' +
                  (state.point === p.label ? 'selected' : '') +
                  '"><td><button class="text-button" data-action="point" data-id="' +
                  esc(p.label) +
                  '">' +
                  esc(p.label) +
                  '</button></td><td>' +
                  p.kind +
                  '</td><td>' +
                  p.scene.map(fmt).join(', ') +
                  '</td><td>' +
                  p.enu_m.map(fmt).join(', ') +
                  '</td><td>' +
                  fmt(p.error) +
                  '</td></tr>',
              )
              .join('') +
            '</tbody></table></div><p class="meta">点击点位聚焦。误差来自配准计算；合成控制点的零残差不代表真实测绘精度。</p>' +
            artifactReview(r)
        : empty('尚未导入配准快照'),
    ) +
    '</div>' +
    panel('导入控制点与对象范围', artifactImport('registrations', '三维配准')) +
    '</div>'
  );
}
export function plans(embedded = false) {
  const nets = state.artifacts.filter(
      (a) => a.artifact_type === 'road_network' && a.status === 'approved',
    ),
    r = state.route;
  return (
    '<div class="page-content">' +
    title(
      'NETWORK ANALYSIS',
      '道路可达性',
      '按审核路网计算路径，排除封闭、未知与通行方式不匹配的道路。',
    ) +
    '<div class="route-layout"><div>' +
    (embedded ? '' : mapPanel()) +
    '</div>' +
    panel(
      '路径检索',
      '<form id="route-form"><label>审核路网<select name="network_id" required>' +
        options(
          nets.map((n) => [n.id, n.snapshot.source_note.slice(0, 45)]),
          activeArtifact('road_network')?.id,
        ) +
        '</select></label><div class="two-fields"><label>起点<select name="start_entity_id">' +
        entityOptions(state.client ? entities()[0]?.id : 'west') +
        '</select></label><label>终点<select name="end_entity_id">' +
        entityOptions(state.selected) +
        '</select></label></div><label>通行方式<select name="mode"><option value="walk">步行</option><option value="vehicle">车辆</option></select></label><label>查询时刻<input type="datetime-local" name="as_of" value="' +
        localTime(state.asOf) +
        '" required></label><button class="button primary full" ' +
        disabled(nets.length && !state.busy) +
        '>' +
        icon('route') +
        '计算路径</button></form>' +
        (r
          ? '<div class="route-result"><span class="eyebrow">ROUTE RESULT</span><h3>' +
            (r.status === 'reachable'
              ? fmt(r.distance_m) + ' <small>米 · 路网距离</small>'
              : '当前路网不可达') +
            '</h3><p>' +
            esc((r.entity_ids || []).map((id) => entity(id)?.name || id).join(' → ')) +
            '</p>' +
            jsonDetails('路段与排除依据', r) +
            '</div>'
          : '<p class="muted">选择起终点后计算，结果会同步高亮在地图中。</p>') +
        '<div class="boundary">可达不等于安全。此处使用路网最短路径，不是旧版 OR-Tools 救援方案。</div>',
    ) +
    '</div><div class="two-columns">' +
    panel('路网快照审核', artifactList('road_network')) +
    panel('导入路网', artifactImport('networks', '道路网络')) +
    '</div></div>'
  );
}
const relations = {
  near: '邻近（米）',
  part_of: '属于',
  inside: '位于内部',
  connects_to: '连接',
  blocks: '阻挡',
  above: '高于',
  below: '低于',
  reachable_from: '从该处可达',
  north_of: '北侧',
  south_of: '南侧',
  east_of: '东侧',
  west_of: '西侧',
};
export function conditionRow(index = 0) {
  return (
    '<div class="condition-row"><label>关系<select name="relation">' +
    options(Object.entries(relations), 'near') +
    '</select></label><label>参照对象<select name="reference">' +
    entityOptions(state.center) +
    '</select></label><label>距离 / m<input name="distance" type="number" min="1" max="100000" value="100"></label><button type="button" class="icon-button" data-action="remove-condition" aria-label="删除条件">' +
    icon('close') +
    '</button></div>'
  );
}
export function reason() {
  return (
    '<div class="page-content">' +
    title(
      'SPATIAL REASONING',
      '把复杂问题拆成可验证条件',
      '全部条件同时成立才返回对象；关系链与工件来源随结果展示。',
    ) +
    '<div class="two-columns">' +
    panel(
      '联合条件查询',
      '<form id="reason-form"><div id="conditions">' +
        conditionRow() +
        '</div><button type="button" class="text-button" data-action="add-condition">' +
        icon('plus') +
        '增加条件（最多 12 条）</button><label>对象类型<select name="kind">' +
        options([['', '全部对象'], ...Object.entries(kinds)], '') +
        '</select></label>' +
        ['road_network', 'relation_set', 'registration']
          .map(
            (kind, i) =>
              '<label>' +
              ['路网快照', '关系快照', '配准快照'][i] +
              '<select name="' +
              ['network_id', 'relation_set_id', 'registration_id'][i] +
              '">' +
              options(
                [
                  ['', '不指定'],
                  ...state.artifacts
                    .filter((a) => a.artifact_type === kind && a.status === 'approved')
                    .map((a) => [a.id, a.snapshot.source_note.slice(0, 50)]),
                ],
                activeArtifact(kind)?.id || '',
              ) +
              '</select></label>',
          )
          .join('') +
        '<label>可达方式<select name="mode"><option value="walk">步行</option><option value="vehicle">车辆</option></select></label><button class="button primary full" ' +
        disabled(!state.busy) +
        '>' +
        icon('link') +
        '执行联合查询</button></form>',
    ) +
    panel(
      '查询结果',
      answerView() ||
        empty('等待查询', 'near、方位、包含、多跳关系、上下位置与路网可达可组合查询。'),
    ) +
    '</div><div class="two-columns">' +
    panel('关系快照审核', artifactList('relation_set')) +
    panel('导入空间关系', artifactImport('relations', '空间关系')) +
    '</div></div>'
  );
}
export function field() {
  return (
    '<div class="page-content">' +
    title(
      'FIELD OBSERVATION',
      '把现场变化带回指挥台',
      '先上传原图，再关联对象提交观察。人工录入也需要审核。',
    ) +
    '<div class="two-columns">' +
    panel('01 / 上传现场原图', uploadForm()) +
    panel(
      '02 / 提交待审观察',
      '<form id="observation-form"><label>来源图片<select name="image_id" required>' +
        options(
          state.images.map((i) => [i.id, i.name]),
          state.images[0]?.id,
        ) +
        '</select></label><label>地图对象<select name="entity_id" required>' +
        entityOptions(state.selected) +
        '</select></label><label>观察类别<select name="observation">' +
        options(Object.entries(observations), 'unknown') +
        '</select></label><label>描述<textarea name="description" required maxlength="2000" placeholder="描述图片可观察的事实，避免推断安全性"></textarea></label><label>来源 / 核实说明<input name="source_note" required maxlength="2000"></label><p class="meta">默认以整张图片为观察区域，审核员可修正标注框。记录来源为外部导入。</p><button class="button primary full" ' +
        disabled(canWrite() && state.images.length && !state.busy) +
        '>' +
        icon('upload') +
        '提交待审观察</button></form>',
    ) +
    '</div></div>'
  );
}
