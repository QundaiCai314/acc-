import base64
import json
from datetime import datetime, timedelta, timezone
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from app import vision
from app.spatial import distance_m
from app.spatial_models import Coordinates, QueryIntent


ROOT = Path(__file__).resolve().parents[1]
PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='
ANNOTATION = {
    'entity_id': 'entrance-near', 'observation': 'obstacle_visible',
    'description': '测试候选记录，不是对测试占位图片的真实识别结果',
    'bbox': {'x_min': 0.1, 'y_min': 0.2, 'x_max': 0.9, 'y_max': 0.8}, 'confidence': 0.8,
}


class SpatialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'test.db'
        self.client = self.enterContext(TestClient(create_app(self.db)))
        self.dataset = json.loads((ROOT / 'examples/spatial_dataset.json').read_text(encoding='utf-8'))
        response = self.client.post('/spatial/datasets', json=self.dataset)
        self.assertEqual(response.status_code, 201, response.text)
        self.dataset_id = response.json()['id']
        self.image_payload = {
            'name': 'test-placeholder.png', 'captured_at': '2026-10-18T10:00:00+08:00',
            'source': '单像素测试占位图片，不是灾害素材', 'evidence_basis': 'exercise',
            'mime_type': 'image/png', 'content_base64': PNG,
        }
        self.image_id = self.upload(self.image_payload)
        self.query = {'center_entity_id': 'building-a', 'radius_m': 100,
                      'as_of': '2026-10-18T12:00:00+08:00', 'max_age_hours': 24}

    def upload(self, payload):
        r = self.client.post(f'/spatial/datasets/{self.dataset_id}/images', json=payload)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()['id']

    def propose(self, annotation=None, image_id=None):
        r = self.client.post(f'/spatial/datasets/{self.dataset_id}/annotations', json={
            'image_id': image_id or self.image_id, 'annotation': annotation or ANNOTATION,
            'source_note': '测试用外部候选，不是真实 AI 运行',
        })
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()['id']

    def review(self, identifier, action='approve', **kwargs):
        return self.client.post(f'/spatial/annotations/{identifier}/review', json={
            'reviewer': 'test-reviewer', 'action': action, 'note': '仅测试审核流程', **kwargs,
        })

    def ask(self, **changes):
        r = self.client.post(f'/spatial/datasets/{self.dataset_id}/query', json={**self.query, **changes})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_review_gate_citations_and_withdrawal(self):
        annotation_id = self.propose()
        self.assertEqual(self.ask()['status'], 'insufficient_evidence')
        self.assertEqual(self.review(annotation_id).status_code, 201)
        result = self.ask()
        self.assertEqual(result['status'], 'evidence_found')
        citation = result['citations'][0]
        self.assertAlmostEqual(citation['distance_m'], 55.60, places=2)
        self.assertEqual(citation['annotation_id'], annotation_id)
        self.assertEqual(citation['origin'], 'imported_unverified')
        self.assertIn('演练', result['answer'])
        self.assertEqual(self.client.get(citation['image_url']).content, base64.b64decode(PNG))
        self.assertEqual(self.review(annotation_id).status_code, 409)
        r = self.client.post(f'/spatial/annotations/{annotation_id}/withdraw',
                             json={'reviewer': 'test-reviewer', 'note': '测试撤回'})
        self.assertEqual(r.status_code, 201)
        r = self.client.post(f'/spatial/annotations/{annotation_id}/withdraw',
                             json={'reviewer': 'test-reviewer', 'note': 'repeat'})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.ask()['citations'], [])
        with TestClient(create_app(self.db)) as reopened:
            records = reopened.get(f'/spatial/datasets/{self.dataset_id}/annotations').json()['annotations']
            self.assertEqual(records[0]['status'], 'withdrawn')
            self.assertEqual(records[0]['review']['approved_annotation'], ANNOTATION)

    def test_date_only_capture_is_not_an_invented_instant(self):
        from app.geometry import evidence_records
        payload = {k: v for k, v in self.image_payload.items() if k != 'captured_at'}
        for changes in ({}, {'captured_on': '0001-01-01'}, {'captured_on': '9999-12-31'},
                        {'captured_on': '2026-10-17', 'captured_at': self.image_payload['captured_at']}):
            self.assertEqual(self.client.post(f'/spatial/datasets/{self.dataset_id}/images',
                                             json=payload | changes).status_code, 422)
        image = self.upload(payload | {'captured_on': '2026-10-17'})
        annotation = self.propose(image_id=image)
        self.assertEqual(self.ask()['citations'], [])
        self.assertEqual(self.review(annotation).status_code, 201)
        # Date+unknown timezone spans Oct 16 10:00Z through Oct 18 12:00Z.
        result = self.ask(as_of='2026-10-18T12:00:00Z', max_age_hours=50)
        self.assertEqual(result['citations'][0]['captured_on'], '2026-10-17')
        self.assertIsNone(result['citations'][0]['captured_at'])
        self.assertIn('仅日期', result['answer'])
        self.assertEqual(self.ask(as_of='2026-10-18T11:59:59Z', max_age_hours=50)['citations'], [])
        self.assertEqual(self.ask(as_of='2026-10-18T12:00:00Z', max_age_hours=49)['citations'], [])
        self.assertEqual(self.ask(as_of='2026-10-16T09:00:00Z')['older_evidence_count'], 0)
        self.assertEqual(self.ask(as_of='2026-10-20T12:00:00Z')['older_evidence_count'], 1)
        store = self.client.app.state.store
        end = datetime.fromisoformat('2026-10-18T12:00:00Z')
        self.assertIn(annotation, evidence_records(store, self.dataset_id, end, 50))
        self.assertNotIn(annotation, evidence_records(store, self.dataset_id, end, 49))

    def test_rejected_pending_far_unknown_and_time_filters(self):
        rejected = self.propose()
        self.assertEqual(self.review(rejected, 'reject').status_code, 201)
        self.propose()  # remains pending
        for entity in ('entrance-far', 'entrance-unlocated'):
            self.review(self.propose({**ANNOTATION, 'entity_id': entity}))
        for time in ('2026-10-15T10:00:00+08:00', '2026-10-19T10:00:00+08:00'):
            image = self.upload({**self.image_payload, 'captured_at': time})
            self.review(self.propose(image_id=image))
        result = self.ask()
        self.assertFalse(result['citations'])
        self.assertEqual(result['missing_coordinates'], ['entrance-unlocated'])
        self.assertEqual(len(self.ask(radius_m=300)['citations']), 1)
        self.assertEqual(len(self.ask(max_age_hours=120)['citations']), 1)

    def test_correction_keeps_original_and_requires_link(self):
        identifier = self.propose({**ANNOTATION, 'entity_id': None})
        self.assertEqual(self.review(identifier).status_code, 422)
        corrected = {**ANNOTATION, 'description': '人工修正后关联到 A 楼东侧入口'}
        self.assertEqual(self.review(identifier, corrected_annotation=corrected).status_code, 201)
        self.assertEqual(self.ask()['citations'][0]['annotation']['description'], corrected['description'])
        record = self.client.get(f'/spatial/datasets/{self.dataset_id}/annotations').json()['annotations'][0]
        self.assertIsNone(record['annotation']['entity_id'])
        self.assertEqual(record['review']['approved_annotation']['entity_id'], 'entrance-near')

    def test_older_evidence_hint_filters_and_time_boundaries(self):
        self.assertEqual(self.ask()['older_evidence_count'], 0)
        old_image = self.upload({**self.image_payload, 'captured_at': '2026-10-17T03:59:59+00:00'})
        old_annotation = self.propose(image_id=old_image)
        self.assertEqual(self.ask()['older_evidence_count'], 0)
        self.assertEqual(self.review(old_annotation).status_code, 201)
        self.propose(image_id=old_image)
        self.review(self.propose(image_id=old_image), 'reject')
        for changes in ({'entity_id': 'entrance-far'}, {'entity_id': 'entrance-unlocated'},
                        {'entity_id': 'building-a'}, {'observation': 'no_obstacle_visible'}):
            self.review(self.propose({**ANNOTATION, **changes}, image_id=old_image))
        future = self.upload({**self.image_payload, 'captured_at': '2026-10-18T04:00:01+00:00'})
        self.review(self.propose(image_id=future))
        result = self.ask()
        self.assertEqual(result['older_evidence_count'], 1)
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.assertEqual(result['citations'], [])
        self.assertIn('1 条早于本次时间窗口', result['answer'])
        self.assertIn('2026-10-17T03:59:59+00:00', result['answer'])
        self.assertIn('包含演练图片证据', result['answer'])
        wider = self.ask(max_age_hours=25)
        self.assertEqual(wider['older_evidence_count'], 0)
        self.assertEqual([item['annotation_id'] for item in wider['citations']], [old_annotation])
        boundary_ids = []
        for timestamp in ('2026-10-17T04:00:00+00:00', '2026-10-18T04:00:00+00:00'):
            image = self.upload({**self.image_payload, 'captured_at': timestamp})
            identifier = self.propose(image_id=image)
            self.review(identifier)
            boundary_ids.append(identifier)
        result = self.ask()
        self.assertEqual(result['older_evidence_count'], 1)
        self.assertEqual({item['annotation_id'] for item in result['citations']}, set(boundary_ids))
        self.assertNotIn('条早于本次时间窗口', result['answer'])
        response = self.client.post(f'/spatial/annotations/{old_annotation}/withdraw',
                                    json={'reviewer': 'test-reviewer', 'note': '撤回旧记录'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.ask()['older_evidence_count'], 0)

    def test_natural_question_explains_old_evidence_without_using_it(self):
        image = self.upload({**self.image_payload,
                             'captured_at': (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()})
        self.review(self.propose(image_id=image))
        intent = QueryIntent(center_entity_id='building-a', radius_m=100, kind='entrance',
                             observation='obstacle_visible', max_age_hours=None)
        with patch('app.spatial.vision.interpret_question', return_value=(intent, {})):
            response = self.client.post(f'/spatial/datasets/{self.dataset_id}/ask',
                                        json={'question': 'A 楼 100 米内哪些入口有障碍？'})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['evidence']['older_evidence_count'], 1)
        self.assertEqual(result['evidence']['status'], 'insufficient_evidence')
        self.assertEqual(result['evidence']['citations'], [])
        self.assertIn('回溯 24 小时', result['answer'])
        self.assertIn('可扩大查询时间范围查看', result['answer'])

    def test_validation_and_dataset_isolation(self):
        other = self.client.post('/spatial/datasets', json=self.dataset).json()['id']
        r = self.client.post(f'/spatial/datasets/{other}/annotations', json={
            'image_id': self.image_id, 'annotation': ANNOTATION, 'source_note': 'wrong dataset',
        })
        self.assertEqual(r.status_code, 422)
        for changes in ({'radius_m': -1}, {'center_entity_id': 'entrance-unlocated'},
                        {'center_entity_id': 'missing'}, {'as_of': '2026-10-18T12:00:00'}):
            r = self.client.post(f'/spatial/datasets/{self.dataset_id}/query', json={**self.query, **changes})
            self.assertEqual(r.status_code, 422)
        for changes in ({'content_base64': 'not-base64'}, {'captured_at': '2026-10-18T10:00:00'},
                        {'mime_type': 'image/jpeg'}, {'evidence_basis': 'not-an-enum'}):
            r = self.client.post(f'/spatial/datasets/{self.dataset_id}/images', json={**self.image_payload, **changes})
            self.assertEqual(r.status_code, 422)
        for changes in ({'entity_id': 'missing'}, {'approved': True},
                        {'bbox': {'x_min': 0.9, 'x_max': 0.1, 'y_min': 0, 'y_max': 1}}):
            r = self.client.post(f'/spatial/datasets/{self.dataset_id}/annotations', json={
                'image_id': self.image_id, 'annotation': {**ANNOTATION, **changes}, 'source_note': 'invalid',
            })
            self.assertEqual(r.status_code, 422)

    def test_distance_math_and_radius_boundary(self):
        a = Coordinates(latitude=0, longitude=0)
        b = Coordinates(latitude=0, longitude=1)
        self.assertAlmostEqual(distance_m(a, b), 111195.08, places=2)
        self.assertEqual(distance_m(a, a), 0)
        self.assertAlmostEqual(distance_m(a, b), distance_m(b, a), places=8)
        self.assertAlmostEqual(distance_m(Coordinates(latitude=0, longitude=179.999),
                                         Coordinates(latitude=0, longitude=-179.999)), 222.39, places=2)
        self.review(self.propose())
        boundary = distance_m(a, Coordinates(latitude=0, longitude=0.0005))
        self.assertEqual(len(self.ask(radius_m=boundary)['citations']), 1)
        self.assertFalse(self.ask(radius_m=boundary - 0.001)['citations'])

    def test_model_adapter_success_and_failure_without_network(self):
        original_client = httpx.Client
        seen = []

        def gateway(request):
            payload = json.loads(request.content)
            seen.append(payload)
            self.assertEqual(request.headers['Authorization'], 'Bearer test-secret')
            return httpx.Response(200, json={'choices': [{'message': {
                'content': json.dumps({'annotations': [ANNOTATION]})}}]})

        env = {'VISION_CHAT_URL': 'https://vision.invalid/v1/chat/completions',
               'VISION_API_KEY': 'test-secret', 'VISION_MODEL': 'test-vision'}
        with patch.dict(os.environ, env), patch('app.vision.httpx.Client', side_effect=lambda **kwargs:
                original_client(transport=httpx.MockTransport(gateway), **kwargs)):
            r = self.client.post(f'/spatial/images/{self.image_id}/analyze')
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0]['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,'))
        candidate = r.json()['annotations'][0]
        self.assertEqual(candidate['origin'], 'ai')
        self.assertEqual(self.ask()['citations'], [])
        self.review(candidate['id'])
        self.assertEqual(len(self.ask()['citations']), 1)
        self.assertNotIn('test-secret', self.client.get('/spatial/runs/' + r.json()['run_id']).text)
        for response in (httpx.Response(200, json={'choices': []}),
                         httpx.Response(429, text='test-secret upstream failure'),
                         httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({
                             'annotations': [{**ANNOTATION, 'entity_id': 'invented'}]})}}]})):
            with patch.dict(os.environ, env), patch('app.vision.httpx.Client', side_effect=lambda **kwargs:
                    original_client(transport=httpx.MockTransport(lambda request: response), **kwargs)):
                r = self.client.post(f'/spatial/images/{self.image_id}/analyze')
            self.assertEqual(r.status_code, 502)
            self.assertNotIn('test-secret', r.text)
        with patch.dict(os.environ, {'VISION_API_KEY': ''}):
            r = self.client.post(f'/spatial/images/{self.image_id}/analyze')
        self.assertEqual(r.status_code, 503)
        records = self.client.get(f'/spatial/datasets/{self.dataset_id}/annotations').json()['annotations']
        self.assertEqual(len(records), 1)

    def test_natural_question_uses_reviewed_spatial_evidence(self):
        # /ask measures the time window from now, so the evidence image must be fresh.
        fresh = self.upload({**self.image_payload, 'captured_at': datetime.now(timezone.utc).isoformat()})
        self.review(self.propose(image_id=fresh))
        intent = QueryIntent(center_entity_id='building-a', radius_m=100, kind='entrance',
                             observation='obstacle_visible', max_age_hours=None)
        with patch('app.spatial.vision.interpret_question', return_value=(intent, {})):
            response = self.client.post(f'/spatial/datasets/{self.dataset_id}/ask',
                                        json={'question': 'A 楼 100 米内哪些入口有障碍？'})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['interpreted_query']['max_age_hours'], 24)
        run = self.client.get('/spatial/runs/' + result['run_id']).json()
        self.assertEqual(run['interpreted_query']['center_entity_id'], 'building-a')
        self.assertEqual(result['evidence']['status'], 'evidence_found')
        self.assertEqual(len(result['evidence']['citations']), 1)
        self.assertEqual(result['evidence']['citations'][0]['annotation_id'],
                         self.client.get(f'/spatial/datasets/{self.dataset_id}/annotations').json()['annotations'][0]['id'])

    def test_natural_question_clarifies_without_retrieval(self):
        for intent in (
            QueryIntent(center_entity_id=None, radius_m=100, kind='entrance',
                        observation='obstacle_visible', max_age_hours=None),
            QueryIntent(center_entity_id='building-a', radius_m=None, kind='entrance',
                        observation='obstacle_visible', max_age_hours=None),
            QueryIntent(center_entity_id='entrance-unlocated', radius_m=100, kind='entrance',
                        observation='obstacle_visible', max_age_hours=None),
        ):
            with patch('app.spatial.vision.interpret_question', return_value=(intent, {})), \
                    patch('app.spatial.query') as retrieve:
                response = self.client.post(f'/spatial/datasets/{self.dataset_id}/ask',
                                            json={'question': '附近情况怎么样？'})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['status'], 'clarification_needed')
            self.assertIsNone(response.json()['evidence'])
            retrieve.assert_not_called()

    def test_natural_question_gateway_contract(self):
        url = f'/spatial/datasets/{self.dataset_id}/ask'
        original_client = httpx.Client
        env = {'VISION_CHAT_URL': 'https://vision.invalid/v1/chat/completions',
               'VISION_API_KEY': 'test-secret', 'VISION_MODEL': 'test-chat'}
        intent = {'center_entity_id': 'building-a', 'radius_m': 100, 'kind': 'entrance',
                  'observation': 'obstacle_visible', 'max_age_hours': None}
        seen = []

        def gateway(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, json={'choices': [{'message': {
                'content': '```json\n' + json.dumps(intent) + '\n```'}}]})

        with patch.dict(os.environ, env), patch('app.vision.httpx.Client', side_effect=lambda **kwargs:
                original_client(transport=httpx.MockTransport(gateway), **kwargs)):
            r = self.client.post(url, json={'question': 'A ? 100 ??????????????????????'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['status'], 'answered')
        self.assertEqual(r.json()['evidence']['citations'], [])
        self.assertEqual(seen[0]['messages'][1]['role'], 'user')
        self.assertNotIn('test-secret', self.client.get('/spatial/runs/' + r.json()['run_id']).text)
        bad = json.dumps({**intent, 'center_entity_id': 'invented'})
        with patch.dict(os.environ, env), patch('app.vision.httpx.Client', side_effect=lambda **kwargs:
                original_client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
                    'choices': [{'message': {'content': bad}}]})), **kwargs)):
            r = self.client.post(url, json={'question': 'A ????'})
        self.assertEqual(r.status_code, 502)

    def test_natural_question_model_errors_are_explicit(self):
        url = f'/spatial/datasets/{self.dataset_id}/ask'
        with patch('app.spatial.vision.interpret_question', side_effect=vision.VisionUnavailable('Configure model')):
            self.assertEqual(self.client.post(url, json={'question': 'A 楼附近？'}).status_code, 503)
        with patch('app.spatial.vision.interpret_question', side_effect=vision.VisionFailure('Invalid intent')):
            response = self.client.post(url, json={'question': 'A 楼附近？'})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('secret', response.text)


if __name__ == '__main__':
    unittest.main()
