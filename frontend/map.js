import {
  state,
  entities,
  entity,
  effective,
  activeArtifact,
  displayedNetwork,
  roadStatus,
  roadLabel,
  visibleAnnotations,
  reviewedRelations,
  selectedRelationPaths,
} from './state.js';
import { esc, fmt, icon, empty } from './ui.js';

// ponytail: a local equirectangular overview for a block, not a survey basemap.
// Use a tiled GIS renderer if the dataset grows beyond the documented local scope.
export function projection() {
  const points = entities().filter((e) => e.coordinates);
  if (!points.length) return null;
  const origin = points[0].coordinates,
    latitude = origin.latitude,
    longitude = origin.longitude;
  const meters = (c) => [
    (c.longitude - longitude) * 111195 * Math.cos((latitude * Math.PI) / 180),
    (c.latitude - latitude) * 111195,
  ];
  const xy = points.map((e) => meters(e.coordinates));
  const xs = xy.map((p) => p[0]),
    ys = xy.map((p) => p[1]);
  const mid = [(Math.max(...xs) + Math.min(...xs)) / 2, (Math.max(...ys) + Math.min(...ys)) / 2];
  const scale =
    Math.min(
      580 / Math.max(240, Math.max(...xs) - Math.min(...xs)),
      400 / Math.max(220, Math.max(...ys) - Math.min(...ys)),
    ) * state.zoom;
  return {
    scale,
    point: (c) => {
      const p = meters(c);
      return [380 + (p[0] - mid[0]) * scale, 300 - (p[1] - mid[1]) * scale];
    },
  };
}
const svgButton = (id, label, body) =>
  '<g role="button" tabindex="0" data-action="select" data-id="' +
  esc(id) +
  '" aria-label="' +
  esc(label) +
  '">' +
  body +
  '</g>';
export function mapSvg() {
  const proj = projection();
  if (!proj) return empty('还没有地图坐标', '导入含 WGS84 坐标的地图快照后，这里会显示空间对象。');
  const p = (id) => {
    const e = entity(id);
    return e?.coordinates ? proj.point(e.coordinates) : null;
  };
  const selected = p(state.selected),
    center = p(state.center),
    network = displayedNetwork();
  let body =
    '<defs><pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#263137" stroke-width=".6"/></pattern><marker id="direction" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto"><path d="m0 0 6 3-6 3" fill="#91b3ae"/></marker></defs><rect width="760" height="600" fill="#151e22"/><rect width="760" height="600" fill="url(#grid)"/>';
  if (state.layers.buffer && center)
    body +=
      '<circle cx="' +
      center[0] +
      '" cy="' +
      center[1] +
      '" r="' +
      state.radius * proj.scale +
      '" fill="#6dd5b0" fill-opacity=".035" stroke="#6dd5b0" stroke-opacity=".5" stroke-dasharray="5 6"/><text x="' +
      (center[0] + 12) +
      '" y="' +
      (center[1] - state.radius * proj.scale + 20) +
      '" fill="#98bcb0" font-size="11">' +
      state.radius +
      ' m · 查询范围</text>';
  if (state.layers.roads && network)
    for (const edge of network.snapshot.edges) {
      const a = p(edge.source),
        b = p(edge.target);
      if (!a || !b) continue;
      const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      const route = state.route?.edges?.some((e) => e.id === edge.id),
        status = roadStatus(edge),
        color = route
          ? '#74e8ba'
          : status === 'blocked'
            ? '#f18d7c'
            : status === 'unknown'
              ? '#89949a'
              : '#72a6a2';
      body +=
        '<polyline points="' +
        a.join(',') +
        ' ' +
        mid.join(',') +
        ' ' +
        b.join(',') +
        '" fill="none" stroke="' +
        color +
        '" stroke-width="' +
        (route ? 5 : 3) +
        '" ' +
        (status !== 'open' ? 'stroke-dasharray="7 6"' : '') +
        ' ' +
        (!edge.bidirectional ? 'marker-mid="url(#direction)"' : '') +
        '/><text x="' +
        (mid[0] + 8) +
        '" y="' +
        (mid[1] - 9) +
        '" fill="' +
        color +
        '" font-size="10">' +
        esc(roadLabel(edge, status) + (!edge.bidirectional ? ' · 单向' : '')) +
        '</text>';
    }
  if (state.layers.objects)
    for (const e of entities()) {
      const c = p(e.id);
      if (!c) continue;
      const is = e.id === state.selected,
        fill = e.kind === 'resource' ? '#6dd5b0' : e.kind === 'entrance' ? '#e7b969' : '#aab8c0';
      let symbol =
        e.kind === 'building'
          ? '<rect x="-24" y="-23" width="48" height="46" rx="2" fill="' +
            (is ? '#32473f' : '#354147') +
            '" stroke="' +
            fill +
            '"/><path d="M-16-16h32v32h-32Z" stroke="#65766e" fill="none"/>'
          : '<circle r="' +
            (e.kind === 'road' ? 5 : 9) +
            '" fill="#1b2d2d" stroke="' +
            fill +
            '" stroke-width="2"/>';
      if (e.kind === 'resource')
        symbol += '<path d="M-4 0h8M0-4v8" stroke="' + fill + '" stroke-width="2"/>';
      if (is)
        symbol +=
          '<circle r="37" fill="none" stroke="#6dd5b0" stroke-width="1"/><path d="M-45 0h8M37 0h8M0-45v8M0 37v8" stroke="#6dd5b0"/>';
      body += svgButton(
        e.id,
        e.name,
        '<g transform="translate(' +
          c.join(',') +
          ')">' +
          symbol +
          '<text x="0" y="' +
          (e.kind === 'building' ? 42 : 26) +
          '" text-anchor="middle" fill="#d5dfdf" stroke="#151e22" stroke-width="4" paint-order="stroke" font-size="12">' +
          esc(e.name) +
          '</text></g>',
      );
    }
  if (state.layers.evidence)
    for (const ann of visibleAnnotations()) {
      const a = effective(ann),
        c = p(a.entity_id);
      if (!c) continue;
      body += svgButton(
        a.entity_id,
        '查看 ' + (entity(a.entity_id)?.name || '') + ' 的证据',
        '<g transform="translate(' +
          (c[0] + 19) +
          ',' +
          (c[1] - 22) +
          ')"><rect x="-9" y="-9" width="18" height="18" rx="3" fill="' +
          (ann.status === 'approved' ? '#6dd5b0' : '#e7b969') +
          '"/><text text-anchor="middle" y="4" fill="#14201c" font-size="12" font-weight="700">' +
          (ann.status === 'approved' ? '✓' : '?') +
          '</text></g>',
      );
    }
  body +=
    '<path d="M32 552h' +
    50 * proj.scale +
    'm-' +
    50 * proj.scale +
    '-4v8m' +
    50 * proj.scale +
    '-8v8" stroke="#9caaa8"/><text x="32" y="540" fill="#9caaa8" font-size="10">50 m · 局部近似</text>';
  return (
    '<svg class="map-svg" viewBox="0 0 760 600" role="group" aria-label="空间对象地图，可用 Tab 选择对象">' +
    body +
    '</svg>'
  );
}
export function relationGraph() {
  const relation = activeArtifact('relation_set');
  if (!relation)
    return empty('没有有效的已审核关系图', '导入并审核关系快照后可查看对象之间的连接。');
  const rows = reviewedRelations(),
    paths = selectedRelationPaths();
  const ids = [...new Set(rows.flatMap((r) => [r.subject, r.object]))],
    n = ids.length;
  const pos = (id) => {
    const i = ids.indexOf(id),
      a = (2 * Math.PI * i) / n;
    return [380 + 210 * Math.cos(a), 290 + 180 * Math.sin(a)];
  };
  let body =
    '<defs><marker id="rel-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="m0 0 7 3-7 3" fill="#6b9d92"/></marker></defs>';
  for (const r of rows) {
    const a = pos(r.subject),
      b = pos(r.object),
      active = paths.has(r);
    body +=
      '<path d="M' +
      a +
      'L' +
      b +
      '" class="' +
      (active ? 'relation-active' : '') +
      '" stroke="' +
      (active ? '#f4bd6e' : '#5a8077') +
      '" stroke-width="' +
      (active ? 3 : 1) +
      '" fill="none" marker-end="url(#rel-arrow)"/><text x="' +
      (a[0] + b[0]) / 2 +
      '" y="' +
      ((a[1] + b[1]) / 2 - 8) +
      '" fill="#adc3bb" font-size="12">' +
      esc(r.predicate) +
      '</text>';
  }
  for (const id of ids) {
    const c = pos(id);
    body += svgButton(
      id,
      entity(id)?.name || id,
      '<rect x="' +
        (c[0] - 65) +
        '" y="' +
        (c[1] - 23) +
        '" width="130" height="46" rx="4" fill="#223632" stroke="' +
        (id === state.selected ? '#80e0b8' : '#487165') +
        '"/><text x="' +
        c[0] +
        '" y="' +
        (c[1] + 5) +
        '" text-anchor="middle" fill="#d1e5db" font-size="12">' +
        esc(entity(id)?.name || id) +
        '</text>',
    );
  }
  return (
    '<svg class="map-svg" viewBox="0 0 760 600" role="group" aria-label="已审核空间关系图">' +
    body +
    '</svg>'
  );
}
export function mapPanel() {
  return (
    '<section class="map-panel" aria-label="地图工作区"><div class="map-toolbar"><div class="segmented"><button data-action="map-view" data-value="map" aria-pressed="' +
    (state.mapView === 'map') +
    '">' +
    icon('map') +
    '地图</button><button data-action="map-view" data-value="graph" aria-pressed="' +
    (state.mapView === 'graph') +
    '">' +
    icon('link') +
    '关系图</button></div><span class="map-basis">' +
    (state.dataset?.snapshot.coordinate_basis === 'measured' ? '实测点位' : '演练坐标') +
    ' · WGS84</span></div><div class="map-drawing">' +
    (state.mapView === 'graph' ? relationGraph() : '<div id="gis-slot"></div>') +
    '</div><div class="compass"><b>N</b><span>↑</span></div><div class="zoom"><button aria-label="放大地图" data-action="gis-zoom" data-value="1">' +
    icon('plus') +
    '</button><button aria-label="缩小地图" data-action="gis-zoom" data-value="-1">' +
    icon('minus') +
    '</button><button aria-label="重置地图视野" data-action="fit-map">' +
    icon('scan') +
    '</button></div><div class="map-foot"><span><i class="dot mint"></i>已审核</span><span><i class="dot amber"></i>候选</span><span><i class="dash"></i>封闭 / 未知</span><small>' +
    (state.client ? 'WGS84 · 审核路网' : '合成演练图层') +
    '</small></div></section>'
  );
}
