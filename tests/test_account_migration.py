import hashlib
import json
import tempfile
import subprocess
import sys
import time
import unittest
from contextlib import closing
from pathlib import Path

from app.account_config import (initialize_accounts, account_connection,
    account_transaction, read_accounts)
from app.store import Store


class AccountMigrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.root / 'access.json'
        self.seed = {'users': [{'user_id': 'admin', 'workspace': 'default', 'role': 'admin',
                      'token_sha256': hashlib.sha256(b'test-only').hexdigest()}]}
        self.path.write_text(json.dumps(self.seed), encoding='utf-8')
        self.store = Store(self.root / 'legacy.db')

    def test_restart_does_not_reimport_consumed_registration_or_old_accounts(self):
        self.store.create_registration('default', 'new', 'legacy-hash', '2026-10-23')
        initialize_accounts(self.path, self.store)
        with account_transaction(self.path) as (body, db):
            self.assertEqual(db.execute('SELECT COUNT(*) FROM registration_requests').fetchone()[0], 1)
            db.execute('DELETE FROM registration_requests')
            body['users'][0]['enabled'] = False
        initialize_accounts(self.path, Store(self.store.path))
        self.assertFalse(read_accounts(self.path).users[0].enabled)
        with closing(account_connection(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM registration_requests').fetchone()[0], 0)
        self.assertIsNotNone(self.store.registration('default', 'new'))

    def test_failed_import_rolls_back_and_retry_imports_all_rows(self):
        initialize_accounts(self.path)
        with account_transaction(self.path) as (_, db):
            db.execute('INSERT INTO registration_requests VALUES (?, ?, ?, ?)',
                       ('default', 'new', 'other-hash', '2026-10-23'))
        self.store.create_registration('default', 'new', 'legacy-hash', '2026-10-23')
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            initialize_accounts(self.path, self.store)
        with closing(account_connection(self.path)) as db, db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM imports').fetchone()[0], 0)
            db.execute('DELETE FROM registration_requests')
        initialize_accounts(self.path, self.store)
        with closing(account_connection(self.path)) as db:
            self.assertEqual(db.execute('SELECT password_hash FROM registration_requests').fetchone()[0], 'legacy-hash')

    def test_corrupt_or_future_database_does_not_reseed(self):
        initialize_accounts(self.path, self.store)
        with closing(account_connection(self.path)) as db, db:
            db.execute('DELETE FROM config')
        initialize_accounts(self.path, self.store)
        with self.assertRaises(ValueError):
            read_accounts(self.path)
        with closing(account_connection(self.path)) as db:
            db.execute('PRAGMA user_version=999')
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            initialize_accounts(self.path, self.store)

    def test_killed_writer_rolls_back_and_database_can_be_reopened(self):
        initialize_accounts(self.path, self.store)
        ready = self.root / 'writer-ready'
        script = '''
import sys
from pathlib import Path
from app.account_config import account_connection
db = account_connection(Path(sys.argv[1]))
db.execute('BEGIN IMMEDIATE')
db.execute('DELETE FROM config')
Path(sys.argv[2]).write_text('ready')
sys.stdin.read()
'''
        child = subprocess.Popen([sys.executable, '-c', script, str(self.path), str(ready)],
                                 stdin=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 15
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(ready.exists(), 'Child failed to enter the uncommitted write')
            child.kill()
            child.wait(timeout=5)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stdin.close()
        initialize_accounts(self.path, self.store)
        self.assertEqual(read_accounts(self.path).users[0].user_id, 'admin')
        with closing(account_connection(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_four_processes_do_not_lose_account_updates(self):
        initialize_accounts(self.path, self.store)
        script = '''
import sys
from pathlib import Path
from app.account_config import account_transaction
for _ in range(10):
    with account_transaction(Path(sys.argv[1])) as (body, db):
        body['requests_per_minute'] += 1
'''
        children = [subprocess.Popen([sys.executable, '-c', script, str(self.path)]) for _ in range(4)]
        try:
            for child in children:
                self.assertEqual(child.wait(timeout=30), 0)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
        self.assertEqual(read_accounts(self.path).requests_per_minute, 160)
