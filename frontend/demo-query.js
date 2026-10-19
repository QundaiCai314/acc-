import { state, entities, entity, effective } from './state.js';
export function distance(a, b) {
  const rad = (v) => (v * Math.PI) / 180;
  const dlat = rad(b.latitude - a.latitude),
    dlon = rad(b.longitude - a.longitude);
  return (
    6371008.8 *
    2 *
    Math.asin(
      Math.sqrt(
        Math.sin(dlat / 2) ** 2 +
          Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude)) * Math.sin(dlon / 2) ** 2,
      ),
    )
  );
}
export function demoQuery(payload) {
  const center = entity(payload.center_entity_id);
  if (!center?.coordinates) throw new Error('查询中心缺少坐标，请选择有坐标的对象。');
  const citations = [];
  let older = 0;
  for (const a of state.annotations) {
    const observation = effective(a),
      e = entity(observation.entity_id),
      img = state.images.find((i) => i.id === a.image_id);
    if (
      a.status !== 'approved' ||
      !e?.coordinates ||
      e.kind !== payload.kind ||
      observation.observation !== payload.observation ||
      !img
    )
      continue;
    const d = distance(center.coordinates, e.coordinates),
      age = (new Date(payload.as_of) - new Date(img.captured_at)) / 3600000;
    if (d > payload.radius_m || age < 0) continue;
    if (age > payload.max_age_hours) {
      older++;
      continue;
    }
    citations.push({
      annotation_id: a.id,
      image_id: img.id,
      entity_id: e.id,
      entity_name: e.name,
      coordinates: e.coordinates,
      distance_m: d,
      captured_at: img.captured_at,
      source: img.source,
      evidence_basis: img.evidence_basis,
      origin: a.origin,
      annotation: observation,
      reviewer: a.review.reviewer,
      review_note: a.review.note,
      reviewed_at: a.review.created_at,
    });
  }
  citations.sort((a, b) => a.distance_m - b.distance_m);
  return {
    status: citations.length ? 'evidence_found' : 'insufficient_evidence',
    answer:
      '【离线演练】' +
      (citations.length
        ? '在当前范围与时间窗内找到 ' +
          citations.length +
          ' 条已审核障碍物记录：' +
          citations.map((c, i) => c.entity_name + ' [' + (i + 1) + ']').join('、')
        : '未找到满足条件的已审核证据。') +
      (older ? ' 另有 ' + older + ' 条更早记录，可扩大时间范围查看。' : ''),
    query: payload,
    citations,
    older_evidence_count: older,
    limitations: [
      '演练插画与合成坐标，仅验证交互。',
      '距离为球面点位距离；不表示道路距离或通行安全。',
    ],
  };
}
export function demoRoute(q) {
  const net = state.artifacts.find((a) => a.id === q.network_id);
  if (
    !net ||
    net.status !== 'approved' ||
    new Date(q.as_of) < new Date(net.snapshot.valid_from) ||
    new Date(q.as_of) > new Date(net.snapshot.valid_until)
  )
    throw new Error('路网未审核、已撤回或超出有效期，请核对快照与查询时间。');
  const edges = [],
    excluded = [];
  for (const e of net.snapshot.edges) {
    if (e.status !== 'open' || !e.modes.includes(q.mode)) {
      excluded.push({ edge_id: e.id, reason: e.status !== 'open' ? e.status : 'mode_not_allowed' });
      continue;
    }
    edges.push(e);
  }
  const dist = new Map([[q.start_entity_id, 0]]),
    prev = new Map(),
    todo = new Set(entities().map((e) => e.id));
  while (todo.size) {
    const id = [...todo].sort((a, b) => (dist.get(a) ?? Infinity) - (dist.get(b) ?? Infinity))[0];
    todo.delete(id);
    if (!dist.has(id)) break;
    if (id === q.end_entity_id) break;
    for (const e of edges) {
      const next =
        e.source === id ? e.target : e.bidirectional && e.target === id ? e.source : null;
      if (!next) continue;
      const d = dist.get(id) + e.length_m;
      if (d < (dist.get(next) ?? Infinity)) {
        dist.set(next, d);
        prev.set(next, { id, edge: e });
      }
    }
  }
  if (!dist.has(q.end_entity_id))
    return {
      status: 'unreachable',
      distance_m: null,
      entity_ids: [],
      edges: [],
      excluded_edges: excluded,
    };
  const path = [q.end_entity_id],
    pathEdges = [];
  let id = q.end_entity_id;
  while (id !== q.start_entity_id) {
    const p = prev.get(id);
    path.unshift(p.id);
    pathEdges.unshift(p.edge);
    id = p.id;
  }
  return {
    status: 'reachable',
    distance_m: dist.get(q.end_entity_id),
    entity_ids: path,
    edges: pathEdges,
    excluded_edges: excluded,
    note: '离线演练路网，不表示安全通行',
  };
}
