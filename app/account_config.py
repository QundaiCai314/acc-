"""Transactional accounts and registrations; JSON is a one-time seed."""
import json
import sqlite3
from contextlib import contextmanager, closing
from pathlib import Path

from .access import AccessConfig


def accounts_path(path):
    return Path(str(path) + '.accounts.db')


def initialize_accounts(path, legacy_store=None):
    target = accounts_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target, timeout=10)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
            raise ValueError('Unsupported account database version')
        db.execute('CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS registration_requests ('
                   'workspace TEXT NOT NULL, user_id TEXT NOT NULL, password_hash TEXT NOT NULL, '
                   'created_at TEXT NOT NULL, PRIMARY KEY (workspace, user_id))')
        db.execute('CREATE TABLE IF NOT EXISTS imports (source TEXT PRIMARY KEY)')
        if version == 0 and not db.execute('SELECT 1 FROM config').fetchone() and path.exists():
            config = AccessConfig.model_validate_json(path.read_text(encoding='utf-8'))
            db.execute('INSERT INTO config VALUES (1, ?)', (config.model_dump_json(),))
        if legacy_store is not None:
            source_id = str(legacy_store.path.resolve())
            if not db.execute('SELECT 1 FROM imports WHERE source=?', (source_id,)).fetchone():
                with closing(legacy_store.connect()) as legacy:
                    pending = legacy.execute('SELECT * FROM registration_requests').fetchall()
                for workspace, user, password_hash, created in pending:
                    existing = db.execute('SELECT password_hash FROM registration_requests WHERE workspace=? AND user_id=?',
                                          (workspace, user)).fetchone()
                    if existing and existing[0] != password_hash:
                        raise ValueError('Conflicting pending registration during account migration')
                    db.execute('INSERT OR IGNORE INTO registration_requests VALUES (?, ?, ?, ?)',
                               (workspace, user, password_hash, created))
                db.execute('INSERT INTO imports VALUES (?)', (source_id,))
        db.execute('PRAGMA user_version=1')


def account_connection(path):
    # Missing authoritative storage must fail closed, never recreate from stale JSON.
    return sqlite3.connect(accounts_path(path).resolve().as_uri() + '?mode=rw', uri=True, timeout=10)


def read_accounts(path):
    with closing(account_connection(path)) as db:
        row = db.execute('SELECT body FROM config WHERE id=1').fetchone()
        if row is None:
            raise ValueError('Account configuration is empty')
        return AccessConfig.model_validate_json(row[0])


@contextmanager
def account_transaction(path):
    with closing(account_connection(path)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT body FROM config WHERE id=1').fetchone()
        body = json.loads(row[0]) if row else {'users': []}
        yield body, db
        config = AccessConfig.model_validate(body)
        db.execute('INSERT INTO config VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                   (config.model_dump_json(),))


@contextmanager
def edit_accounts(path):
    """CLI/bootstrap edits share the same transaction as web account changes."""
    initialize_accounts(path)
    with account_transaction(path) as (body, db):
        yield body
