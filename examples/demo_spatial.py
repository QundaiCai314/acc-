"""Offline contract demo with a synthetic diagram; no vision inference is invoked or imitated."""

import base64
import json
import struct
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def diagram_png():
    # Code-drawn doorway and obstacle; not a photo of a real site.
    width, height = 160, 100
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rgb = (205, 205, 205)
            if 50 <= x < 110 and 20 <= y < 95:
                rgb = (30, 65, 90)
            if 40 <= x < 120 and 65 <= y < 95:
                rgb = (220, 120, 40)
            rows.extend(rgb)

    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))

    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def main():
    dataset = json.loads(Path(__file__).with_name('spatial_dataset.json').read_text(encoding='utf-8'))
    now = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory() as folder, TestClient(create_app(Path(folder) / 'demo.db')) as client:
        def post(url, data=None):
            response = client.post(url, json=data)
            response.raise_for_status()
            return response.json()

        dataset_id = post('/spatial/datasets', dataset)['id']
        image_id = post(f'/spatial/datasets/{dataset_id}/images', {
            'name': 'synthetic-doorway.png', 'source': '代码绘制的演练示意图，不是现场照片',
            'captured_at': now, 'evidence_basis': 'exercise', 'mime_type': 'image/png',
            'content_base64': base64.b64encode(diagram_png()).decode('ascii'),
        })['id']
        candidate = post(f'/spatial/datasets/{dataset_id}/annotations', {
            'image_id': image_id, 'source_note': '人工编写的演练候选，仅验证接口，不模拟真实 AI 识别质量',
            'annotation': {
                'entity_id': 'entrance-near', 'observation': 'obstacle_visible',
                'description': '演练图中橙色块位于蓝色入口下部前方',
                'bbox': {'x_min': 0.25, 'y_min': 0.65, 'x_max': 0.75, 'y_max': 0.95}, 'confidence': 1,
            },
        })['id']
        query = {'center_entity_id': 'building-a', 'radius_m': 100, 'as_of': now}
        endpoint = f'/spatial/datasets/{dataset_id}/query'
        before = post(endpoint, query)
        assert before['status'] == 'insufficient_evidence'
        post(f'/spatial/annotations/{candidate}/review', {
            'reviewer': 'demo-reviewer', 'action': 'approve', 'note': '仅在合成演练中确认对应与标注',
        })
        after = post(endpoint, query)
        assert len(after['citations']) == 1
        post(f'/spatial/annotations/{candidate}/withdraw', {'reviewer': 'demo-reviewer', 'note': '演示撤回'})
        withdrawn = post(endpoint, query)
        assert not withdrawn['citations']
        print(json.dumps({'before_review': before['status'], 'after_review': after,
                          'after_withdrawal': withdrawn['status']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
