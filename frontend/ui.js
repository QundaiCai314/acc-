export const esc = (value) =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
const paths = {
  map: 'M3 5l6-2 6 2 6-2v16l-6 2-6-2-6 2zm6-2v16m6-14v16',
  layers: 'm12 3 10 6-10 6L2 9zm-9 11 9 5 9-5m-18 5 9 5 9-5',
  upload: 'M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6',
  scan: 'M8 3H3v5m13-5h5v5M3 16v5h5m8 0h5v-5M7 12h10',
  check: 'm5 12 4 4L19 6',
  shield: 'm12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z',
  route: 'M5 5h10a4 4 0 0 1 0 8H9a4 4 0 0 0 0 8h10M3 3h4v4H3zm14 16h4v4h-4z',
  cube: 'm12 2 9 5v10l-9 5-9-5V7zm0 10v10M3 7l9 5 9-5M12 2v10',
  chat: 'M21 4H3v14h5l4 4 4-4h5zM7 9h10M7 13h6',
  search: 'M20 20l-5-5M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0',
  settings: 'M4 7h16M4 17h16M8 4v6m8 4v6',
  refresh: 'M20 8a8 8 0 1 0 0 8m0-13v5h-5',
  arrow: 'M4 12h16m-6-6 6 6-6 6',
  close: 'm6 6 12 12M6 18 18 6',
  clock: 'M12 7v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  image: 'M3 3h18v18H3zm0 14 6-6 5 5 3-3 4 4M15 7h1',
  plus: 'M12 4v16M4 12h16',
  minus: 'M4 12h16',
  link: 'm9 15 6-6m-7 2-3 3a4 4 0 0 0 6 6l3-3m-4-10 3-3a4 4 0 0 1 6 6l-3 3',
  file: 'M5 2h9l5 5v15H5zm9 0v6h5M8 13h8m-8 4h6',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12m13 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  logout: 'M9 3H3v18h6m0-9h12m-5-5 5 5-5 5',
};
export const icon = (name, cls = '') =>
  '<svg class="icon ' +
  cls +
  '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="' +
  (paths[name] || paths.file) +
  '"/></svg>';
export const kinds = {
  building: '建筑',
  entrance: '入口',
  road: '道路节点',
  resource: '救援资源',
  other: '其他对象',
};
export const observations = {
  obstacle_visible: '可见障碍物',
  no_obstacle_visible: '未见明显障碍物',
  unknown: '情况不明确',
};
export const statuses = {
  pending_review: '候选待审',
  approved: '已审核',
  rejected: '已驳回',
  withdrawn: '已撤回',
};
export const badge = (status, text) =>
  '<span class="badge ' + esc(status) + '">' + esc(text || statuses[status] || status) + '</span>';
export const empty = (title, detail = '') =>
  '<div class="empty">' +
  icon('layers') +
  '<strong>' +
  esc(title) +
  '</strong><p>' +
  esc(detail) +
  '</p></div>';
export const fmt = (value) =>
  value == null ? '—' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
export const time = (value) =>
  value
    ? new Date(value).toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })
    : '—';
export const captureTime = (image) =>
  image?.captured_on
    ? esc(image.captured_on) + '（仅日期，时区未知）'
    : image?.captured_at
      ? esc(
          new Date(image.captured_at).toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
          }),
        )
      : '采集时间未知';
export const options = (rows, selected) =>
  rows
    .map(
      ([value, label]) =>
        '<option value="' +
        esc(value) +
        '" ' +
        (value === selected ? 'selected' : '') +
        '>' +
        esc(label) +
        '</option>',
    )
    .join('');
export const jsonDetails = (label, value) =>
  '<details><summary>' +
  esc(label) +
  '</summary><pre>' +
  esc(JSON.stringify(value, null, 2)) +
  '</pre></details>';
export function safeURL(value) {
  try {
    const u = new URL(value);
    return ['http:', 'https:'].includes(u.protocol) && !u.username && !u.password
      ? esc(u.href)
      : '';
  } catch {
    return '';
  }
}
export function notify(message, error = false) {
  const n = document.querySelector('#notice');
  n.textContent = message;
  n.className = error ? 'visible error' : 'visible';
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => (n.className = ''), 6500);
}
