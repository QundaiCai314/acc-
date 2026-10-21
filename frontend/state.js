import { makeDemo } from './demo.js';
export const state = {
  ...makeDemo(),
  datasets: [],
  client: null,
  identity: { user_id: '演练操作员', role: 'admin', workspace: '离线演练' },
  screen: 'command',
  selected: 'east',
  annotationId: 'ann-east',
  artifactId: 'reg-demo',
  search: '',
  hours: 24,
  radius: 100,
  center: 'building-a',
  asOf: new Date().toISOString(),
  layers: { objects: true, roads: true, evidence: true, buffer: true },
  zoom: 1,
  mapView: 'map',
  angle: 35,
  point: '',
  answer: null,
  route: null,
  references: null,
  busy: false,
  error: '',
  revision: 0,
};
export const entities = () => state.dataset?.snapshot.entities || [];
export const entity = (id) => entities().find((e) => e.id === id);
export const effective = (a) => a.review?.approved_annotation || a.annotation;
export const canReview = () => ['admin', 'reviewer'].includes(state.identity.role);
export const canWrite = () => state.identity.role !== 'viewer';
export const activeArtifact = (kind) =>
  state.artifacts.find(
    (a) =>
      a.artifact_type === kind &&
      a.status === 'approved' &&
      new Date(a.snapshot.valid_from) <= new Date(state.asOf) &&
      new Date(a.snapshot.valid_until) >= new Date(state.asOf),
  );
export const visibleAnnotations = () =>
  state.annotations.filter((a) => {
    const img = state.images.find((i) => i.id === a.image_id);
    const age = (new Date(state.asOf) - new Date(img?.captured_at)) / 3600000;
    return age >= 0 && age <= state.hours;
  });
export function reviewedRelations() {
  const approved = new Set(
    visibleAnnotations()
      .filter((a) => a.status === 'approved')
      .map((a) => a.id),
  );
  return (activeArtifact('relation_set')?.snapshot.relations || []).filter((r) =>
    (r.annotation_ids || []).every((id) => approved.has(id)),
  );
}
// Highlight explicit paths only; blocks is never transitive. The backend decides query matches.
export function selectedRelationPaths() {
  const rows = reviewedRelations(),
    chosen = new Set();
  for (const predicate of ['part_of', 'inside', 'connects_to', 'blocks']) {
    const seen = new Set([state.selected]);
    let frontier = [state.selected];
    for (let hop = 0; hop < (predicate === 'blocks' ? 1 : 4) && frontier.length; hop++) {
      const next = [];
      for (const id of frontier)
        for (const r of rows) {
          if (r.predicate !== predicate) continue;
          const other =
            r.subject === id
              ? r.object
              : predicate === 'connects_to' && r.object === id
                ? r.subject
                : null;
          if (!other) continue;
          chosen.add(r);
          if (!seen.has(other)) {
            seen.add(other);
            next.push(other);
          }
        }
      frontier = next;
    }
  }
  return chosen;
}
Object.assign(state, {
  showLayers: false,
  showIntel: false,
  showObjects: false,
  showTimeline: true,
  showGraph: true,
  basemap: true,
  cameraImage: null,
  hoverCamera: null,
  endAge: 0,
  timelineBase: Date.now(),
  playing: false,
  reviewFilter: 'all',
  reviewLabel: 'all',
  minConfidence: 0,
  imageZoom: 1,
  compareBoxes: true,
  drawBox: false,
  lease: null,
  leaseKnown: false,
  artTheme: 'vellum',
});
state.layers.cameras = true;
export function clearResults() {
  state.answer = null;
  state.route = null;
  state.references = null;
  state.revision++;
}
export function resetSelection() {
  state.selected = entities()[0]?.id || '';
  state.center = state.selected;
  state.annotationId = state.annotations[0]?.id;
  state.artifactId = state.artifacts.find((a) => a.artifact_type === 'registration')?.id;
  state.zoom = 1;
  state.hours = 24;
  state.endAge = 0;
  state.timelineBase = Date.now();
  state.asOf = new Date().toISOString();
  state.fixedTime = false;
  state.leaseKey = null;
  state.lease = null;
  state.leaseKnown = false;
  clearResults();
}
