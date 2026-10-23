import hashlib
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import create_app
from app.passwords import hash_password
from app.account_config import edit_accounts, read_accounts, accounts_path


class LoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = 'test-only-password-123'
        cls.password_hash = hash_password(cls.password)

    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.config = self.folder / 'access.json'
        self.users = [{'user_id': 'reader', 'workspace': w, 'role': 'viewer',
                       'token_sha256': hashlib.sha256(w.encode()).hexdigest(),
                       'password_hash': self.password_hash, 'enabled': True} for w in ('default', 'other')]
        self.write_config()
        self.client = self.enterContext(TestClient(self.app()))

    def write_config(self):
        if accounts_path(self.config).exists():
            with edit_accounts(self.config) as body:
                body['users'] = self.users
        else:
            self.config.write_text(json.dumps({'users': self.users}), encoding='utf-8')

    def app(self):
        return create_app(self.folder / 'auth.db', mode='team', access_config=self.config)

    def login(self, **changes):
        return self.client.post('/auth/login', json={
            'user_id': 'reader', 'workspace': 'default', 'password': self.password, **changes})

    def headers(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        return {'Authorization': 'Bearer ' + response.json()['access_token']}

    def test_sessions_roles_isolation_and_logout_across_workers(self):
        response = self.login()
        headers = self.headers(response)
        self.assertIn('no-store', response.headers['cache-control'])
        self.assertNotIn('password', json.dumps(response.json()['identity']))
        self.assertEqual(self.client.get('/auth/me', headers=headers).json(),
                         {'user_id': 'reader', 'workspace': 'default', 'role': 'viewer'})
        self.assertEqual(self.client.post('/spatial/datasets', headers=headers, json={}).status_code, 403)
        other = self.headers(self.login(workspace='other'))
        self.assertEqual(self.client.get('/auth/me', headers=other).json()['workspace'], 'other')
        with closing(self.client.app.state.store.connect()) as db:
            stored = db.execute('SELECT token_sha256 FROM auth_sessions').fetchall()
            self.assertNotIn(response.json()['access_token'], str(stored))
        with TestClient(self.app()) as worker:
            self.assertEqual(worker.get('/auth/me', headers=headers).status_code, 200)
            self.assertTrue(worker.post('/auth/logout', headers=headers).json()['session_revoked'])
        self.assertEqual(self.client.get('/auth/me', headers=headers).status_code, 401)
        self.assertEqual(self.client.get('/auth/me', headers=other).status_code, 200)
        legacy = {'Authorization': 'Bearer default'}
        self.assertFalse(self.client.post('/auth/logout', headers=legacy).json()['session_revoked'])
        self.assertEqual(self.client.get('/auth/me', headers=legacy).status_code, 200)

    def test_invalid_credentials_validation_and_public_surface(self):
        bad = self.login(password='incorrect').json()
        self.assertEqual(self.login(user_id='unknown').json(), bad)
        self.users[0]['enabled'] = False
        self.write_config()
        self.assertEqual(self.login().json(), bad)
        for payload in ({'password': self.password}, {'user_id': 'reader', 'password': 'x' * 257},
                        {'user_id': 'reader', 'password': {'secret': self.password}}):
            response = self.client.post('/auth/login', json=payload)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(self.password, response.text)
        self.assertEqual(self.client.post('/auth/login', content='x' * 4097).status_code, 413)
        for path in ('/auth/me', '/auth/login', '/docs', '/openapi.json'):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.post('/auth/logout').status_code, 401)

    def test_expiry_disable_password_reset_and_token_rotation(self):
        headers = self.headers(self.login())
        with closing(self.client.app.state.store.connect()) as db, db:
            db.execute('UPDATE auth_sessions SET expires_at=0')
        self.assertEqual(self.client.get('/auth/me', headers=headers).status_code, 401)
        for field, value in [('enabled', False), ('password_hash', hash_password(self.password)),
                             ('token_sha256', hashlib.sha256(b'rotated').hexdigest())]:
            headers = self.headers(self.login())
            original = self.users[0][field]
            self.users[0][field] = value
            self.write_config()
            self.assertEqual(self.client.get('/auth/me', headers=headers).status_code, 401, field)
            self.users[0][field] = original
            self.write_config()

    def test_login_throttle_shared_and_local_mode_compatibility(self):
        with patch('app.auth.verify_password', return_value=False), TestClient(self.app()) as worker:
            for i in range(10):
                client = self.client if i % 2 else worker
                self.assertEqual(client.post('/auth/login', json={'user_id': 'reader',
                    'password': 'wrong'}).status_code, 401)
            self.assertEqual(self.login().status_code, 429)
        with TestClient(create_app(self.folder / 'local.db', mode='local')) as local:
            self.assertEqual(local.get('/auth/me').json()['user_id'], 'local')
            self.assertEqual(local.post('/auth/login', json={}).status_code, 409)

    def test_cli_password_reset_preserves_role_and_token(self):
        from app.manage import main
        original = self.users[0].copy()
        with (patch('sys.argv', ['manage', '--config', str(self.config), '--user', 'reader', '--set-password']),
              patch('app.manage.getpass.getpass', return_value=self.password), patch('builtins.print')):
            main()
        account = next(u.model_dump() for u in read_accounts(self.config).users if u.workspace == 'default')
        self.assertEqual(account['role'], original['role'])
        self.assertEqual(account['token_sha256'], original['token_sha256'])
        self.assertNotEqual(account['password_hash'], original['password_hash'])
        self.assertNotIn(self.password, self.config.read_text())
