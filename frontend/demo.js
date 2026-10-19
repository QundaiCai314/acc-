// Explicit synthetic fixtures. Never imported into a service automatically.
export function makeDemo() {
  const now = Date.now(),
    stamp = (h) => new Date(now - h * 3600000).toISOString();
  const coords = (x, y) => ({ latitude: 31.2304 + y / 111195, longitude: 121.4737 + x / 95100 });
  const entities = [
    ['building-a', 'A 楼', 'building', 0, 0],
    ['building-b', 'B 楼', 'building', 135, 65],
    ['building-c', 'C 楼', 'building', -150, 80],
    ['east', 'A 楼 · 东入口', 'entrance', 48, -8],
    ['south', 'A 楼 · 南入口', 'entrance', 0, -50],
    ['west', '西侧集合点', 'resource', -130, -100],
    ['medical', '临时医疗点', 'resource', 155, -105],
    ['junction', '南侧路口', 'road', 45, -100],
    ['north', '北侧路口', 'road', 45, 105],
  ];
  const dataset = {
    id: 'demo',
    snapshot: {
      title: '北城街区 · 地震救援演练',
      exercise: true,
      coordinate_basis: 'exercise',
      coordinate_reference_system: 'WGS84',
      map_source: '合成演练坐标，非真实现场测绘',
      curator: '演练小组',
      entities: entities.map(([id, name, kind, x, y]) => ({
        id,
        name,
        kind,
        coordinates: coords(x, y),
      })),
    },
  };
  const images = [
    {
      id: 'img-east',
      name: '东入口观察.svg',
      captured_at: stamp(1),
      source: '演练插画 · 东入口',
      evidence_basis: 'exercise',
      url: 'assets/entrance.svg',
    },
    {
      id: 'img-south',
      name: '南入口观察.svg',
      captured_at: stamp(3),
      source: '演练插画 · 南入口',
      evidence_basis: 'exercise',
      url: 'assets/entrance.svg',
    },
    {
      id: 'img-old',
      name: '早期入口记录.svg',
      captured_at: stamp(30),
      source: '演练插画 · 旧记录',
      evidence_basis: 'exercise',
      url: 'assets/entrance.svg',
    },
  ];
  dataset.snapshot.entities.push(
    { id: 'lobby-a', name: 'A 楼 · 首层门厅', kind: 'other' },
    { id: 'debris-east', name: '东入口 · 散落构件', kind: 'other' },
  );
  images.forEach((img, i) => {
    img.camera_pose = {
      coordinates: coords(i === 1 ? 20 : 80, i === 1 ? -80 : -40),
      altitude_m: 1.8,
      heading_deg: i === 1 ? 330 : 315,
      pitch_deg: 0,
      horizontal_fov_deg: 65,
      vertical_fov_deg: 45,
      position_basis: 'exercise',
      source_note: '合成演练相机位姿，非真实拍摄定位',
    };
  });
  const annotations = [
    [
      'ann-east',
      'img-east',
      'east',
      'obstacle_visible',
      'approved',
      '东入口画面可见散落构件，不能据此判断整体结构安全。',
      0.91,
    ],
    [
      'ann-south',
      'img-south',
      'south',
      'unknown',
      'pending_review',
      '南入口视线受遮挡，需人工核对现场情况。',
      0.72,
    ],
    [
      'ann-old',
      'img-old',
      'south',
      'obstacle_visible',
      'approved',
      '早期记录可见障碍物，已超出默认 24 小时时间窗。',
      0.84,
    ],
  ].map(([id, image_id, entity_id, observation, status, description, confidence]) => {
    const annotation = {
      entity_id,
      observation,
      description,
      confidence,
      bbox: { x_min: 0.28, y_min: 0.38, x_max: 0.73, y_max: 0.84 },
    };
    return {
      id,
      image_id,
      origin: 'imported_unverified',
      status,
      annotation,
      review:
        status === 'approved'
          ? {
              approved_annotation: annotation,
              reviewer: '演练审核员',
              note: '合成示例，供界面核验',
              created_at: stamp(0.5),
            }
          : null,
    };
  });
  const validity = {
    valid_from: stamp(24),
    valid_until: stamp(-24),
    source_note: '合成演练数据；不代表实地通行状态',
  };
  const edges = [
    ['r1', 'west', 'junction', 180, 'open', true, ['walk', 'vehicle']],
    ['r2', 'junction', 'medical', 120, 'open', true, ['walk', 'vehicle']],
    ['r3', 'junction', 'east', 100, 'blocked', true, ['walk', 'vehicle']],
    ['r4', 'junction', 'south', 80, 'open', false, ['walk']],
    ['r5', 'south', 'east', 90, 'open', true, ['walk']],
    ['r6', 'east', 'north', 130, 'unknown', true, ['walk', 'vehicle']],
  ].map(([id, source, target, length_m, status, bidirectional, modes]) => ({
    id,
    source,
    target,
    length_m,
    status,
    bidirectional,
    modes,
    source_note: '演练路段',
    annotation_ids: [],
  }));
  const control_points = [
    { label: 'GCP-01', scene: [-30, -25, 0], enu_m: [-30, -25, 0] },
    { label: 'GCP-02', scene: [30, -25, 0], enu_m: [30, -25, 0] },
    { label: 'GCP-03', scene: [-30, 25, 0], enu_m: [-30, 25, 0] },
    { label: 'GCP-04', scene: [0, 0, 20], enu_m: [0, 0, 20] },
  ];
  const check_points = [{ label: 'CHECK-01', scene: [20, 18, 4], enu_m: [20, 18, 4] }];
  const registration = {
    ...validity,
    scene_name: 'A 楼 · 局部控制点',
    origin: coords(0, 0),
    origin_altitude_m: 0,
    scene_unit_m: 1,
    solve_scale: false,
    control_points,
    check_points,
    objects: [
      { entity_id: 'building-a', min_corner: [-25, -20, 0], max_corner: [25, 20, 30] },
      { entity_id: 'east', min_corner: [26, -7, 0], max_corner: [32, 0, 4] },
    ],
    max_rmse_m: 0.5,
    max_error_m: 1,
  };
  const relations = {
    ...validity,
    relations: [
      {
        subject: 'east',
        predicate: 'part_of',
        object: 'lobby-a',
        annotation_ids: [],
        source_note: '演练从属关系',
      },
      {
        subject: 'lobby-a',
        predicate: 'part_of',
        object: 'building-a',
        annotation_ids: [],
        source_note: '演练多跳关系',
      },
      {
        subject: 'south',
        predicate: 'part_of',
        object: 'building-a',
        annotation_ids: [],
        source_note: '演练从属关系',
      },
      {
        subject: 'debris-east',
        predicate: 'blocks',
        object: 'east',
        annotation_ids: [],
        source_note: '合成障碍关系，不代表实地封闭',
      },
    ],
  };
  const artifacts = [
    ['net-demo', 'road_network', { ...validity, edges }],
    ['reg-demo', 'registration', registration],
    ['rel-demo', 'relation_set', relations],
  ].map(([id, artifact_type, snapshot]) => ({
    id,
    artifact_type,
    snapshot,
    status: 'approved',
    review: { reviewer: '演练审核员', created_at: stamp(0.5), note: '合成演练' },
    computed:
      artifact_type === 'registration'
        ? {
            fit_rmse_m: 0,
            check_rmse_m: 0,
            fit_residuals_m: [0, 0, 0, 0],
            check_residuals_m: [0],
            estimated_scale: 1,
          }
        : null,
  }));
  return { dataset, images, annotations, artifacts };
}
