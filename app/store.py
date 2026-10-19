import json
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .access import attributed, principal


class ReviewLeaseConflict(Exception):
    pass


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2, 3):
                raise RuntimeError(f'Unsupported database version: {version}; explicit migration required')
            db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS decisions (plan_id TEXT PRIMARY KEY REFERENCES records(id), body TEXT NOT NULL)')
            db.execute("CREATE INDEX IF NOT EXISTS records_workspace_kind_dataset ON records "
                       "(COALESCE(json_extract(body, '$.workspace_id'), 'default'), kind, json_extract(body, '$.dataset_id'))")
            # Existing duplicate withdrawals must be resolved explicitly, never silently discarded.
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_annotation_withdrawal ON records "
                       "(json_extract(body, '$.annotation_id')) WHERE kind = 'annotation_retraction'")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_artifact_withdrawal ON records "
                       "(json_extract(body, '$.artifact_id')) WHERE kind = 'artifact_retraction'")
            db.execute('CREATE TABLE IF NOT EXISTS rate_limits (bucket TEXT PRIMARY KEY, window INTEGER NOT NULL, count INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS operations (workspace TEXT NOT NULL, scope TEXT NOT NULL, '
                       'key TEXT NOT NULL, status TEXT NOT NULL, body TEXT, PRIMARY KEY (workspace, scope, key))')
            db.execute('CREATE TABLE IF NOT EXISTS review_leases ('
                       'annotation_id TEXT PRIMARY KEY REFERENCES records(id), workspace TEXT NOT NULL, '
                       'user_id TEXT NOT NULL, expires_at REAL NOT NULL)')
            db.execute('PRAGMA user_version = 3')
        with closing(self.connect()) as db:
            db.execute('PRAGMA journal_mode = WAL')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA foreign_keys = ON')
        return db

    def save(self, kind: str, body: dict) -> dict:
        record = {**attributed(body), 'id': str(uuid4()), 'created_at': datetime.now(timezone.utc).isoformat()}
        with closing(self.connect()) as db, db:
            db.execute('INSERT INTO records VALUES (?, ?, ?)',
                       (record['id'], kind, json.dumps(record, ensure_ascii=False)))
        return record

    def get(self, kind: str, identifier: str, metadata: bool = False) -> dict | None:
        with closing(self.connect()) as db:
            projection = "json_remove(body, '$.content_base64')" if metadata else 'body'
            row = db.execute(f"SELECT {projection} FROM records WHERE id = ? AND kind = ? "
                             "AND COALESCE(json_extract(body, '$.workspace_id'), 'default') = ?",
                             (identifier, kind, principal.get().workspace)).fetchone()
        return json.loads(row[0]) if row else None

    def list_records(self, kind: str, dataset_id: str | None, limit: int | None = None, offset: int = 0,
                     metadata: bool = False) -> list[dict]:
        with closing(self.connect()) as db:
            projection = "json_remove(body, '$.content_base64')" if metadata else 'body'
            rows = db.execute(
                f"SELECT {projection} FROM records WHERE kind = ? AND (? IS NULL OR json_extract(body, '$.dataset_id') = ?) "
                "AND COALESCE(json_extract(body, '$.workspace_id'), 'default') = ? ORDER BY rowid LIMIT ? OFFSET ?",
                (kind, dataset_id, dataset_id, principal.get().workspace, limit if limit is not None else -1, offset),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def reviewed_records(self, dataset_id: str) -> list[tuple[dict, dict]]:
        with closing(self.connect()) as db:
            rows = db.execute(
                "SELECT r.body, d.body FROM records r JOIN decisions d ON d.plan_id = r.id "
                "WHERE r.kind = 'annotation' AND json_extract(r.body, '$.dataset_id') = ? "
                "AND COALESCE(json_extract(r.body, '$.workspace_id'), 'default') = ? ORDER BY r.rowid",
                (dataset_id, principal.get().workspace),
            ).fetchall()
        return [(json.loads(record), json.loads(decision)) for record, decision in rows]

    def save_many(self, kind: str, bodies: list[dict]) -> list[dict]:
        records = [{**attributed(body), 'id': str(uuid4()), 'created_at': datetime.now(timezone.utc).isoformat()}
                   for body in bodies]
        with closing(self.connect()) as db, db:
            db.executemany('INSERT INTO records VALUES (?, ?, ?)',
                           [(r['id'], kind, json.dumps(r, ensure_ascii=False)) for r in records])
        return records

    def decide(self, plan_id: str, body: dict) -> dict:
        record = {**attributed(body), 'plan_id': plan_id, 'created_at': datetime.now(timezone.utc).isoformat()}
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM records WHERE id = ? "
                          "AND COALESCE(json_extract(body, '$.workspace_id'), 'default') = ?",
                          (plan_id, principal.get().workspace)).fetchone() is None:
                raise sqlite3.IntegrityError('Decision target not in workspace')
            lease = db.execute('SELECT user_id FROM review_leases WHERE annotation_id=? AND expires_at>?',
                               (plan_id, time.time())).fetchone()
            if lease and lease[0] != principal.get().user_id:
                raise ReviewLeaseConflict('Another reviewer holds this annotation; refresh after the lease expires')
            db.execute('INSERT INTO decisions VALUES (?, ?)', (plan_id, json.dumps(record, ensure_ascii=False)))
            db.execute('DELETE FROM review_leases WHERE annotation_id=?', (plan_id,))
        return record

    def review_lease(self, annotation_id: str):
        with closing(self.connect()) as db:
            row = db.execute('SELECT user_id, expires_at FROM review_leases '
                             'WHERE annotation_id=? AND workspace=? AND expires_at>?',
                             (annotation_id, principal.get().workspace, time.time())).fetchone()
        return {'user_id': row[0], 'expires_at': datetime.fromtimestamp(row[1], timezone.utc).isoformat()} if row else None

    def claim_review(self, annotation_id: str):
        actor, now = principal.get(), time.time()
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM records WHERE id=? AND kind='annotation' AND "
                          "COALESCE(json_extract(body,'$.workspace_id'),'default')=?",
                          (annotation_id, actor.workspace)).fetchone() is None:
                raise ReviewLeaseConflict('Annotation unavailable in this workspace')
            if db.execute('SELECT 1 FROM decisions WHERE plan_id=?', (annotation_id,)).fetchone():
                raise ReviewLeaseConflict('Annotation has already been reviewed')
            lease = db.execute('SELECT user_id, expires_at FROM review_leases WHERE annotation_id=?',
                               (annotation_id,)).fetchone()
            if lease and lease[1] > now and lease[0] != actor.user_id:
                raise ReviewLeaseConflict('Annotation is held by another reviewer')
            expires = now + 300
            db.execute('INSERT INTO review_leases VALUES (?, ?, ?, ?) ON CONFLICT(annotation_id) '
                       'DO UPDATE SET user_id=excluded.user_id, expires_at=excluded.expires_at',
                       (annotation_id, actor.workspace, actor.user_id, expires))
        return {'user_id': actor.user_id, 'expires_at': datetime.fromtimestamp(expires, timezone.utc).isoformat()}

    def release_review(self, annotation_id: str):
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM review_leases WHERE annotation_id=? AND workspace=? AND user_id=?',
                       (annotation_id, principal.get().workspace, principal.get().user_id))

    def decision(self, plan_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT d.body FROM decisions d JOIN records r ON d.plan_id = r.id WHERE d.plan_id = ? "
                             "AND COALESCE(json_extract(r.body, '$.workspace_id'), 'default') = ?",
                             (plan_id, principal.get().workspace)).fetchone()
        return json.loads(row[0]) if row else None

    def consume_rate(self, bucket: str, limit: int) -> bool:
        window = int(time.time()) // 60
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM rate_limits WHERE window < ?', (window - 1,))
            db.execute('INSERT INTO rate_limits VALUES (?, ?, 1) ON CONFLICT(bucket) DO UPDATE SET '
                       'count = CASE WHEN window = excluded.window THEN count + 1 ELSE 1 END, window = excluded.window',
                       (bucket, window))
            return db.execute('SELECT count FROM rate_limits WHERE bucket = ?', (bucket,)).fetchone()[0] <= limit

    def claim_operation(self, scope: str, key: str):
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status, body FROM operations WHERE workspace=? AND scope=? AND key=?',
                             (principal.get().workspace, scope, key)).fetchone()
            if row:
                return row[0], json.loads(row[1]) if row[1] else None
            db.execute('INSERT INTO operations VALUES (?, ?, ?, ?, NULL)',
                       (principal.get().workspace, scope, key, 'pending'))
        return 'claimed', None

    def finish_operation(self, scope: str, key: str, result: dict | None):
        with closing(self.connect()) as db, db:
            db.execute('UPDATE operations SET status=?, body=? WHERE workspace=? AND scope=? AND key=?',
                       ('complete' if result is not None else 'failed', json.dumps(result) if result is not None else None,
                        principal.get().workspace, scope, key))
