import {
  state,
  entities,
  entity,
  effective,
  visibleAnnotations,
  displayedNetwork,
  roadStatus,
  roadLabel,
  reviewedRelations,
  selectedRelationPaths,
} from './state.js';
import { mapSvg } from './map.js';
import { captureWithinWindow } from './capture-time.js';
let maplibregl, mapLibrary;

let map,
  element,
  ready = false,
  datasetKey = '',
  baseOn = true,
  markers = [];
const collection = (features) => ({ type: 'FeatureCollection', features });
const feature = (geometry, properties = {}) => ({ type: 'Feature', geometry, properties });
const xy = (c) => [c.longitude, c.latitude];
const point = (coords, properties) => feature({ type: 'Point', coordinates: coords }, properties);
const line = (coords, properties) =>
  feature({ type: 'LineString', coordinates: coords }, properties);
const offset = (c, m, bearing) => {
  const a = (bearing * Math.PI) / 180;
  return [
    c.longitude +
      (Math.sin(a) * m) / (111195 * Math.max(0.001, Math.cos((c.latitude * Math.PI) / 180))),
    c.latitude + (Math.cos(a) * m) / 111195,
  ];
};
function themePalette() {
  const t = state.artTheme || 'vellum';
  if (t === 'brutalist') {
    return {
      bg: '#0c0c0c',
      gridMajor: '#2e2e2e',
      gridMinor: '#1c1c1c',
      bufferFill: '#e8ff00',
      bufferLine: '#e8ff00',
      roadShadow: '#000000',
      roadOpen: '#f5f5f0',
      roadBlocked: '#ff2a00',
      roadUnknown: '#858580',
      routeLine: '#e8ff00',
      relActive: '#e8ff00',
      relIdle: '#888882',
      coneActive: '#e8ff00',
      coneIdle: '#999992',
      coneEdge: '#e8ff00',
      haloFill: '#ff2a00',
      haloStroke: '#e8ff00',
      pointFill: '#0c0c0c',
      camFill: '#e8ff00',
      camStroke: '#0c0c0c',
      entBlocked: '#ff2a00',
      entResource: '#e8ff00',
      entEntrance: '#ffffff',
      entBuilding: '#f5f5f0',
    };
  }
  if (t === 'mineral') {
    return {
      bg: '#141d22',
      gridMajor: '#283842',
      gridMinor: '#1c2830',
      bufferFill: '#c9933b',
      bufferLine: '#c9933b',
      roadShadow: '#0b1114',
      roadOpen: '#74c8aa',
      roadBlocked: '#ff917d',
      roadUnknown: '#a3b2ba',
      routeLine: '#d14332',
      relActive: '#c9933b',
      relIdle: '#6c808a',
      coneActive: '#c9933b',
      coneIdle: '#45937a',
      coneEdge: '#c9933b',
      haloFill: '#d14332',
      haloStroke: '#c9933b',
      pointFill: '#141d22',
      camFill: '#f0ebe1',
      camStroke: '#141d22',
      entBlocked: '#ff917d',
      entResource: '#74c8aa',
      entEntrance: '#c9933b',
      entBuilding: '#f0ebe1',
    };
  }
  // Default: 'vellum' (Kunsthalle & Vignelli Archival Vellum Atlas)
  return {
    bg: '#e8e1d3',
    gridMajor: '#c4bba8',
    gridMinor: '#d6cebe',
    bufferFill: '#1d4696',
    bufferLine: '#1d4696',
    roadShadow: '#ded6c6',
    roadOpen: '#1f6346',
    roadBlocked: '#c83720',
    roadUnknown: '#6c655b',
    routeLine: '#c83720',
    relActive: '#c83720',
    relIdle: '#6e675c',
    coneActive: '#1d4696',
    coneIdle: '#5a72a3',
    coneEdge: '#1d4696',
    haloFill: '#c83720',
    haloStroke: '#c83720',
    pointFill: '#f5f1e8',
    camFill: '#1d4696',
    camStroke: '#f5f1e8',
    entBlocked: '#c83720',
    entResource: '#1f6346',
    entEntrance: '#b56c12',
    entBuilding: '#161513',
  };
}
export function detachMap() {
  if (element?.isConnected) element.remove();
}
export function mapData() {
  const pal = themePalette();
  const marks = [],
    roads = [],
    zones = [],
    cameras = [],
    cones = [],
    links = [];
  const visible = visibleAnnotations(),
    net = displayedNetwork();
  for (const e of entities())
    if (e.coordinates) {
      const anns = visible.filter((a) => effective(a).entity_id === e.id),
        blocked = anns.some(
          (a) => a.status === 'approved' && effective(a).observation === 'obstacle_visible',
        );
      marks.push(
        point(xy(e.coordinates), {
          id: e.id,
          name: e.name,
          kind: e.kind,
          selected: e.id === state.selected,
          color: blocked
            ? pal.entBlocked
            : e.kind === 'resource'
              ? pal.entResource
              : e.kind === 'entrance'
                ? pal.entEntrance
                : pal.entBuilding,
          evidence: anns.length,
          mark: e.kind === 'resource' ? '+' : e.kind === 'entrance' ? '◇' : '□',
        }),
      );
    }
  if (net)
    for (const e of net.snapshot.edges) {
      const a = entity(e.source)?.coordinates,
        b = entity(e.target)?.coordinates,
        status = roadStatus(e);
      if (!a || !b) continue;
      roads.push(
        line([xy(a), xy(b)], {
          id: e.id,
          status,
          route: !!state.route?.edges?.some((r) => r.id === e.id),
          oneway: !e.bidirectional,
          color:
            status === 'blocked'
              ? pal.roadBlocked
              : status === 'unknown'
                ? pal.roadUnknown
                : pal.roadOpen,
          label: roadLabel(e, status),
        }),
      );
    }
  const center = entity(state.center)?.coordinates;
  if (center)
    zones.push(
      feature({
        type: 'Polygon',
        coordinates: [Array.from({ length: 73 }, (_, i) => offset(center, state.radius, i * 5))],
      }),
    );
  for (const img of state.images) {
    const pose = img.camera_pose;
    if (!pose || !captureWithinWindow(img, state.asOf, state.hours)) continue;
    const active = img.id === (state.hoverCamera || state.cameraImage);
    const a = pose.heading_deg - pose.horizontal_fov_deg / 2;
    const polygon = [
      xy(pose.coordinates),
      ...Array.from({ length: 25 }, (_, i) =>
        offset(pose.coordinates, active ? 45 : 30, a + (pose.horizontal_fov_deg * i) / 24),
      ),
      xy(pose.coordinates),
    ];
    cones.push(feature({ type: 'Polygon', coordinates: [polygon] }, { id: img.id, active }));
    cameras.push(
      point(xy(pose.coordinates), {
        id: img.id,
        name: img.name,
        active,
        heading: pose.heading_deg,
      }),
    );
  }
  const paths = selectedRelationPaths();
  if (state.showGraph)
    for (const r of reviewedRelations()) {
      const a = entity(r.subject)?.coordinates,
        b = entity(r.object)?.coordinates;
      if (a && b) links.push(line([xy(a), xy(b)], { label: r.predicate, active: paths.has(r) }));
    }
  const gridLines = [];
  const baseOrigin =
    entity('building-a')?.coordinates || entities().find((e) => e.coordinates)?.coordinates;
  // Local display grid only; no site coordinates means no grid.
  if (baseOrigin)
    for (let d = -320; d <= 320; d += 40) {
      const ew = { latitude: offset(baseOrigin, d, 0)[1], longitude: baseOrigin.longitude };
      const ns = { latitude: baseOrigin.latitude, longitude: offset(baseOrigin, d, 90)[0] };
      gridLines.push(line([offset(ew, 320, 270), offset(ew, 320, 90)], { major: d % 120 === 0 }));
      gridLines.push(line([offset(ns, 320, 180), offset(ns, 320, 0)], { major: d % 120 === 0 }));
    }
  return {
    grid: collection(gridLines),
    entities: collection(marks),
    roads: collection(roads),
    buffer: collection(zones),
    cameras: collection(cameras),
    cones: collection(cones),
    relations: collection(links),
  };
}
function setup() {
  for (const name of ['grid', 'entities', 'roads', 'buffer', 'cameras', 'cones', 'relations'])
    map.addSource(name, { type: 'geojson', data: collection([]) });
  const add = (id, type, source, paint = {}, layout = {}, filter) =>
    map.addLayer({ id, type, source, paint, layout, ...(filter ? { filter } : {}) });
  const pal = themePalette();
  add('tactical-grid', 'line', 'grid', {
    'line-color': ['case', ['get', 'major'], pal.gridMajor, pal.gridMinor],
    'line-width': ['case', ['get', 'major'], 1.1, 0.55],
    'line-opacity': 0.85,
  });
  add('buffer-fill', 'fill', 'buffer', { 'fill-color': '#51cce5', 'fill-opacity': 0.055 });
  add('buffer-line', 'line', 'buffer', {
    'line-color': '#6bdcf4',
    'line-width': 1.2,
    'line-dasharray': [3, 3],
  });
  add('roads-shadow', 'line', 'roads', { 'line-color': '#09121a', 'line-width': 9 });
  add('roads-open', 'line', 'roads', { 'line-color': ['get', 'color'], 'line-width': 3.5 }, {}, [
    '==',
    ['get', 'status'],
    'open',
  ]);
  add(
    'roads-closed',
    'line',
    'roads',
    { 'line-color': ['get', 'color'], 'line-width': 3.5, 'line-dasharray': [2, 2] },
    {},
    ['!=', ['get', 'status'], 'open'],
  );
  add(
    'roads-route',
    'line',
    'roads',
    { 'line-color': '#68e1ed', 'line-width': 6, 'line-opacity': 0.95 },
    {},
    ['==', ['get', 'route'], true],
  );
  add('relation-links', 'line', 'relations', {
    'line-color': ['case', ['get', 'active'], '#f4bd6e', '#7b96a4'],
    'line-width': ['case', ['get', 'active'], 2, 1],
    'line-dasharray': [1, 2],
  });
  add('camera-cones', 'fill', 'cones', {
    'fill-color': ['case', ['get', 'active'], '#76dcff', '#71a6c0'],
    'fill-opacity': ['case', ['get', 'active'], 0.25, 0.08],
  });
  add('camera-cone-edges', 'line', 'cones', {
    'line-color': '#72d9ff',
    'line-opacity': 0.5,
    'line-width': 1,
  });
  add(
    'selected-halo',
    'circle',
    'entities',
    {
      'circle-radius': 23,
      'circle-color': '#66d9ed',
      'circle-opacity': 0.1,
      'circle-stroke-color': '#71deed',
      'circle-stroke-width': 1.5,
    },
    {},
    ['==', ['get', 'selected'], true],
  );
  add('object-points', 'circle', 'entities', {
    'circle-radius': ['match', ['get', 'kind'], 'building', 10, 'resource', 8, 6],
    'circle-color': '#162530',
    'circle-stroke-color': ['get', 'color'],
    'circle-stroke-width': 2.5,
  });
  add('camera-points', 'circle', 'cameras', {
    'circle-radius': ['case', ['get', 'active'], 7, 4],
    'circle-color': '#8ae6ff',
    'circle-stroke-color': '#152b37',
    'circle-stroke-width': 2,
  });
  map.on('click', 'object-points', (e) =>
    window.dispatchEvent(new CustomEvent('gis-select', { detail: e.features[0].properties.id })),
  );
  map.on('click', 'camera-points', (e) =>
    window.dispatchEvent(new CustomEvent('camera-select', { detail: e.features[0].properties.id })),
  );
  map.on('mousemove', 'camera-points', (e) => {
    const id = e.features[0].properties.id;
    if (state.hoverCamera !== id) {
      state.hoverCamera = id;
      map.getSource('cones').setData(mapData().cones);
    }
  });
  map.on('mouseleave', 'camera-points', () => {
    state.hoverCamera = null;
    map.getSource('cones').setData(mapData().cones);
  });
  for (const id of ['object-points', 'camera-points']) {
    map.on('mouseenter', id, () => (map.getCanvas().style.cursor = 'pointer'));
    map.on('mouseleave', id, () => (map.getCanvas().style.cursor = ''));
  }
  ready = true;
  updateMap();
  fitMap();
}
export function mountMap() {
  const slot = document.querySelector('#gis-slot');
  if (!slot) return;
  if (!maplibregl) {
    slot.innerHTML = mapSvg();
    const status = document.querySelector('#basemap-status');
    if (status) status.textContent = '地图组件加载中 · 坐标概览可用';
    mapLibrary ||= import('./vendor/maplibre-gl.mjs');
    mapLibrary.then((library) => {
      maplibregl = library;
      if (slot.isConnected) {
        if (status) status.textContent = 'Esri 参考底图 · 非实时灾情 · 现场证据另行上传';
        mountMap();
      }
    }).catch(() => {
      if (!slot.isConnected) return;
      if (status) status.textContent = '地图组件加载失败 · 坐标概览可用，请刷新重试';
    });
    return;
  }
  if (!map) {
    element = document.createElement('div');
    element.className = 'gis-renderer';
    element.setAttribute('aria-label', '交互地图，可拖动平移、滚轮缩放，左侧列表支持键盘选择');
    slot.replaceChildren(element);
    try {
      map = new maplibregl.Map({
        container: element,
        style: {
          version: 8,
          sources: {
            basemap: {
              type: 'raster',
              tiles: [
                'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
              ],
              tileSize: 256,
              attribution: 'Tiles © Esri, Vantor, Earthstar Geographics, GIS User Community',
            },
          },
          layers: [
            { id: 'background', type: 'background', paint: { 'background-color': '#101a22' } },
            {
              id: 'basemap',
              type: 'raster',
              source: 'basemap',
              paint: {
                'raster-opacity': 0.85,
                'raster-saturation': -0.75,
                'raster-brightness-max': 0.55,
              },
            },
          ],
        },
        center: [0, 20],
        zoom: 1,
        renderWorldCopies: false,
        pitch: 0,
        attributionControl: { compact: true },
        preserveDrawingBuffer: true,
      });
      map.on('load', setup);
      map.on('error', (e) => {
        const status = document.querySelector('#basemap-status');
        if (status) {
          status.textContent = '影像底图加载受限 · 业务图层仍可用';
          status.classList.add('warn');
        }
      });
    } catch (e) {
      map = null;
      slot.innerHTML = mapSvg();
      const status = document.querySelector('#basemap-status');
      if (status) status.textContent = 'WebGL 不可用 · 已切换坐标概览';
    }
  } else {
    slot.replaceChildren(element);
    map.resize();
    updateMap();
  }
}
export function updateMap() {
  if (!ready || !map) return;
  const pal = themePalette();
  if (map.getLayer('background')) map.setPaintProperty('background', 'background-color', pal.bg);
  if (map.getLayer('tactical-grid'))
    map.setPaintProperty('tactical-grid', 'line-color', [
      'case',
      ['get', 'major'],
      pal.gridMajor,
      pal.gridMinor,
    ]);
  if (map.getLayer('buffer-fill'))
    map.setPaintProperty('buffer-fill', 'fill-color', pal.bufferFill);
  if (map.getLayer('buffer-line'))
    map.setPaintProperty('buffer-line', 'line-color', pal.bufferLine);
  if (map.getLayer('roads-shadow'))
    map.setPaintProperty('roads-shadow', 'line-color', pal.roadShadow);
  if (map.getLayer('roads-route')) map.setPaintProperty('roads-route', 'line-color', pal.routeLine);
  if (map.getLayer('relation-links'))
    map.setPaintProperty('relation-links', 'line-color', [
      'case',
      ['get', 'active'],
      pal.relActive,
      pal.relIdle,
    ]);
  if (map.getLayer('camera-cones'))
    map.setPaintProperty('camera-cones', 'fill-color', [
      'case',
      ['get', 'active'],
      pal.coneActive,
      pal.coneIdle,
    ]);
  if (map.getLayer('camera-cone-edges'))
    map.setPaintProperty('camera-cone-edges', 'line-color', pal.coneEdge);
  if (map.getLayer('selected-halo')) {
    map.setPaintProperty('selected-halo', 'circle-color', pal.haloFill);
    map.setPaintProperty('selected-halo', 'circle-stroke-color', pal.haloStroke);
  }
  if (map.getLayer('object-points'))
    map.setPaintProperty('object-points', 'circle-color', pal.pointFill);
  if (map.getLayer('camera-points')) {
    map.setPaintProperty('camera-points', 'circle-color', pal.camFill);
    map.setPaintProperty('camera-points', 'circle-stroke-color', pal.camStroke);
  }
  const data = mapData();
  for (const [id, geo] of Object.entries(data)) map.getSource(id)?.setData(geo);
  markers.forEach((m) => m.remove());
  markers = [];
  if (state.layers.objects)
    for (const f of data.entities.features) {
      const el = document.createElement('button');
      el.className = 'geo-label ' + (f.properties.selected ? 'selected' : '');
      const symbol = document.createElement('b');
      symbol.textContent = f.properties.mark;
      symbol.style.color = f.properties.color;
      const label = document.createElement('span');
      label.textContent = f.properties.name;
      el.append(symbol, label);
      el.setAttribute('aria-label', '地图对象：' + f.properties.name);
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        window.dispatchEvent(new CustomEvent('gis-select', { detail: f.properties.id }));
      });
      markers.push(
        new maplibregl.Marker({ element: el, anchor: 'top', offset: [0, -14] })
          .setLngLat(f.geometry.coordinates)
          .addTo(map),
      );
    }
  if (state.layers.roads)
    for (const f of data.roads.features) {
      const [a, b] = f.geometry.coordinates,
        el = document.createElement('span');
      el.className = 'geo-road-label';
      el.textContent = f.properties.label;
      el.style.color = f.properties.color;
      const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      markers.push(
        new maplibregl.Marker({ element: el, anchor: 'bottom', offset: [0, -8] })
          .setLngLat(mid)
          .addTo(map),
      );
      if (f.properties.oneway) {
        const arrow = document.createElement('span');
        arrow.className = 'geo-direction';
        arrow.innerHTML = '<i>› › ›</i>';
        const angle =
          (Math.atan2(-(b[1] - a[1]), (b[0] - a[0]) * Math.cos((a[1] * Math.PI) / 180)) * 180) /
          Math.PI;
        markers.push(
          new maplibregl.Marker({
            element: arrow,
            rotation: angle,
            rotationAlignment: 'map',
          })
            .setLngLat(mid)
            .addTo(map),
        );
      }
    }
  const groups = {
    objects: ['selected-halo', 'object-points'],
    roads: ['roads-shadow', 'roads-open', 'roads-closed', 'roads-route'],
    buffer: ['buffer-fill', 'buffer-line'],
    cameras: ['camera-cones', 'camera-cone-edges', 'camera-points'],
  };
  for (const [key, ids] of Object.entries(groups))
    for (const id of ids)
      map.setLayoutProperty(id, 'visibility', state.layers[key] ? 'visible' : 'none');
  if (baseOn !== state.basemap) {
    map.setLayoutProperty('basemap', 'visibility', state.basemap ? 'visible' : 'none');
    baseOn = state.basemap;
  }
  const key = (state.client?.base || 'disconnected') + '|' + state.dataset?.id;
  if (datasetKey !== key) {
    datasetKey = key;
    fitMap();
  }
}
export function fitMap() {
  if (!map || !ready) return;
  const coords = entities()
    .filter((e) => e.coordinates)
    .map((e) => xy(e.coordinates));
  if (!coords.length) {
    map.jumpTo({ center: [0, 20], zoom: 1, bearing: 0, pitch: 0 });
    return;
  }
  const bounds = coords.reduce(
    (b, p) => b.extend(p),
    new maplibregl.LngLatBounds(coords[0], coords[0]),
  );
  map.fitBounds(bounds, {
    padding: { top: 140, bottom: 180, left: 80, right: 80 },
    maxZoom: 18,
    duration: 400,
  });
}
export function focusMap(id) {
  const c = entity(id)?.coordinates;
  if (map && c) map.easeTo({ center: xy(c), duration: 450 });
  updateMap();
}
export function zoomMap(delta) {
  if (map) map.zoomTo(Math.min(22, Math.max(1, map.getZoom() + delta)), { duration: 200 });
}
