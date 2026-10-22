import { state } from './state.js';
import { icon, esc } from './ui.js';
import * as bench from './workbench.js';
import * as view from './views.js';

const groups = {
  media: {
    name: '素材与审核',
    tabs: [
      ['analysis', '素材库'],
      ['import', '上传资料'],
      ['field', '现场观察'],
      ['review', '人工审核'],
    ],
  },
  spatial: {
    name: '空间分析',
    tabs: [
      ['plans', '道路可达'],
      ['reason', '关系查证'],
    ],
  },
  scene: { name: '三维核验', tabs: [['registration', '配准与控制点']] },
};
export const groupFor = (route) =>
  Object.keys(groups).find((key) => groups[key].tabs.some(([id]) => id === route));
const layouts = new Map();
let activeWindow;
let mountedWindows = new Set();
const markup = (html) => {
  const node = document.createElement('div');
  node.innerHTML = html;
  return node;
};
const take = (root, selector) => root.querySelector(selector)?.outerHTML || '';

function windowFrame(id, title, body, close, extra = '') {
  return (
    '<section class="float-window ' +
    extra +
    '" data-window="' +
    id +
    '" aria-label="' +
    title +
    '">' +
    '<header class="window-bar" title="拖动标题栏移动窗口"><button class="window-grip" data-drag-window="' +
    id +
    '" aria-label="移动' +
    title +
    '，方向键微调"><span class="grip-dots" aria-hidden="true">⠿</span></button><' +
    (id === 'tool' ? 'h1' : 'h2') +
    '>' +
    title +
    '</' +
    (id === 'tool' ? 'h1' : 'h2') +
    '><span class="window-hint" aria-hidden="true">拖动移动</span><span class="window-actions">' +
    (id === 'tool'
      ? '<button data-action="expand-tool" aria-label="' +
        (state.expandedTool ? '还原工作窗' : '放大工作窗') +
        '">' +
        icon('scan') +
        '</button>'
      : '') +
    '<button data-action="minimize-window" data-window-id="' +
    id +
    '" aria-label="收起' +
    title +
    '">' +
    icon('minus') +
    '</button><button data-action="' +
    close +
    '" aria-label="关闭' +
    title +
    '">' +
    icon('close') +
    '</button></span></header><div class="window-body">' +
    body +
    '</div></section>'
  );
}

export function compose(pages) {
  const base = markup(bench.command()),
    map = base.querySelector('.operating-map');
  // One persistent map. Existing forms become contextual tools above it.
  map.querySelector('.gis-floatbar')?.remove();
  if (!state.dataset) {
    map.querySelector('.filter-pills')?.remove();
    map.querySelector('.floating-legend')?.remove();
  }
  const layers = take(map, '.floating-layers'),
    timeline = take(map, '.floating-timeline');
  const photo = take(map, '.camera-pip'),
    graph = take(map, '.relation-inset');
  for (const selector of [
    '.floating-layers',
    '.floating-timeline',
    '.camera-pip',
    '.relation-inset',
  ])
    map.querySelector(selector)?.remove();
  if (state.screen !== 'command') map.querySelector('h1')?.remove();
  let panels = '';
  if (state.showObjects)
    panels += windowFrame('objects', '对象与范围', take(base, '.entity-sidebar'), 'toggle-objects');
  if (state.showLayers) panels += windowFrame('layers', '图层', layers, 'toggle-layers');
  if (state.showData)
    panels += windowFrame('data', '数据来源与可用性', bench.dataStatus(), 'toggle-data');
  if (state.showTimeline) panels += windowFrame('time', '采集时间', timeline, 'toggle-time');
  if (photo) panels += windowFrame('photo', '定向影像', photo, 'close-pip');
  if (graph) panels += windowFrame('graph', '关系图谱', graph, 'close-graph');
  if (state.showIntel) {
    const intel = base.querySelector('.intel');
    intel.querySelector('.panel-heading')?.remove();
    if (state.screen === 'reason') intel.querySelector('.answer')?.remove();
    panels += windowFrame('intel', '证据与问答', intel.outerHTML, 'toggle-intel');
  }
  const group = groupFor(state.screen);
  if (group) {
    const content = markup(state.screen === 'plans' ? view.plans(true) : pages[state.screen]());
    const heading = content.querySelector('h1')?.textContent || groups[group].name;
    content.querySelector('.page-heading')?.remove();
    content.querySelector('.review-page-head')?.remove();
    content.querySelector('h1')?.remove();
    const tabs =
      '<nav class="workflow-tabs" aria-label="' +
      groups[group].name +
      '">' +
      groups[group].tabs
        .map(
          ([id, label]) =>
            '<a href="#' +
            id +
            '" ' +
            (state.screen === id ? 'aria-current="page"' : '') +
            '>' +
            label +
            (id === 'review'
              ? '<span>' +
                state.annotations.filter((a) => a.status === 'pending_review').length +
                '</span>'
              : '') +
            '</a>',
        )
        .join('') +
      '</nav>';
    panels += windowFrame(
      'tool',
      esc(heading),
      (group === 'media' || group === 'scene'
        ? '<div class="workflow-toolbar">' +
          tabs +
          '<div class="workflow-context"><button class="text-button" data-action="datasets" aria-label="切换现场">' +
          esc(state.dataset?.snapshot.title || '选择现场') +
          ' ↓</button><button class="text-button" data-action="refresh"' +
          (state.busy || !state.client ? ' disabled' : '') +
          '>' +
          icon('refresh') +
          '刷新</button></div></div>'
        : tabs) +
        '<div class="tool-content">' +
        content.innerHTML +
        '</div>',
      'close-tool',
      'tool-' + group + (state.expandedTool ? ' expanded' : ''),
    );
  }
  const tools =
    '<nav class="map-tool-dock" aria-label="地图工具">' +
    [
      ['toggle-objects', 'map', '对象', state.showObjects],
      ['toggle-layers', 'layers', '图层', state.showLayers],
      ['toggle-data', 'shield', '数据', state.showData],
      ['toggle-time', 'clock', '时间', state.showTimeline],
      ['toggle-graph', 'link', '关系', state.mapView === 'graph'],
      ['toggle-intel', 'chat', '问答', state.showIntel],
      ['fit-map', 'scan', '全域', false],
    ]
      .map(
        ([action, symbol, label, active]) =>
          '<button data-action="' +
          action +
          '" aria-pressed="' +
          active +
          '">' +
          icon(symbol) +
          '<span>' +
          label +
          '</span></button>',
      )
      .join('') +
    '</nav>';
  const question =
    !state.showIntel && !group && state.dataset
      ? '<form id="quick-question" class="map-question"><label for="quick-question-text">' +
        icon('chat') +
        '<span class="sr-only">向现场证据提问</span></label><input id="quick-question-text" name="question" required minlength="2" maxlength="1000" placeholder="输入现场对象、距离和需要查证的问题"><button aria-label="打开证据问答">' +
        icon('arrow') +
        '</button></form>'
      : '';
  const visible = new Set(
    [...markup(panels).querySelectorAll('[data-window]')].map((node) => node.dataset.window),
  );
  state.minimizedWindows = (state.minimizedWindows || []).filter((w) => !visible.has(w.id));
  const tray = state.minimizedWindows.length
    ? '<div class="window-tray" aria-label="已收起的窗口">' +
      state.minimizedWindows
        .map(
          (w) =>
            '<button data-action="restore-window" data-window-id="' +
            w.id +
            '">' +
            icon('layers') +
            esc(w.title) +
            ' ↗</button>',
        )
        .join('') +
      '</div>'
    : '';
  return (
    '<div class="workspace-stage v2 ' +
    (group ? 'with-tool' : '') +
    (!state.dataset ? ' empty-workspace' : '') +
    '">' +
    map.outerHTML +
    (!group && !state.showIntel && !state.showObjects && !state.showData
      ? bench.onboarding()
      : '') +
    tools +
    question +
    panels +
    tray +
    '</div>'
  );
}

function layoutKey(node) {
  return node.dataset.window === 'tool' ? 'tool-' + groupFor(state.screen) : node.dataset.window;
}
function clampPosition(node, left, top) {
  const stage = document.querySelector('.workspace-stage');
  return {
    left: Math.max(8, Math.min(left, stage.clientWidth - node.offsetWidth - 8)),
    top: Math.max(8, Math.min(top, stage.clientHeight - node.offsetHeight - 8)),
  };
}
function place(node, left, top) {
  const position = clampPosition(node, left, top);
  Object.assign(node.style, {
    left: position.left + 'px',
    top: position.top + 'px',
    right: 'auto',
    bottom: 'auto',
  });
  layouts.set(layoutKey(node), position);
}
export function mountWindows() {
  const windows = [...document.querySelectorAll('[data-window]')];
  const keys = new Set(windows.map(layoutKey));
  for (const key of keys) if (!mountedWindows.has(key)) activeWindow = key;
  if (!keys.has(activeWindow)) activeWindow = windows.length ? layoutKey(windows.at(-1)) : null;
  mountedWindows = keys;
  for (const node of windows) {
    const position = layouts.get(layoutKey(node));
    if (innerWidth <= 640 || node.classList.contains('expanded')) {
      for (const property of ['left', 'top', 'right', 'bottom'])
        node.style.removeProperty(property);
    } else {
      const rect = node.getBoundingClientRect(),
        stage = node.parentElement.getBoundingClientRect();
      place(node, position?.left ?? rect.left - stage.left, position?.top ?? rect.top - stage.top);
    }
    node.classList.toggle('is-active', layoutKey(node) === activeWindow);
  }
}
function activate(node) {
  activeWindow = layoutKey(node);
  for (const panel of document.querySelectorAll('[data-window]'))
    panel.classList.toggle('is-active', panel === node);
}
let drag;
document.addEventListener('pointerdown', (event) => {
  const node = event.target.closest('[data-window]');
  if (node) activate(node);
  const handle = event.target.closest('.window-bar');
  if (
    !handle ||
    event.target.closest('.window-actions') ||
    event.button !== 0 ||
    !event.isPrimary ||
    innerWidth <= 640 ||
    node.classList.contains('expanded')
  )
    return;
  const rect = node.getBoundingClientRect(),
    stage = document.querySelector('.workspace-stage').getBoundingClientRect();
  drag = {
    node,
    handle,
    pointer: event.pointerId,
    x: event.clientX,
    y: event.clientY,
    left: rect.left - stage.left,
    top: rect.top - stage.top,
  };
  node.classList.add('is-dragging');
  handle.setPointerCapture(event.pointerId);
  event.preventDefault();
});
document.addEventListener('pointermove', (event) => {
  if (drag?.pointer === event.pointerId)
    place(drag.node, drag.left + event.clientX - drag.x, drag.top + event.clientY - drag.y);
});
function stopDrag() {
  if (!drag) return;
  const { node, handle, pointer } = drag;
  drag = null;
  node.classList.remove('is-dragging');
  if (handle.hasPointerCapture(pointer)) handle.releasePointerCapture(pointer);
}
document.addEventListener('pointerup', stopDrag);
document.addEventListener('pointercancel', stopDrag);
document.addEventListener('lostpointercapture', stopDrag);
window.addEventListener('blur', stopDrag);
document.addEventListener('keydown', (event) => {
  if (
    !event.target.matches('[data-drag-window]') ||
    !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key) ||
    innerWidth <= 640
  )
    return;
  const node = event.target.closest('[data-window]');
  if (node.classList.contains('expanded')) return;
  event.preventDefault();
  activate(node);
  const rect = node.getBoundingClientRect(),
    stage = document.querySelector('.workspace-stage').getBoundingClientRect();
  place(
    node,
    rect.left - stage.left + ({ ArrowLeft: -16, ArrowRight: 16 }[event.key] || 0),
    rect.top - stage.top + ({ ArrowUp: -16, ArrowDown: 16 }[event.key] || 0),
  );
});
window.addEventListener('resize', mountWindows);
