"""Regression checks for malformed time windows and provider configuration."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import vision
from app.main import create_app
from app.spatial_models import Dataset


class AuditBoundaryTests(unittest.TestCase):
    def test_time_windows_reject_overflow_before_retrieval(self):
        with tempfile.TemporaryDirectory() as folder, TestClient(create_app(Path(folder) / 'test.db')) as client:
            snapshot = json.loads((Path(__file__).resolve().parents[1] / 'examples/spatial_dataset.json').read_text(encoding='utf-8'))
            identifier = client.post('/spatial/datasets', json=snapshot).json()['id']
            base = f'/spatial/datasets/{identifier}'
            for stamp in ('0001-01-01T00:00:00Z', '0001-01-01T00:00:00+14:00',
                          '9999-12-31T23:59:59-14:00'):
                for endpoint, body in (('/query', {'center_entity_id': 'building-a', 'radius_m': 100}),
                        ('/reason', {'all_of': [{'relation': 'near', 'reference_entity_id': 'building-a', 'distance_m': 100}]})):
                    with self.subTest(stamp=stamp, endpoint=endpoint):
                        response = client.post(base + endpoint, json={**body, 'as_of': stamp, 'max_age_hours': 8760})
                        self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(client.post(base + '/query', json={'center_entity_id': 'building-a',
                'radius_m': 100, 'as_of': '0002-01-01T00:00:00Z', 'max_age_hours': 8760}).status_code, 200)

    def test_malformed_provider_urls_are_unavailable_without_a_request(self):
        dataset = Dataset(title='Test', coordinate_basis='exercise', map_source='test', curator='test',
                          entities=[{'id': 'a', 'name': 'A', 'kind': 'building'}])
        for url in ('https://[broken', 'https://example.com:invalid/chat', 'https://example.com:99999/chat',
                    'http://example.com/chat', 'https://user:secret@example.com/chat'):
            with (self.subTest(url=url), patch.dict(os.environ, {
                    'VISION_CHAT_URL': url, 'VISION_API_KEY': 'test', 'VISION_MODEL': 'test',
                    'QUESTION_CHAT_URL': url, 'QUESTION_API_KEY': 'test', 'QUESTION_MODEL': 'test'}),
                    patch('app.vision.request_json') as request):
                for invoke in (lambda: vision.analyze({}, dataset),
                        lambda: vision.interpret_question('test', dataset),
                        lambda: vision.interpret_relations('test', dataset, [])):
                    with self.assertRaises(vision.VisionUnavailable):
                        invoke()
                request.assert_not_called()
