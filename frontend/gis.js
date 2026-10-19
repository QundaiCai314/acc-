import {
  state,
  entities,
  entity,
  effective,
  visibleAnnotations,
  activeArtifact,
  reviewedRelations,
  selectedRelationPaths,
} from './state.js';
import { mapSvg } from './map.js';

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
export function detachMap() {
  if (element?.isConnected) element.remove();
}
export function mapData() {
  const marks = [],
    roads = [],
    zones = [],
    cameras = [],
    cones = [],
    links = [];
  const visible = visibleAnnotations(),
    net = state.route?.network_id
      ? state.artifacts.find((a) => a.id === state.route.network_id)
      : activeArtifact('road_network');
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
            ? '#ff796b'
            : e.kind === 'resource'
              ? '#58d9f5'
              : e.kind === 'entrance'
                ? '#f2ba62'
                : '#b7cbd6',
          evidence: anns.length,
          mark: e.kind === 'resource' ? '+' : e.kind === 'entrance' ? '◇' : '□',
        }),
      );
    }
  if (net)
    for (const e of net.snapshot.edges) {
      const a = entity(e.source)?.coordinates,
        b = entity(e.target)?.coordinates;
      if (!a || !b) continue;
      roads.push(
        line([xy(a), xy(b)], {
          id: e.id,
          status: e.status,
          route: !!state.route?.edges?.some((r) => r.id === e.id),
          oneway: !e.bidirectional,
          color:
            e.status === 'blocked' ? '#ff796b' : e.status === 'unknown' ? '#8b9aa5' : '#6bcbd5',
          label:
            e.status === 'blocked'
              ? '封闭 ×'
              : e.status === 'unknown'
                ? '未知'
                : e.modes.includes('vehicle')
                  ? '步行 / 车辆'
                  : '仅步行',
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
    const pose = img.camera_pose,
      age = (new Date(state.asOf) - new Date(img.captured_at)) / 3600000;
    if (!pose || age < 0 || age > state.hours) continue;
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
  return {
    entities: collection(marks),
    roads: collection(roads),
    buffer: collection(zones),
    cameras: collection(cameras),
    cones: collection(cones),
    relations: collection(links),
  };
}
function setup() {
  for (const name of ['entities', 'roads', 'buffer', 'cameras', 'cones', 'relations'])
    map.addSource(name, { type: 'geojson', data: collection([]) });
  const add = (id, type, source, paint = {}, layout = {}, filter) =>
    map.addLayer({ id, type, source, paint, layout, ...(filter ? { filter } : {}) });
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
  if (!window.maplibregl) {
    slot.innerHTML = mapSvg();
    return;
  }
  if (!map) {
    element = document.createElement('div');
    element.className = 'gis-renderer';
    element.setAttribute('aria-label', '交互地图，可拖动平移、滚轮缩放，左侧列表支持键盘选择');
    slot.append(element);
    try {
      map = new window.maplibregl.Map({
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
        center: [121.4737, 31.2304],
        zoom: 17,
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
    slot.append(element);
    map.resize();
    updateMap();
  }
}
export function updateMap() {
  if (!ready || !map) return;
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
        new window.maplibregl.Marker({ element: el, anchor: 'top', offset: [0, -14] })
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
        new window.maplibregl.Marker({ element: el, anchor: 'bottom', offset: [0, -8] })
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
          new window.maplibregl.Marker({
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
  const key = (state.client?.base || 'demo') + '|' + state.dataset?.id;
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
  if (!coords.length) return;
  const bounds = coords.reduce(
    (b, p) => b.extend(p),
    new window.maplibregl.LngLatBounds(coords[0], coords[0]),
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
