// Templates intentionally contain no example sites, coordinates, dates or observations.
// Empty values must be replaced with sourced data before the backend will accept them.
export function inputTemplate(kind) {
  const validity = { source_note: '', valid_from: '', valid_until: '' };
  const point = () => ({ label: '', scene: [null, null, null], enu_m: [null, null, null] });
  switch (kind) {
    case 'dataset':
      return {
        title: '',
        coordinate_basis: 'measured',
        coordinate_reference_system: 'WGS84',
        map_source: '',
        curator: '',
        entities: [{ id: '', name: '', kind: 'other', coordinates: null }],
      };
    case 'networks':
      return {
        ...validity,
        edges: [
          {
            id: '',
            source: '',
            target: '',
            length_m: null,
            bidirectional: null,
            modes: [],
            status: 'unknown',
            source_note: '',
            annotation_ids: [],
          },
        ],
      };
    case 'registrations':
      return {
        ...validity,
        scene_name: '',
        origin: { latitude: null, longitude: null },
        origin_altitude_m: null,
        scene_unit_m: null,
        solve_scale: false,
        control_points: [point(), point(), point()],
        check_points: [point()],
        objects: [],
        max_rmse_m: null,
        max_error_m: null,
      };
    case 'relations':
      return {
        ...validity,
        relations: [
          { subject: '', predicate: '', object: '', annotation_ids: [], source_note: '' },
        ],
      };
    default:
      throw new Error('未识别的数据模板。');
  }
}
export function validateRealDataset(snapshot) {
  if (snapshot?.coordinate_basis !== 'measured')
    throw new Error(
      '此工作台仅接收真实来源的现场。演练坐标不能导入；请使用实测数据，未知坐标留空，并填写来源。',
    );
}
export function validateRealImage(image) {
  if (
    image.evidence_basis !== 'field_image' ||
    (image.camera_pose && image.camera_pose.position_basis !== 'measured')
  )
    throw new Error(
      '现场含演练图片或演练位姿，未载入。请建立独立现场导入真实素材；历史资料仍保留在后端。',
    );
}
