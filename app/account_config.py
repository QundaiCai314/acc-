"""Serialize CLI and web account changes across processes on a local disk."""
import os
import secrets
import sqlite3
from contextlib import contextmanager, closing

from .access import AccessConfig


@contextmanager
def edit_accounts(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    # ponytail: SQLite supplies a cross-platform process lock for this small JSON directory.
    with closing(sqlite3.connect(str(path) + '.lock.db', timeout=10)) as lock, lock:
        lock.execute('CREATE TABLE IF NOT EXISTS mutex (id INTEGER)')
        lock.execute('BEGIN IMMEDIATE')
        body = AccessConfig.model_validate_json(path.read_text(encoding='utf-8')).model_dump() if path.exists() else {'users': []}
        yield body
        config = AccessConfig.model_validate(body)
        temporary = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
        try:
            with temporary.open('x', encoding='utf-8') as output:
                output.write(config.model_dump_json(indent=2))
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
