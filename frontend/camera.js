export function cameraFields() {
  return '<details class="camera-fields wide"><summary>拍摄位置与视野（可选）</summary><label class="check-label"><input type="checkbox" name="camera_enabled">为这张图片记录相机位姿</label><div class="two-fields"><label>相机纬度 / WGS84<input name="camera_lat" type="number" step="any" min="-90" max="90"></label><label>相机经度 / WGS84<input name="camera_lon" type="number" step="any" min="-180" max="180"></label><label>镜头朝向 / °（北为 0）<input name="camera_heading" type="number" step="any" min="0" max="359.999"></label><label>水平视角 / °<input name="camera_fov" type="number" step="any" min="1" max="178"></label><label>椭球高 / m（3D 可选）<input name="camera_alt" type="number" step="any" min="-1000" max="10000"></label><label>俯仰角 / °（向上为正）<input name="camera_pitch" type="number" step="any" min="-90" max="90" ></label><label>垂直视角 / °<input name="camera_vfov" type="number" step="any" min="1" max="178" ></label><label>定位性质<select name="camera_basis"><option value="measured">实测位姿</option></select></label></div><label>位姿来源说明<input name="camera_source" maxlength="2000" placeholder="设备记录或人工测量方法"></label><p class="meta">朝向与坐标由来源提供，不从图片或对象坐标推测；没有椭球高时仅绘制二维扇区。</p></details>';
}
export function cameraPayload(data) {
  if (!data.get('camera_enabled')) return null;
  for (const key of [
    'camera_lat',
    'camera_lon',
    'camera_heading',
    'camera_fov',
    'camera_pitch',
    'camera_vfov',
    'camera_source',
  ])
    if (!data.get(key)?.trim())
      throw new Error('启用相机位姿时，请填写坐标、朝向、俯仰角、水平及垂直视角和来源说明。');
  return {
    coordinates: {
      latitude: Number(data.get('camera_lat')),
      longitude: Number(data.get('camera_lon')),
    },
    altitude_m: data.get('camera_alt')?.trim() ? Number(data.get('camera_alt')) : null,
    heading_deg: Number(data.get('camera_heading')),
    pitch_deg: Number(data.get('camera_pitch')),
    horizontal_fov_deg: Number(data.get('camera_fov')),
    vertical_fov_deg: Number(data.get('camera_vfov')),
    position_basis: data.get('camera_basis'),
    source_note: data.get('camera_source'),
  };
}
