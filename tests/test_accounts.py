import hashlib
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import create_app
from app.passwords import hash_password
from app.account_config import read_accounts, edit_accounts, account_transaction, account_connection
from contextlib import closing


class AccountFlowTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.config = self.directory / 'access.json'
        self.password = 'account-test-password'
        self.config.write_text(json.dumps({'users': [
            {'user_id': user, 'workspace': space, 'role': role,
             'token_sha256': hashlib.sha256(token.encode()).hexdigest(),
             'password_hash': hash_password(self.password)}
            for user, space, role, token in [('admin', 'default', 'admin', 'admin'),
                ('admin', 'other', 'admin', 'other'), ('reader', 'default', 'viewer', 'reader')]]}), encoding='utf-8')
        self.app = create_app(self.directory / 'test.db', mode='team', access_config=self.config)
        self.client = self.enterContext(TestClient(self.app))
        self.admin = {'Authorization': 'Bearer admin'}

    def register(self, user='new', **extra):
        return self.client.post('/auth/register', json={
            'user_id': user, 'workspace': 'default', 'password': self.password, **extra})

    def manage(self, action, user='new', **extra):
        return self.client.post('/auth/members', headers=self.admin, json={
            'user_id': user, 'action': action, **extra})

    def login(self, user='new', password=None):
        r = self.client.post('/auth/login', json={'user_id': user, 'password': password or self.password})
        self.assertEqual(r.status_code, 200, r.text)
        return {'Authorization': 'Bearer ' + r.json()['access_token']}

    def test_registration_approval_permissions_and_scope(self):
        self.assertEqual(self.register(role='admin').status_code, 422)
        self.assertEqual(self.register(workspace='unknown').status_code, 409)
        self.assertEqual(self.register().status_code, 202)
        self.assertEqual(self.register().status_code, 409)
        self.assertEqual(self.client.post('/auth/login', json={'user_id': 'new', 'password': self.password}).status_code, 401)
        listing = self.client.get('/auth/members', headers=self.admin)
        self.assertNotIn('password_hash', listing.text)
        self.assertNotIn('token_sha256', listing.text)
        self.assertEqual(listing.json()['pending'][0]['user_id'], 'new')
        reader = {'Authorization': 'Bearer reader'}
        self.assertEqual(self.client.get('/auth/me', headers=reader).status_code, 200)
        self.assertEqual(self.client.get('/auth/members', headers=reader).status_code, 403)
        self.assertEqual(self.client.post('/auth/members', headers=reader, json={'user_id': 'new', 'action': 'approve'}).status_code, 403)
        other = {'Authorization': 'Bearer other'}
        self.assertFalse(self.client.get('/auth/members', headers=other).json()['pending'])
        self.assertEqual(self.client.post('/auth/members', headers=other, json={'user_id': 'new', 'action': 'approve'}).status_code, 409)
        self.assertEqual(self.manage('approve', role='admin').status_code, 422)
        self.assertEqual(self.manage('approve', role='contributor').status_code, 200)
        headers = self.login()
        self.assertEqual(self.client.get('/auth/me', headers=headers).json()['role'], 'contributor')
        self.assertEqual(self.manage('disable').status_code, 200)
        self.assertEqual(self.manage('enable').status_code, 200)
        self.assertEqual(self.client.get('/auth/me', headers=headers).status_code, 401)
        self.login()
        self.assertEqual(self.manage('disable', user='admin').status_code, 409)

    def test_password_change_and_one_time_expiring_reset(self):
        headers = self.login('reader')
        code = self.manage('reset', user='reader').json()['reset_code']
        self.assertNotIn(code, self.config.read_text())
        new = 'new-account-password'
        payload = {'user_id': 'reader', 'password': new, 'reset_code': code}
        self.assertEqual(self.client.post('/auth/reset-password', json={**payload, 'reset_code': 'wrong'}).status_code, 400)
        self.assertEqual(self.client.post('/auth/reset-password', json=payload).status_code, 200)
        self.assertEqual(self.client.post('/auth/reset-password', json=payload).status_code, 400)
        self.assertEqual(self.client.get('/auth/me', headers=headers).status_code, 401)
        headers = self.login('reader', new)
        self.assertEqual(self.client.post('/auth/password', headers=headers, json={
            'current_password': 'incorrect', 'password': self.password}).status_code, 400)
        self.assertEqual(self.client.post('/auth/password', headers=headers, json={
            'current_password': new, 'password': self.password}).status_code, 200)
        self.assertEqual(self.client.get('/auth/me', headers=headers).status_code, 401)
        self.login('reader')
        code = self.manage('reset', user='reader').json()['reset_code']
        with edit_accounts(self.config) as body:
            body['users'][2]['reset_expires'] = 1
        self.assertEqual(self.client.post('/auth/reset-password', json={**payload, 'reset_code': code}).status_code, 400)

    def test_concurrent_approvals_and_rejection(self):
        self.assertEqual(self.register('one').status_code, 202)
        self.assertEqual(self.register('two').status_code, 202)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda user: self.manage('approve', user).status_code, ['one', 'two']))
        self.assertEqual(results, [200, 200])
        self.assertEqual(len(read_accounts(self.config).users), 5)
        self.assertEqual(self.register('three').status_code, 202)
        self.assertEqual(self.manage('reject', 'three').status_code, 200)
        self.assertFalse(self.client.get('/auth/members', headers=self.admin).json()['pending'])

    def test_validation_limits_and_local_mode(self):
        bad = self.register(password='short')
        self.assertEqual(bad.status_code, 422)
        self.assertNotIn('short', bad.text)
        self.assertEqual(self.client.post('/auth/register', content='x' * 4097).status_code, 413)
        with TestClient(create_app(self.directory / 'local.db', mode='local')) as local:
            for path in ('/auth/register', '/auth/reset-password', '/auth/password', '/auth/members'):
                self.assertEqual(local.post(path, json={}).status_code, 409)
        for i in range(5):
            self.assertEqual(self.client.post('/auth/reset-password', json={
                'user_id': 'reader', 'password': self.password, 'reset_code': 'wrong'}).status_code, 400)
        self.assertEqual(self.client.post('/auth/reset-password', json={
            'user_id': 'reader', 'password': self.password, 'reset_code': 'wrong'}).status_code, 429)

    def test_cli_disable_permanently_revokes_sessions_tokens_and_reset_codes(self):
        from app.manage import main
        session = self.login('reader')
        code = self.manage('reset', user='reader').json()['reset_code']
        with (patch('sys.argv', ['manage', '--config', str(self.config), '--user', 'reader', '--disable']),
              patch('builtins.print')):
            main()
        self.assertEqual(self.manage('enable', user='reader').status_code, 200)
        self.assertEqual(self.client.get('/auth/me', headers=session).status_code, 401)
        self.assertEqual(self.client.get('/auth/me', headers={'Authorization': 'Bearer reader'}).status_code, 401)
        self.assertEqual(self.client.post('/auth/reset-password', json={
            'user_id': 'reader', 'password': self.password, 'reset_code': code}).status_code, 400)
        self.login('reader')

    def test_full_account_capacity_preserves_pending_registration(self):
        self.assertEqual(self.register().status_code, 202)
        with edit_accounts(self.config) as body:
            for i in range(997):
                body['users'].append({**body['users'][2], 'user_id': f'fill{i}',
                    'token_sha256': hashlib.sha256(f'fill{i}'.encode()).hexdigest()})
        self.assertEqual(self.manage('approve').status_code, 409)
        self.assertEqual(len(read_accounts(self.config).users), 1000)
        self.assertIsNotNone(self.pending('new'))

    def test_stale_pending_registration_can_be_rejected_after_interrupted_approval(self):
        with account_transaction(self.config) as (body, db):
            db.execute('INSERT INTO registration_requests VALUES (?, ?, ?, ?)',
                       ('default', 'reader', hash_password(self.password), '2026-10-22T00:00:00Z'))
        self.assertEqual(self.manage('approve', 'reader').status_code, 409)
        self.assertEqual(self.manage('reject', 'reader').status_code, 200)
        self.assertIsNone(self.pending('reader'))
        self.login('reader')

    def test_registration_rechecks_accounts_after_password_hashing(self):
        from app.account_config import edit_accounts
        def concurrent_create(password):
            digest = hash_password(password)
            with edit_accounts(self.config) as body:
                body['users'].append({**body['users'][2], 'user_id': 'new',
                    'token_sha256': hashlib.sha256(b'concurrently-created').hexdigest()})
            return digest
        with patch('app.auth.hash_password', side_effect=concurrent_create):
            self.assertEqual(self.register().status_code, 409)
        self.assertIsNone(self.pending('new'))

    def pending(self, user):
        with closing(account_connection(self.config)) as db:
            return db.execute('SELECT password_hash FROM registration_requests WHERE workspace=? AND user_id=?',
                              ('default', user)).fetchone()

    def test_approval_rolls_back_both_account_and_pending_on_write_failure(self):
        self.assertEqual(self.register().status_code, 202)
        # Fail the config write AFTER the pending row has been deleted in the transaction.
        with closing(account_connection(self.config)) as db, db:
            db.execute("CREATE TRIGGER fail_config BEFORE UPDATE ON config BEGIN SELECT RAISE(ABORT, 'injected'); END")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.manage('approve')
        self.assertIsNotNone(self.pending('new'))
        self.assertNotIn('new', [u.user_id for u in read_accounts(self.config).users])
        with closing(account_connection(self.config)) as db, db:
            db.execute('DROP TRIGGER fail_config')
        self.assertEqual(self.manage('approve').status_code, 200)
        self.assertIsNone(self.pending('new'))
        self.login()

    def test_same_registration_concurrent_approval_has_exactly_one_winner(self):
        self.assertEqual(self.register().status_code, 202)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.manage('approve').status_code, range(2)))
        self.assertEqual(sorted(results), [200, 409])
        self.assertIsNone(self.pending('new'))
        self.assertEqual(sum(u.user_id == 'new' for u in read_accounts(self.config).users), 1)
