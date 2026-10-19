import { Client } from './api.js';
import { makeDemo } from './demo.js';
import { demoQuery, demoRoute } from './demo-query.js';
import { state, entities, entity, canWrite, clearResults, resetSelection } from './state.js';
import { esc, icon, notify, options } from './ui.js';
import * as view from './views.js';
import * as bench from './workbench.js';
import { detachMap, mountMap, updateMap, fitMap, focusMap, zoomMap } from './gis.js';
import { detachScene, mountScene } from './scene.js';
import { cameraPayload } from './camera.js';

const pages = {
  command: bench.command,
  import: view.importPage,
  analysis: bench.analysis,
  review: bench.review,
  registration: view.registration,
  plans: view.plans,
  reason: view.reason,
  field: view.field,
};
const app = document.querySelector('#app'),
  dialog = document.querySelector('#dialog');
const datasetPath = () => {
  if (!state.dataset) throw new Error('请先选择或建立一个现场。');
  return '/spatial/datasets/' + encodeURIComponent(state.dataset.id);
};
const requireLive = () => {
  if (!state.client) throw new Error('当前为离线演练。请点击「连接设置」连接后端，再执行此操作。');
  return state.client;
};
function render() {
  const context =
    state.screen +
    '|' +
    (state.client?.base || 'demo') +
    '|' +
    state.identity.user_id +
    '|' +
    state.dataset?.id +
    '|' +
    (state.screen === 'review'
      ? state.annotationId +
        '|' +
        state.annotations.find((a) => a.id === state.annotationId)?.status
      : '');
  const drafts = render.context === context ? captureQueryForms() : [];
  detachMap();
  detachScene();
  app.innerHTML = view.shell((pages[state.screen] || pages.command)());
  for (const draft of drafts) {
    const form = document.getElementById(draft.id);
    if (!form) continue;
    if (draft.conditions) form.querySelector('#conditions').innerHTML = draft.conditions;
    const controls = [...form.querySelectorAll('input,select,textarea')];
    draft.values.forEach((v, i) => {
      const c = controls[i];
      if (c && (c.tagName !== 'SELECT' || [...c.options].some((o) => o.value === v))) c.value = v;
    });
  }
  render.context = context;
  hydrateImages();
  mountMap();
  mountScene();
  hydrateReview();
}
function captureQueryForms() {
  return ['ask-form', 'route-form', 'reason-form', 'review-form']
    .map((id) => document.getElementById(id))
    .filter(Boolean)
    .map((f) => ({
      id: f.id,
      conditions: f.querySelector('#conditions')?.innerHTML,
      values: [...f.querySelectorAll('input,select,textarea')].map((c) => c.value),
    }));
}
async function hydrateReview() {
  if (state.screen !== 'review') return;
  const a = state.annotations.find((a) => a.id === state.annotationId);
  if (!a) return;
  const overlay = document.querySelector('.annotation-canvas .box-overlay');
  if (overlay) {
    const field = (n) => Number(document.querySelector('#review-form [name=' + n + ']')?.value);
    const box = overlay.querySelector('rect');
    box.setAttribute('x', field('x_min') * 100);
    box.setAttribute('y', field('y_min') * 100);
    box.setAttribute('width', (field('x_max') - field('x_min')) * 100);
    box.setAttribute('height', (field('y_max') - field('y_min')) * 100);
  }
  if (overlay && state.compareBoxes) {
    const b = a.annotation.bbox;
    overlay.insertAdjacentHTML(
      'beforeend',
      '<rect class="original-box" x="' +
        b.x_min * 100 +
        '" y="' +
        b.y_min * 100 +
        '" width="' +
        (b.x_max - b.x_min) * 100 +
        '" height="' +
        (b.y_max - b.y_min) * 100 +
        '"/>',
    );
  }
  if (state.client && a.status === 'pending_review' && state.leaseKey !== a.id) {
    state.leaseKey = a.id;
    state.lease = null;
    state.leaseKnown = false;
    const client = state.client;
    try {
      const result = await client.request('/spatial/annotations/' + a.id + '/lease');
      if (state.client === client && state.annotationId === a.id) {
        state.lease = result.lease;
        state.leaseKnown = true;
        render();
      }
    } catch (e) {
      state.leaseKey = null;
      notify('无法读取审核占用状态，请刷新后重试。', true);
    }
  }
}
async function hydrateImages() {
  const client = state.client;
  if (!client) return;
  await Promise.allSettled(
    [...document.querySelectorAll('img[data-image]')].map(async (image) => {
      try {
        const url = await client.image(image.dataset.image);
        if (image.isConnected && state.client === client) image.src = url;
      } catch (e) {
        if (image.isConnected) {
          const msg = document.createElement('p');
          msg.className = 'image-error';
          msg.textContent = '图片读取失败，请刷新重试。';
          image.replaceWith(msg);
        }
      }
    }),
  );
}
async function work(fn) {
  if (state.busy) return;
  state.busy = true;
  state.error = '';
  const buttons = [...document.querySelectorAll('button')].filter((b) => !b.disabled);
  buttons.forEach((b) => (b.disabled = true));
  document.querySelector('main')?.setAttribute('aria-busy', 'true');
  notify('正在处理，请稍候…');
  try {
    await fn();
    state.busy = false;
    render();
    notify('操作完成。');
  } catch (e) {
    state.busy = false;
    state.error = e.message;
    buttons.forEach((b) => (b.disabled = false));
    document.querySelector('main')?.setAttribute('aria-busy', 'false');
    notify(e.message, true);
    if (dialog.open) {
      let error = dialog.querySelector('[role=alert]');
      if (!error) {
        error = document.createElement('p');
        error.setAttribute('role', 'alert');
        error.className = 'error-banner';
        dialog.append(error);
      }
      error.textContent = e.message;
    }
  }
}
async function loadDataset(id, client = state.client) {
  if (!id) return { dataset: null, images: [], annotations: [], artifacts: [] };
  const path = '/spatial/datasets/' + encodeURIComponent(id);
  const results = await Promise.allSettled([
    client.request(path),
    client.list(path + '/images', 'images'),
    client.list(path + '/annotations', 'annotations'),
    client.list(path + '/artifacts', 'artifacts'),
  ]);
  const failure = results.find((r) => r.status === 'rejected');
  if (failure) throw failure.reason;
  const [dataset, images, annotations, artifacts] = results.map((r) => r.value);
  return { dataset, images, annotations, artifacts };
}
async function refresh() {
  if (!state.client) return;
  const data = await loadDataset(state.dataset?.id);
  Object.assign(state, data);
  state.leaseKey = null;
  state.lease = null;
  state.leaseKnown = false;
  if (!state.fixedTime) state.asOf = new Date().toISOString();
  clearResults();
}
function go(screen) {
  location.hash = screen;
}
function modal(html) {
  dialog.innerHTML =
    '<button type="button" class="dialog-close icon-button" data-action="close-dialog" aria-label="关闭">' +
    icon('close') +
    '</button>' +
    html;
  dialog.showModal();
}
function connectDialog() {
  modal(
    '<span class="eyebrow">WORKSPACE CONNECTION</span><h2>连接你的指挥台后端</h2><p class="muted">个人令牌仅保存在当前页面内存中。刷新页面后需要重新连接。</p><form id="connect-form"><label>后端地址<input name="base" type="url" required value="' +
      esc(state.client?.base || 'http://127.0.0.1:8000') +
      '"></label><label>个人访问令牌<input name="token" type="password" autocomplete="off" placeholder="本机 local 模式可留空"></label><button class="button primary full">连接并读取现场</button></form><p class="meta">跨域部署需在后端 DISASTER_CORS_ORIGINS 中允许当前页面来源。团队远程连接使用 HTTPS。</p>' +
      (state.client
        ? '<button class="button danger full" data-action="disconnect">断开连接，回到离线演练</button>'
        : ''),
  );
}
function datasetsDialog() {
  if (!state.client) {
    connectDialog();
    return;
  }
  modal(
    '<h2>选择工作现场</h2><form id="select-dataset-form"><label>当前工作空间内的现场<select name="id" required>' +
      options(
        state.datasets.map((d) => [d.id, d.snapshot.title]),
        state.dataset?.id,
      ) +
      '</select></label><button class="button primary full" ' +
      (!state.datasets.length ? 'disabled' : '') +
      '>打开现场</button></form><p class="muted">没有现场时，可到「资料导入」建立地图快照。</p>',
  );
}
async function readJSON(file) {
  if (!file?.size) throw new Error('请选择 JSON 文件。');
  if (file.size > 7000000) throw new Error('JSON 超过 7 MB，请缩小文件。');
  try {
    return JSON.parse(await file.text());
  } catch {
    throw new Error('JSON 格式无效，请检查文件后重试。');
  }
}
function download(kind) {
  const demo = makeDemo(),
    mapping = {
      networks: 'road_network',
      registrations: 'registration',
      relations: 'relation_set',
    };
  const payload =
    kind === 'dataset'
      ? demo.dataset.snapshot
      : demo.artifacts.find((a) => a.artifact_type === mapping[kind]).snapshot;
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }),
  );
  const a = document.createElement('a');
  a.href = url;
  a.download = 'exercise-' + kind + '.json';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function query() {
  if (state.client && !state.fixedTime) state.asOf = new Date().toISOString();
  const payload = {
    center_entity_id: state.center,
    radius_m: state.radius,
    kind: 'entrance',
    observation: 'obstacle_visible',
    as_of: state.asOf,
    max_age_hours: state.hours,
  };
  state.answer = state.client
    ? await state.client.request(datasetPath() + '/query', payload)
    : demoQuery(payload);
}
function setSelection(id) {
  state.selected = id;
  const ann = state.annotations.find(
    (a) => (a.review?.approved_annotation || a.annotation).entity_id === id,
  );
  if (ann) state.cameraImage = ann.image_id;
  render();
  focusMap(id);
}
const actions = {
  'toggle-branch': (button) => {
    const collapsed = new Set(state.collapsedBranches || []);
    collapsed.has(button.dataset.id)
      ? collapsed.delete(button.dataset.id)
      : collapsed.add(button.dataset.id);
    state.collapsedBranches = [...collapsed];
    render();
  },
  connect: connectDialog,
  'close-dialog': () => dialog.close(),
  datasets: () =>
    work(async () => {
      if (state.client) state.datasets = await state.client.list('/spatial/datasets', 'datasets');
      datasetsDialog();
    }),
  disconnect: () => {
    state.client?.dispose();
    Object.assign(state, makeDemo(), {
      client: null,
      datasets: [],
      identity: { user_id: '演练操作员', role: 'admin', workspace: '离线演练' },
    });
    resetSelection();
    dialog.close();
    render();
  },
  refresh: () => work(refresh),
  'dismiss-error': () => {
    state.error = '';
    render();
  },
  select: (b) => setSelection(b.dataset.id),
  annotation: (b) => {
    state.annotationId = b.dataset.id;
    state.reviewFilter = 'all';
    state.minConfidence = 0;
    state.reviewLabel = 'all';
    state.leaseKey = null;
    go('review');
  },
  'review-select': (b) => {
    state.annotationId = b.dataset.id;
    state.lease = null;
    state.leaseKey = null;
    state.leaseKnown = false;
    render();
  },
  'map-view': (b) => {
    state.mapView = b.dataset.value;
    render();
  },
  zoom: (b) => {
    state.zoom =
      b.dataset.value === 'reset'
        ? 1
        : Math.min(4, Math.max(0.4, state.zoom * Number(b.dataset.value)));
    render();
  },
  point: (b) => {
    state.point = b.dataset.id;
    render();
  },
  download: (b) => download(b.dataset.kind),
  query: () => work(query),
  'add-condition': () => {
    const holder = document.querySelector('#conditions');
    if (holder.children.length < 12)
      holder.insertAdjacentHTML('beforeend', view.conditionRow(holder.children.length));
  },
  'remove-condition': (b) => {
    if (document.querySelectorAll('.condition-row').length > 1)
      b.closest('.condition-row').remove();
  },
  'toggle-layers': () => {
    state.showLayers = !state.showLayers;
    render();
  },
  'toggle-intel': () => {
    state.showIntel = !state.showIntel;
    render();
  },
  'fit-map': fitMap,
  'focus-center': () => focusMap(state.center),
  'gis-zoom': (b) => zoomMap(Number(b.dataset.value)),
  'reset-radius': () => {
    state.radius = 100;
    clearResults();
    render();
  },
  'close-pip': () => {
    state.cameraImage = null;
    render();
  },
  'review-filter': (b) => {
    state.reviewFilter = b.dataset.value;
    state.annotationId = bench.reviewRows()[0]?.id;
    state.leaseKey = null;
    render();
  },
  'review-reset': () => {
    state.reviewFilter = 'all';
    state.reviewLabel = 'all';
    state.minConfidence = 0;
    render();
  },
  'gallery-status': (b) => {
    state.galleryStatus = b.dataset.value;
    render();
  },
  'image-zoom': (b) => {
    state.imageZoom = Math.min(3, Math.max(0.5, state.imageZoom + Number(b.dataset.value)));
    render();
  },
  'draw-box': () => {
    state.drawBox = !state.drawBox;
    render();
  },
  'compare-boxes': () => {
    state.compareBoxes = !state.compareBoxes;
    render();
  },
  'time-now': () => {
    stopPlayback();
    state.timelineBase = Date.now();
    state.endAge = 0;
    state.fixedTime = false;
    state.asOf = new Date().toISOString();
    clearResults();
    render();
  },
  'play-time': () => {
    if (state.playing) {
      stopPlayback();
      render();
      return;
    }
    state.playing = true;
    if (!state.endAge) state.endAge = Math.max(1, 72 - state.hours);
    playback = setInterval(() => {
      state.endAge = Math.max(0, state.endAge - 1);
      setTimeWindow();
      if (!state.endAge) stopPlayback();
      render();
    }, 1100);
    render();
  },
  lease: (b) =>
    work(async () => {
      const a = state.annotations.find((a) => a.id === state.annotationId);
      if (!a) return;
      if (state.client) {
        const held =
          state.lease &&
          new Date(state.lease.expires_at) > new Date() &&
          state.lease.user_id !== state.identity.user_id;
        const result = await state.client.request(
          '/spatial/annotations/' + a.id + '/' + (held ? 'lease' : b.dataset.value),
          held ? undefined : {},
        );
        state.lease = result.lease;
      } else
        state.lease =
          b.dataset.value === 'release'
            ? null
            : {
                user_id: state.identity.user_id,
                expires_at: new Date(Date.now() + 300000).toISOString(),
              };
      state.leaseKey = a.id;
      state.leaseKnown = true;
    }),
  citation: (b) => {
    const evidence = state.answer?.evidence || state.answer;
    const citations =
      evidence?.citations || evidence?.matches?.flatMap((m) => m.image_citations) || [];
    const c = citations[Number(b.dataset.index)];
    if (!c) return;
    state.selected = c.entity_id || c.annotation.entity_id;
    state.cameraImage = c.image_id;
    state.activeCitation = Number(b.dataset.index);
    render();
    focusMap(state.selected);
    document
      .querySelector('.citation[data-index="' + b.dataset.index + '"]')
      ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  },
  analyze: (b) =>
    work(async () => {
      const client = requireLive(),
        id = b.dataset.id;
      const key = crypto.randomUUID();
      const result = await client.request(
        '/spatial/images/' + encodeURIComponent(id) + '/analyze',
        {},
        { 'Idempotency-Key': key },
      );
      await refresh();
      state.annotationId = result.annotations[0]?.id || state.annotationId;
      state.screen = 'review';
      history.replaceState(null, '', '#review');
    }),
};
let playback;
function stopPlayback() {
  clearInterval(playback);
  state.playing = false;
}
function setTimeWindow() {
  state.hours = Math.max(1, Math.min(72 - state.endAge, state.hours));
  state.asOf = new Date(state.timelineBase - state.endAge * 3600000).toISOString();
  state.fixedTime = true;
  clearResults();
}
window.addEventListener('gis-select', (e) => setSelection(e.detail));
window.addEventListener('camera-select', (e) => {
  state.cameraImage = e.detail;
  const ann = state.annotations.find((a) => a.image_id === e.detail);
  if (ann) state.selected = (ann.review?.approved_annotation || ann.annotation).entity_id;
  render();
});
window.addEventListener('scene-point', (e) => {
  state.point = e.detail;
  render();
});
document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-action]');
  if (!b || b.disabled || state.busy) return;
  actions[b.dataset.action]?.(b);
});
document.addEventListener('keydown', (e) => {
  if (e.target.matches('svg [role="button"]') && ['Enter', ' '].includes(e.key)) {
    e.preventDefault();
    e.target.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  }
});
document.addEventListener('keydown', (e) => {
  if (
    state.screen !== 'review' ||
    state.busy ||
    dialog.open ||
    e.target.closest('input,textarea,select,[contenteditable=true]')
  )
    return;
  const rows = bench.reviewRows(),
    index = rows.findIndex((a) => a.id === state.annotationId);
  if (['ArrowLeft', 'ArrowRight'].includes(e.key)) {
    e.preventDefault();
    const next = rows[index + (e.key === 'ArrowRight' ? 1 : -1)];
    if (next) {
      state.annotationId = next.id;
      state.leaseKey = null;
      state.leaseKnown = false;
      state.lease = null;
      render();
    }
  }
  const form = document.querySelector('#review-form');
  if (!form) return;
  if (['1', '2', '3'].includes(e.key)) {
    const select = form.querySelector('[name=observation]');
    if (!select.disabled) {
      select.value = ['obstacle_visible', 'no_obstacle_visible', 'unknown'][Number(e.key) - 1];
      e.preventDefault();
    }
  }
  if ([' ', 'Backspace'].includes(e.key)) {
    const button = form.querySelector('[value="' + (e.key === ' ' ? 'approve' : 'reject') + '"]');
    if (button && !button.disabled) {
      e.preventDefault();
      form.requestSubmit(button);
    }
  }
});
let drawing;
document.addEventListener('pointerdown', (e) => {
  const photo = e.target.closest('.annotation-canvas .evidence-photo');
  if (!photo || !state.drawBox || e.button !== 0 || state.busy) return;
  const form = document.querySelector('#review-form');
  if (form?.querySelector('fieldset').disabled) return;
  const rect = photo.getBoundingClientRect();
  drawing = {
    photo,
    rect,
    start: [(e.clientX - rect.left) / rect.width, (e.clientY - rect.top) / rect.height],
  };
  photo.setPointerCapture(e.pointerId);
  e.preventDefault();
});
document.addEventListener('pointermove', (e) => {
  if (!drawing) return;
  const { rect, start, photo } = drawing,
    clamp = (v) => Math.max(0, Math.min(1, v)),
    x = clamp((e.clientX - rect.left) / rect.width),
    y = clamp((e.clientY - rect.top) / rect.height);
  const box = {
    x_min: Math.min(start[0], x),
    y_min: Math.min(start[1], y),
    x_max: Math.max(start[0], x),
    y_max: Math.max(start[1], y),
  };
  for (const [key, value] of Object.entries(box))
    document.querySelector('#review-form [name=' + key + ']').value = value.toFixed(3);
  const overlay = photo.querySelector('.box-overlay rect');
  overlay.setAttribute('x', box.x_min * 100);
  overlay.setAttribute('y', box.y_min * 100);
  overlay.setAttribute('width', (box.x_max - box.x_min) * 100);
  overlay.setAttribute('height', (box.y_max - box.y_min) * 100);
});
document.addEventListener('pointerup', () => {
  drawing = null;
});
document.addEventListener('pointercancel', () => {
  drawing = null;
});
document.addEventListener('input', (e) => {
  if (e.target.id === 'entity-search') {
    const start = e.target.selectionStart;
    state.search = e.target.value;
    render();
    const input = document.querySelector('#entity-search');
    input.focus();
    input.setSelectionRange(start, start);
  }
  if (['windowStart', 'endAge'].includes(e.target.dataset.control)) {
    const value = Number(e.target.value);
    if (e.target.dataset.control === 'windowStart') state.hours = Math.max(1, value - state.endAge);
    else {
      const startAge = state.hours + state.endAge;
      state.endAge = Math.min(startAge - 1, value);
      state.hours = startAge - state.endAge;
      e.target.value = state.endAge;
    }
    setTimeWindow();
    updateMap();
  }
});
document.addEventListener('change', (e) => {
  const t = e.target;
  if (state.busy) return;
  if (t.dataset.galleryLabel) {
    const labels = new Set(
      state.galleryLabels || ['obstacle_visible', 'no_obstacle_visible', 'unknown'],
    );
    t.checked ? labels.add(t.dataset.galleryLabel) : labels.delete(t.dataset.galleryLabel);
    state.galleryLabels = [...labels];
    render();
    return;
  }
  if (t.dataset.layer) {
    state.layers[t.dataset.layer] = t.checked;
    render();
    return;
  }
  const key = t.dataset.control;
  if (!key) return;
  if (key === 'basemap') state.basemap = t.checked;
  else if (key === 'windowStart' || key === 'endAge') {
    setTimeWindow();
  } else if (key === 'galleryConfidence') {
    state.galleryConfidence = Number(t.value);
  } else if (key === 'minConfidence') {
    state.minConfidence = Number(t.value);
    state.annotationId = bench.reviewRows()[0]?.id;
    state.leaseKey = null;
  } else if (key === 'reviewLabel') {
    state.reviewLabel = t.value;
    state.annotationId = bench.reviewRows()[0]?.id;
    state.leaseKey = null;
  } else if (key === 'registration') {
    state.artifactId = t.value;
    state.point = '';
  } else if (key === 'asOf') {
    if (!t.value) return;
    state.asOf = new Date(t.value).toISOString();
    state.fixedTime = true;
    clearResults();
  } else if (['radius', 'hours', 'angle'].includes(key)) {
    state[key] = Number(t.value);
    if (key !== 'angle') clearResults();
  } else {
    state[key] = t.value;
    clearResults();
  }
  render();
});

const submits = {
  'connect-form': async (f, d) => {
    const candidate = new Client(d.get('base'), d.get('token').trim());
    try {
      const identity = await candidate.request('/auth/me');
      const datasets = await candidate.list('/spatial/datasets', 'datasets');
      const data = await loadDataset(datasets[0]?.id, candidate);
      state.client?.dispose();
      Object.assign(state, data, { client: candidate, identity, datasets, search: '' });
      resetSelection();
      dialog.close();
    } catch (e) {
      candidate.dispose();
      throw e;
    }
  },
  'select-dataset-form': async (f, d) => {
    Object.assign(state, await loadDataset(d.get('id')));
    resetSelection();
    dialog.close();
  },
  'dataset-form': async (f, d) => {
    const client = requireLive();
    const payload = await readJSON(d.get('file'));
    const result = await client.request('/spatial/datasets', payload);
    state.datasets = await client.list('/spatial/datasets', 'datasets');
    Object.assign(state, await loadDataset(result.id));
    resetSelection();
  },
  'image-form': async (f, d) => {
    const client = requireLive(),
      file = d.get('file');
    if (!file.size || file.size > 5000000 || !['image/png', 'image/jpeg'].includes(file.type))
      throw new Error('请选择不超过 5 MB 的 PNG 或 JPEG 图片。');
    const base64 = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onerror = () => reject(new Error('读取图片失败，请重新选择文件。'));
      reader.readAsDataURL(file);
    });
    await client.request(datasetPath() + '/images', {
      name: file.name,
      captured_at: new Date(d.get('captured_at')).toISOString(),
      source: d.get('source'),
      evidence_basis: d.get('evidence_basis'),
      mime_type: file.type,
      content_base64: base64,
      camera_pose: cameraPayload(d),
    });
    await refresh();
  },
  'ask-form': async (f, d) => {
    const client = requireLive(),
      kind = d.get('kind');
    if (kind === 'references/search') {
      state.references = await client.request(datasetPath() + '/' + kind, {
        query: d.get('question'),
        max_results: 5,
      });
    } else {
      const answer = await client.request(datasetPath() + '/' + kind, {
        question: d.get('question'),
      });
      state.answer = answer;
    }
  },
  'route-form': async (f, d) => {
    const payload = {
      network_id: d.get('network_id'),
      start_entity_id: d.get('start_entity_id'),
      end_entity_id: d.get('end_entity_id'),
      mode: d.get('mode'),
      as_of: new Date(d.get('as_of')).toISOString(),
    };
    state.route = state.client
      ? await state.client.request(datasetPath() + '/route', payload)
      : demoRoute(payload);
  },
  'review-form': async (f, d, decision) => {
    const a = state.annotations.find((r) => r.id === state.annotationId);
    if (!a) throw new Error('未找到候选，请刷新后重试。');
    if (!d.get('note')?.trim()) throw new Error('请填写审核或撤回说明。');
    const payload = { reviewer: state.identity.user_id, note: d.get('note') };
    if (decision !== 'withdraw') payload.action = decision;
    if (decision === 'approve') {
      const bbox = Object.fromEntries(
        ['x_min', 'y_min', 'x_max', 'y_max'].map((k) => [k, Number(d.get(k))]),
      );
      if (bbox.x_min >= bbox.x_max || bbox.y_min >= bbox.y_max)
        throw new Error('标注框的最小坐标必须小于最大坐标。');
      payload.corrected_annotation = {
        ...a.annotation,
        entity_id: d.get('entity_id'),
        observation: d.get('observation'),
        description: d.get('description'),
        bbox,
      };
    }
    if (state.client) {
      await state.client.request(
        '/spatial/annotations/' + a.id + '/' + (decision === 'withdraw' ? 'withdraw' : 'review'),
        payload,
      );
      await refresh();
    } else {
      a.status = { approve: 'approved', reject: 'rejected', withdraw: 'withdrawn' }[decision];
      if (decision !== 'withdraw')
        a.review = {
          ...payload,
          approved_annotation: decision === 'approve' ? payload.corrected_annotation : null,
          created_at: new Date().toISOString(),
        };
      clearResults();
    }
  },
  'artifact-form': async (f, d) => {
    const client = requireLive();
    const payload = await readJSON(d.get('file'));
    const record = await client.request(datasetPath() + '/' + f.dataset.kind, payload);
    await refresh();
    if (f.dataset.kind === 'registrations') state.artifactId = record.id;
  },
  'artifact-review-form': async (f, d, decision) => {
    const id = f.dataset.id,
      note = d.get('note');
    if (state.client) {
      await state.client.request(
        '/spatial/artifacts/' + id + '/' + (decision === 'withdraw' ? 'withdraw' : 'review'),
        decision === 'withdraw'
          ? { note, reviewer: state.identity.user_id }
          : { action: decision, note },
      );
      await refresh();
    } else {
      const a = state.artifacts.find((r) => r.id === id);
      a.status = { approve: 'approved', reject: 'rejected', withdraw: 'withdrawn' }[decision];
      if (decision !== 'withdraw')
        a.review = { reviewer: state.identity.user_id, note, created_at: new Date().toISOString() };
      clearResults();
    }
  },
  'reason-form': async (f, d) => {
    const client = requireLive();
    const all_of = [...f.querySelectorAll('.condition-row')].map((row) => {
      const relation = row.querySelector('[name=relation]').value;
      return {
        relation,
        reference_entity_id: row.querySelector('[name=reference]').value,
        ...(relation === 'near'
          ? { distance_m: Number(row.querySelector('[name=distance]').value) }
          : {}),
      };
    });
    const payload = { all_of, as_of: state.asOf, mode: d.get('mode'), max_age_hours: state.hours };
    for (const k of ['kind', 'network_id', 'relation_set_id', 'registration_id'])
      if (d.get(k)) payload[k] = d.get(k);
    state.answer = await client.request(datasetPath() + '/reason', payload);
  },
  'observation-form': async (f, d) => {
    const client = requireLive();
    await client.request(datasetPath() + '/annotations', {
      image_id: d.get('image_id'),
      source_note: d.get('source_note'),
      annotation: {
        entity_id: d.get('entity_id'),
        observation: d.get('observation'),
        description: d.get('description'),
        confidence: 0,
        bbox: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 },
      },
    });
    await refresh();
  },
};
document.addEventListener('submit', (e) => {
  const fn = submits[e.target.id] || submits[[...e.target.classList].find((c) => submits[c])];
  if (!fn) return;
  e.preventDefault();
  const data = new FormData(e.target),
    decision = e.submitter?.value;
  work(() => fn(e.target, data, decision));
});
window.addEventListener('hashchange', () => {
  const route = location.hash.slice(1);
  if (route === 'main') return;
  stopPlayback();
  state.screen = pages[route] ? route : 'command';
  render();
  document.querySelector('#main')?.focus({ preventScroll: true });
});
state.screen = pages[location.hash.slice(1)] ? location.hash.slice(1) : 'command';
render();
