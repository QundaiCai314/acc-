import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.spatial_models import ProposalBatch
from app.account_config import accounts_path, edit_accounts, account_connection


ROOT = Path(__file__).resolve().parents[1]
PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC'


class TeamTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(self.temp)
        self.config = {'users': [
            {'user_id': role, 'workspace': workspace, 'role': role,
             'token_sha256': hashlib.sha256(f'{workspace}-{role}'.encode()).hexdigest()}
            for workspace in ('default', 'other') for role in ('viewer', 'contributor', 'reviewer', 'admin')]}
        self.config_path = self.path / 'access.json'
        self.write_config()
        self.client = self.enterContext(TestClient(create_app(self.path/'team.db', mode='team', access_config=self.config_path)))
        self.dataset = json.loads((ROOT/'examples/spatial_dataset.json').read_text(encoding='utf-8'))
        self.ds = self.client.post('/spatial/datasets', json=self.dataset, headers=self.auth('contributor')).json()['id']

    def write_config(self):
        if accounts_path(self.config_path).exists():
            with edit_accounts(self.config_path) as body:
                body.update(self.config)
        else:
            self.config_path.write_text(json.dumps(self.config), encoding='utf-8')

    def auth(self, role='viewer', workspace='default'):
        return {'Authorization': f'Bearer {workspace}-{role}'}

    def annotation(self):
        image = self.client.post(f'/spatial/datasets/{self.ds}/images', headers=self.auth('contributor'), json={
            'name': 'test.png', 'captured_at': '2026-10-19T00:00:00Z', 'source': 'test',
            'evidence_basis': 'exercise', 'mime_type': 'image/png', 'content_base64': PNG}).json()['id']
        candidate = self.client.post(f'/spatial/datasets/{self.ds}/annotations', headers=self.auth('contributor'), json={
            'image_id': image, 'source_note': 'test', 'annotation': {'entity_id': 'entrance-near',
            'observation': 'obstacle_visible', 'description': 'test', 'confidence': .8,
            'bbox': {'x_min': 0, 'y_min': 0, 'x_max': 1, 'y_max': 1}}}).json()['id']
        return image, candidate

    def test_authentication_roles_identity_and_revocation(self):
        url = f'/spatial/datasets/{self.ds}'
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get('/docs').status_code, 401)
        self.assertEqual(self.client.get('/health').status_code, 200)
        self.assertEqual(self.client.post('/spatial/datasets', json=self.dataset, headers=self.auth()).status_code, 403)
        self.assertEqual(self.client.get(url, headers=self.auth()).json()['snapshot']['curator'], 'contributor')
        image, candidate = self.annotation()
        review = {'reviewer': 'forged-admin', 'action': 'approve', 'note': 'checked'}
        endpoint = f'/spatial/annotations/{candidate}/review'
        self.assertEqual(self.client.post(endpoint, json=review, headers=self.auth('contributor')).status_code, 403)
        result = self.client.post(endpoint, json=review, headers=self.auth('reviewer'))
        self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(result.json()['reviewer'], 'reviewer')
        self.assertEqual(self.client.get('/integrations', headers=self.auth()).status_code, 403)
        self.config['users'][0]['enabled'] = False
        self.write_config()
        self.assertEqual(self.client.get(url, headers=self.auth()).status_code, 401)
        with closing(account_connection(self.config_path)) as db, db:
            db.execute("UPDATE config SET body='invalid'")
        self.assertEqual(self.client.get(url, headers=self.auth('admin')).status_code, 503)

    def test_review_lease_is_atomic_scoped_and_blocks_other_reviewers(self):
        _, candidate = self.annotation()
        base = f'/spatial/annotations/{candidate}'
        self.assertEqual(self.client.post(base+'/claim', headers=self.auth('viewer')).status_code, 403)
        self.assertEqual(self.client.get(base+'/lease', headers=self.auth('admin', 'other')).status_code, 404)
        def claim(role):
            return role, self.client.post(base+'/claim', headers=self.auth(role)).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = dict(pool.map(claim, ['reviewer', 'admin']))
        self.assertEqual(sorted(results.values()), [200, 409])
        winner = next(role for role, code in results.items() if code == 200)
        loser = next(role for role, code in results.items() if code == 409)
        decision = {'reviewer': 'forged', 'action': 'approve', 'note': 'checked'}
        self.assertEqual(self.client.post(base+'/review', headers=self.auth(loser), json=decision).status_code, 409)
        self.client.post(base+'/release', headers=self.auth(loser))
        self.assertEqual(self.client.get(base+'/lease', headers=self.auth()).json()['lease']['user_id'], winner)
        with closing(self.client.app.state.store.connect()) as db, db:
            db.execute('UPDATE review_leases SET expires_at=0 WHERE annotation_id=?', (candidate,))
        self.assertEqual(self.client.post(base+'/claim', headers=self.auth(loser)).status_code, 200)
        self.assertEqual(self.client.post(base+'/review', headers=self.auth(loser), json=decision).status_code, 201)
        self.assertIsNone(self.client.get(base+'/lease', headers=self.auth()).json()['lease'])
        self.assertEqual(self.client.post(base+'/claim', headers=self.auth(winner)).status_code, 409)

    def test_camera_pose_is_optional_validated_and_kept_with_evidence(self):
        payload = {'name': 'pose.png', 'captured_at': '2026-10-19T00:00:00Z', 'source': 'test',
                   'evidence_basis': 'exercise', 'mime_type': 'image/png', 'content_base64': PNG,
                   'camera_pose': {'coordinates': {'latitude': 0, 'longitude': 0}, 'heading_deg': 315,
                                   'horizontal_fov_deg': 65, 'position_basis': 'exercise', 'source_note': 'synthetic'}}
        path = f'/spatial/datasets/{self.ds}/images'
        invalid = copy.deepcopy(payload)
        invalid['camera_pose']['heading_deg'] = 360
        self.assertEqual(self.client.post(path, headers=self.auth('contributor'), json=invalid).status_code, 422)
        result = self.client.post(path, headers=self.auth('contributor'), json=payload)
        self.assertEqual(result.status_code, 201, result.text)
        image = self.client.get('/spatial/images/'+result.json()['id'], headers=self.auth()).json()
        self.assertEqual(image['camera_pose']['heading_deg'], 315)
        self.assertIsNone(image['camera_pose']['altitude_m'])
        candidate = self.client.post(f'/spatial/datasets/{self.ds}/annotations', headers=self.auth('contributor'), json={
            'image_id': image['id'], 'source_note': 'synthetic pose', 'annotation': {
                'entity_id': 'entrance-near', 'observation': 'obstacle_visible', 'description': 'test',
                'confidence': .8, 'bbox': {'x_min': 0, 'y_min': 0, 'x_max': 1, 'y_max': 1}}}).json()['id']
        self.assertEqual(self.client.post(f'/spatial/annotations/{candidate}/review', headers=self.auth('reviewer'),
            json={'reviewer': 'ignored', 'action': 'approve', 'note': 'checked'}).status_code, 201)
        evidence = self.client.post(f'/spatial/datasets/{self.ds}/query', headers=self.auth(), json={
            'center_entity_id': 'building-a', 'radius_m': 100, 'as_of': '2026-10-19T01:00:00Z',
            'max_age_hours': 24, 'kind': 'entrance', 'observation': 'obstacle_visible'})
        self.assertEqual(evidence.status_code, 200, evidence.text)
        self.assertEqual(evidence.json()['citations'][0]['camera_pose'], image['camera_pose'])

    def test_workspace_isolation_including_images_reviews_and_legacy(self):
        image, candidate = self.annotation()
        urls = [f'/spatial/datasets/{self.ds}', f'/spatial/datasets/{self.ds}/annotations',
                f'/spatial/images/{image}', f'/spatial/images/{image}/content']
        for url in urls:
            self.assertEqual(self.client.get(url, headers=self.auth('admin', 'other')).status_code, 404)
        review = {'reviewer': 'other', 'action': 'approve', 'note': 'test'}
        self.assertEqual(self.client.post(f'/spatial/annotations/{candidate}/review', json=review,
                                         headers=self.auth('admin','other')).status_code, 404)
        scenario = json.loads((ROOT/'examples/scenario.json').read_text(encoding='utf-8'))
        record = self.client.post('/scenarios', json=scenario, headers=self.auth('contributor')).json()
        self.assertEqual(self.client.get('/scenarios/'+record['id'], headers=self.auth('admin','other')).status_code, 404)
        # ContextVars must not leak identities across concurrent requests or worker threads.
        def who(workspace):
            return self.client.get('/auth/me', headers=self.auth('admin', workspace)).json()['workspace']
        workspaces = ['default', 'other'] * 8
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(who, workspaces)), workspaces)

    def test_concurrent_reviews_and_withdrawals_are_unique(self):
        _, candidate = self.annotation()
        def submit(action):
            payload = {'reviewer': 'forged', 'note': 'test'}
            if action == 'review':
                payload['action'] = 'approve'
            return self.client.post(f'/spatial/annotations/{candidate}/{action}', json=payload,
                                    headers=self.auth('reviewer')).status_code
        for action in ('review', 'withdraw'):
            with ThreadPoolExecutor(max_workers=4) as pool:
                statuses = list(pool.map(submit, [action]*4))
            self.assertEqual(statuses.count(201), 1, statuses)
            self.assertEqual(statuses.count(409), 3, statuses)

    def test_rate_limit_shared_across_app_instances_and_body_limit(self):
        self.config['requests_per_minute'] = 2
        self.write_config()
        with TestClient(create_app(self.path/'team.db', mode='team', access_config=self.config_path)) as other:
            self.assertEqual(self.client.get('/auth/me', headers=self.auth()).status_code, 200)
            self.assertEqual(other.get('/auth/me', headers=self.auth()).status_code, 200)
            self.assertEqual(other.get('/auth/me', headers=self.auth()).status_code, 429)
        response = self.client.post('/spatial/datasets', content=b'x'*8_000_001, headers=self.auth('admin'))
        self.assertEqual(response.status_code, 413)

    def test_local_mode_rejects_remote_and_team_requires_valid_config(self):
        with TestClient(create_app(self.path/'local.db', mode='local'), client=('192.0.2.1', 1234)) as remote:
            self.assertEqual(remote.get('/auth/me').status_code, 403)
        with self.assertRaises(FileNotFoundError):
            with TestClient(create_app(self.path/'bad.db', mode='team', access_config=self.path/'missing.json')):
                pass

    def test_version_one_data_remains_in_default_workspace(self):
        legacy = self.path/'legacy.db'
        with closing(sqlite3.connect(legacy)) as db, db:
            db.execute('CREATE TABLE records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL)')
            db.execute('CREATE TABLE decisions (plan_id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            db.execute('PRAGMA user_version=1')
            db.execute('INSERT INTO records VALUES (?,?,?)', ('00000000-0000-0000-0000-000000000001',
                       'spatial_dataset', json.dumps({'id':'00000000-0000-0000-0000-000000000001','snapshot':self.dataset})))
        with TestClient(create_app(legacy, mode='team', access_config=self.config_path)) as client:
            url = '/spatial/datasets/00000000-0000-0000-0000-000000000001'
            self.assertEqual(client.get(url, headers=self.auth()).status_code, 200)
            self.assertEqual(client.get(url, headers=self.auth('admin','other')).status_code, 404)

    def test_analysis_idempotency_and_pagination(self):
        image, _ = self.annotation()
        url=f'/spatial/images/{image}/analyze'
        self.assertEqual(self.client.post(url,headers=self.auth('contributor')).status_code,422)
        with patch('app.spatial.vision.analyze',return_value=(ProposalBatch(annotations=[]),{})) as analyze:
            first=self.client.post(url,headers={**self.auth('contributor'),'Idempotency-Key':'test'})
            second=self.client.post(url,headers={**self.auth('contributor'),'Idempotency-Key':'test'})
        self.assertEqual(first.status_code,201,first.text)
        self.assertEqual(first.json(),second.json())
        analyze.assert_called_once()
        self.assertEqual(self.client.get('/spatial/runs/'+first.json()['run_id'],headers=self.auth()).status_code,403)
        self.assertEqual(self.client.get('/spatial/runs/'+first.json()['run_id'],headers=self.auth('admin','other')).status_code,404)
        self.annotation()
        page=self.client.get(f'/spatial/datasets/{self.ds}/images?limit=1',headers=self.auth()).json()
        self.assertEqual(len(page['images']),1)
        self.assertEqual(page['next_offset'],1)
        self.assertNotIn('content_base64',page['images'][0])
        self.assertEqual(self.client.get('/spatial/datasets',headers=self.auth('admin','other')).json()['datasets'],[])


if __name__ == '__main__':
    unittest.main()
