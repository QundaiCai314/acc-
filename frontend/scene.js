import * as THREE from './vendor/three.module.js';
import { OrbitControls } from './vendor/OrbitControls.js';
import { state, entity } from './state.js';
import { esc, fmt } from './ui.js';

let renderer,
  scene,
  camera,
  controls,
  element,
  frame,
  regId = '',
  focus = '',
  targets = [],
  labels = [],
  reg;
const world = (p) => new THREE.Vector3(p[0], p[2], -p[1]);
function dispose() {
  cancelAnimationFrame(frame);
  controls?.dispose();
  scene?.traverse((o) => {
    o.geometry?.dispose();
    if (o.material)
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) m.dispose();
  });
  renderer?.dispose();
  renderer = null;
  regId = '';
  focus = '';
  targets = [];
  labels = [];
  element = null;
}
export function detachScene() {
  if (element?.isConnected) element.remove();
}
export function sceneControls(r) {
  const img = state.images.find((i) => i.id === state.cameraImage);
  const pip = img
    ? '<div class="scene-pip"><span>' +
      esc(img.name) +
      ' · 原图</span><img ' +
      (img.url ? 'src="' + esc(img.url) + '"' : 'data-image="' + esc(img.id) + '"') +
      ' alt="' +
      esc(img.name) +
      '"><small>' +
      (img.camera_pose
        ? fmt(img.camera_pose.heading_deg) +
          '° / ' +
          fmt(img.camera_pose.horizontal_fov_deg) +
          '° FOV'
        : '未提供相机位姿') +
      '</small></div>'
    : '';
  return (
    '<div class="scene-head"><span>局部三维 / ENU</span><span>' +
    r.snapshot.control_points.length +
    ' GCP · ' +
    r.snapshot.check_points.length +
    ' 检查点</span></div><div class="registration-viewports"><div class="scene-frame"><div id="scene-slot" data-registration="' +
    esc(r.id) +
    '"></div>' +
    pip +
    '</div><div class="control-plan"><h3>2D · 控制点平面</h3>' +
    plan(r) +
    '<p>目标 ENU / m<br>点位与下方残差表联动</p></div></div><div class="scene-hud"><span><i class="dot cyan"></i>控制点</span><span><i class="dot amber"></i>检查点</span><span>拖动旋转 · 滚轮缩放</span></div>'
  );
}
function plan(r) {
  const points = [...r.snapshot.control_points, ...r.snapshot.check_points],
    extent = Math.max(20, ...points.flatMap((p) => p.enu_m.slice(0, 2).map(Math.abs))),
    scale = 85 / extent;
  const body = points
    .map((p, i) => {
      const x = 110 + p.enu_m[0] * scale,
        y = 160 - p.enu_m[1] * scale;
      return (
        '<g role="button" tabindex="0" data-action="point" data-id="' +
        esc(p.label) +
        '" aria-label="平面聚焦 ' +
        esc(p.label) +
        '"><circle cx="' +
        x +
        '" cy="' +
        y +
        '" r="' +
        (state.point === p.label ? 8 : 4) +
        '" fill="' +
        (i < r.snapshot.control_points.length ? '#67d6ed' : '#efbb72') +
        '"/><text x="' +
        (x + 7) +
        '" y="' +
        (y - 8) +
        '" fill="#c4ddea" font-size="8">' +
        esc(p.label) +
        '</text></g>'
      );
    })
    .join('');
  return (
    '<svg viewBox="0 0 220 320" role="group" aria-label="控制点 ENU 俯视图"><defs><pattern id="plan-grid" width="22" height="22" patternUnits="userSpaceOnUse"><path d="M22 0H0V22" fill="none" stroke="#304959" stroke-width=".5"/></pattern></defs><rect width="220" height="320" fill="url(#plan-grid)"/><path d="M20 160H205M110 290V20" stroke="#627d90" stroke-width=".7"/><text x="118" y="24" fill="#9fc4d5" font-size="9">N</text><text x="202" y="153" fill="#9fc4d5" font-size="9">E</text>' +
    body +
    '</svg>'
  );
}
export function mountScene() {
  const slot = document.querySelector('#scene-slot');
  if (!slot) {
    dispose();
    return;
  }
  reg = state.artifacts.find((r) => r.id === slot.dataset.registration);
  if (!reg) return;
  if (regId !== reg.id) {
    dispose();
    regId = reg.id;
    create(slot);
  } else if (element) {
    slot.append(element);
    resize();
  }
  if (controls && renderer && state.point && focus !== state.point) {
    focus = state.point;
    const point = targets.find((o) => o.userData.point === focus);
    if (point) {
      const delta = point.position.clone().sub(controls.target);
      camera.position.add(delta);
      controls.target.copy(point.position);
      controls.update();
    }
  }
}
function resize() {
  if (!renderer || !element) return;
  const w = element.clientWidth,
    h = element.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / Math.max(1, h);
  camera.updateProjectionMatrix();
}
function create(slot) {
  element = document.createElement('div');
  element.className = 'three-renderer';
  slot.append(element);
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  } catch {
    element.textContent = 'WebGL 不可用，请使用下方坐标与残差表核验。';
    return;
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setClearColor('#101b26');
  element.append(renderer.domElement);
  renderer.domElement.setAttribute(
    'aria-label',
    '三维配准视口，拖动旋转；点位表提供键盘可访问的聚焦操作',
  );
  scene = new THREE.Scene();
  scene.add(new THREE.AmbientLight(0xc0ddff, 1.8));
  const light = new THREE.DirectionalLight(0xffffff, 2);
  light.position.set(30, 100, 40);
  scene.add(light);
  camera = new THREE.PerspectiveCamera(45, 1, 0.05, 20000);
  camera.position.set(100, 80, 100);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  const matrix = reg.computed?.matrix_scene_to_enu
    ? new THREE.Matrix4().fromArray(reg.computed.matrix_scene_to_enu.flat()).transpose()
    : new THREE.Matrix4().makeScale(
        reg.snapshot.scene_unit_m,
        reg.snapshot.scene_unit_m,
        reg.snapshot.scene_unit_m,
      );
  const transform = (p) => new THREE.Vector3(...p).applyMatrix4(matrix).toArray();
  targets = [];
  labels = [];
  const all = [...reg.snapshot.control_points, ...reg.snapshot.check_points];
  const extent = Math.max(30, ...all.flatMap((p) => p.enu_m.map(Math.abs)));
  const grid = new THREE.GridHelper(extent * 4, 24, 0x3d5364, 0x233542);
  scene.add(grid);
  const axes = new THREE.AxesHelper(extent * 0.55);
  scene.add(axes);
  for (const o of reg.snapshot.objects) {
    const [a, b, c] = o.min_corner,
      [x, y, z] = o.max_corner,
      vertices = [
        [a, b, c],
        [x, b, c],
        [x, y, c],
        [a, y, c],
        [a, b, z],
        [x, b, z],
        [x, y, z],
        [a, y, z],
      ].map((p) => world(transform(p)));
    const geometry = new THREE.BufferGeometry().setFromPoints(vertices);
    geometry.setIndex([
      0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3,
      0, 4, 3, 4, 7,
    ]);
    geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(
      geometry,
      new THREE.MeshStandardMaterial({
        color: 0x376879,
        transparent: true,
        opacity: 0.65,
        side: THREE.DoubleSide,
        roughness: 0.8,
      }),
    );
    scene.add(mesh);
    scene.add(
      new THREE.LineSegments(
        new THREE.EdgesGeometry(geometry),
        new THREE.LineBasicMaterial({ color: 0x80cbe2 }),
      ),
    );
    const center = new THREE.Box3().setFromPoints(vertices).getCenter(new THREE.Vector3());
    labels.push({
      position: center.clone().add(new THREE.Vector3(0, 20, 0)),
      text: entity(o.entity_id)?.name || o.entity_id,
    });
  }
  all.forEach((p, i) => {
    const target = world(p.enu_m),
      actual = world(transform(p.scene)),
      check = i >= reg.snapshot.control_points.length;
    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(extent * 0.016, 14, 10),
      new THREE.MeshBasicMaterial({ color: check ? 0xf4ba65 : 0x5ee2f4 }),
    );
    sphere.position.copy(target);
    sphere.userData.point = p.label;
    scene.add(sphere);
    targets.push(sphere);
    labels.push({ position: target, text: p.label });
    const residual = new THREE.BufferGeometry().setFromPoints([actual, target]);
    scene.add(new THREE.Line(residual, new THREE.LineBasicMaterial({ color: 0xff786b })));
  });
  for (const img of state.images) {
    const pose = img.camera_pose;
    if (!pose || pose.altitude_m == null) continue;
    const origin = reg.snapshot.origin;
    const east =
        (pose.coordinates.longitude - origin.longitude) *
        111195 *
        Math.cos((origin.latitude * Math.PI) / 180),
      north = (pose.coordinates.latitude - origin.latitude) * 111195;
    if (Math.hypot(east, north) > 10000) continue;
    const pos = world([east, north, pose.altitude_m - reg.snapshot.origin_altitude_m]);
    const yaw = THREE.MathUtils.degToRad(pose.heading_deg),
      pitch = THREE.MathUtils.degToRad(pose.pitch_deg);
    const direction = new THREE.Vector3(
      Math.sin(yaw) * Math.cos(pitch),
      Math.sin(pitch),
      -Math.cos(yaw) * Math.cos(pitch),
    );
    const aspect =
      Math.tan(THREE.MathUtils.degToRad(pose.horizontal_fov_deg / 2)) /
      Math.tan(THREE.MathUtils.degToRad(pose.vertical_fov_deg / 2));
    const lens = new THREE.PerspectiveCamera(pose.vertical_fov_deg, aspect, 0.1, 25);
    lens.position.copy(pos);
    lens.lookAt(pos.clone().add(direction));
    lens.updateMatrixWorld();
    const helper = new THREE.CameraHelper(lens);
    scene.add(helper);
    const point = new THREE.Mesh(
      new THREE.OctahedronGeometry(extent * 0.026),
      new THREE.MeshBasicMaterial({ color: 0xb7e9fb }),
    );
    point.position.copy(pos);
    point.userData.image = img.id;
    scene.add(point);
    targets.push(point);
  }
  const box = new THREE.Box3();
  targets.forEach((o) => box.expandByPoint(o.position));
  if (!box.isEmpty()) {
    const center = box.getCenter(new THREE.Vector3());
    controls.target.copy(center);
    camera.position.copy(center).add(new THREE.Vector3(extent * 2, extent * 1.5, extent * 2));
  }
  const overlay = document.createElement('div');
  overlay.className = 'scene-labels';
  element.append(overlay);
  for (const label of labels) {
    const el = document.createElement('span');
    el.textContent = label.text;
    overlay.append(el);
    label.element = el;
  }
  let start;
  renderer.domElement.addEventListener('pointerdown', (e) => (start = [e.clientX, e.clientY]));
  renderer.domElement.addEventListener('pointerup', (e) => {
    if (!start || Math.hypot(e.clientX - start[0], e.clientY - start[1]) > 5) return;
    const rect = renderer.domElement.getBoundingClientRect(),
      mouse = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        (-(e.clientY - rect.top) / rect.height) * 2 + 1,
      ),
      ray = new THREE.Raycaster();
    ray.setFromCamera(mouse, camera);
    const hit = ray.intersectObjects(targets)[0]?.object;
    if (hit?.userData.point)
      window.dispatchEvent(new CustomEvent('scene-point', { detail: hit.userData.point }));
    if (hit?.userData.image)
      window.dispatchEvent(new CustomEvent('camera-select', { detail: hit.userData.image }));
  });
  function tick() {
    if (!renderer) return;
    frame = requestAnimationFrame(tick);
    if (!element.isConnected) return;
    resize();
    controls.update();
    renderer.render(scene, camera);
    for (const label of labels) {
      const pos = label.position.clone().project(camera);
      label.element.style.transform =
        'translate(' +
        (pos.x * 0.5 + 0.5) * element.clientWidth +
        'px,' +
        (-pos.y * 0.5 + 0.5) * element.clientHeight +
        'px)';
      label.element.hidden = pos.z > 1 || pos.z < -1;
    }
  }
  tick();
}
