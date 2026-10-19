import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError(f'Unsupported database version: {version}; explicit migration required')
            db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS decisions (plan_id TEXT PRIMARY KEY REFERENCES records(id), body TEXT NOT NULL)')
            db.execute('PRAGMA user_version = 1')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA foreign_keys = ON')
        return db

    def save(self, kind: str, body: dict) -> dict:
        record = {**body, 'id': str(uuid4()), 'created_at': datetime.now(timezone.utc).isoformat()}
        with closing(self.connect()) as db, db:
            db.execute('INSERT INTO records VALUES (?, ?, ?)',
                       (record['id'], kind, json.dumps(record, ensure_ascii=False)))
        return record

    def get(self, kind: str, identifier: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute('SELECT body FROM records WHERE id = ? AND kind = ?', (identifier, kind)).fetchone()
        return json.loads(row[0]) if row else None

    def list_records(self, kind: str, dataset_id: str) -> list[dict]:
        # ponytail: JSON scan is sufficient for one block; add indexed columns when datasets grow.
        with closing(self.connect()) as db:
            rows = db.execute(
                "SELECT body FROM records WHERE kind = ? AND json_extract(body, '$.dataset_id') = ? ORDER BY rowid",
                (kind, dataset_id),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def reviewed_records(self, dataset_id: str) -> list[tuple[dict, dict]]:
        with closing(self.connect()) as db:
            rows = db.execute(
                "SELECT r.body, d.body FROM records r JOIN decisions d ON d.plan_id = r.id "
                "WHERE r.kind = 'annotation' AND json_extract(r.body, '$.dataset_id') = ? ORDER BY r.rowid",
                (dataset_id,),
            ).fetchall()
        return [(json.loads(record), json.loads(decision)) for record, decision in rows]

    def save_many(self, kind: str, bodies: list[dict]) -> list[dict]:
        records = [{**body, 'id': str(uuid4()), 'created_at': datetime.now(timezone.utc).isoformat()}
                   for body in bodies]
        with closing(self.connect()) as db, db:
            db.executemany('INSERT INTO records VALUES (?, ?, ?)',
                           [(r['id'], kind, json.dumps(r, ensure_ascii=False)) for r in records])
        return records

    def decide(self, plan_id: str, body: dict) -> dict:
        record = {**body, 'plan_id': plan_id, 'created_at': datetime.now(timezone.utc).isoformat()}
        with closing(self.connect()) as db, db:
            db.execute('INSERT INTO decisions VALUES (?, ?)', (plan_id, json.dumps(record, ensure_ascii=False)))
        return record

    def decision(self, plan_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute('SELECT body FROM decisions WHERE plan_id = ?', (plan_id,)).fetchone()
        return json.loads(row[0]) if row else None
