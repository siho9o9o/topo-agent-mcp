# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite storage for immutable experiments and benchmark runs."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, author TEXT NOT NULL,
                    title TEXT NOT NULL, summary TEXT NOT NULL, commit_sha TEXT NOT NULL,
                    tags TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, author TEXT NOT NULL,
                    method TEXT NOT NULL, commit_sha TEXT NOT NULL, notes TEXT NOT NULL,
                    dataset_version TEXT NOT NULL, metrics TEXT NOT NULL, rows TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS runs_dataset_idx ON runs(dataset_version);
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def add_experiment(self, author, title, summary, commit_sha, tags):
        entry = {"id": uuid.uuid4().hex, "created_at": _now(), "author": author,
                 "title": title, "summary": summary, "commit_sha": commit_sha, "tags": tags}
        with self._connect() as db:
            db.execute("INSERT INTO experiments VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (entry["id"], entry["created_at"], author, title, summary,
                        commit_sha, json.dumps(tags)))
        return entry

    def experiments(self, query="", limit=30):
        with self._connect() as db:
            sql = """SELECT * FROM experiments
                WHERE title LIKE ? OR summary LIKE ? OR tags LIKE ?
                ORDER BY created_at DESC, rowid DESC"""
            params = [f"%{query}%"] * 3
            if limit is not None:
                sql += " LIMIT ?"
                params.append(limit)
            rows = db.execute(sql, params).fetchall()
        return [{**dict(row), "tags": json.loads(row["tags"])} for row in rows]

    def add_run(self, author, method, commit_sha, notes, version, metrics, rows):
        entry = {"id": uuid.uuid4().hex, "created_at": _now(), "author": author,
                 "method": method, "commit_sha": commit_sha, "notes": notes,
                 "dataset_version": version, "metrics": metrics, "rows": rows}
        with self._connect() as db:
            db.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (entry["id"], entry["created_at"], author, method, commit_sha,
                        notes, version, json.dumps(metrics), json.dumps(rows)))
        return entry

    def runs(self, version):
        with self._connect() as db:
            rows = db.execute("""SELECT * FROM runs WHERE dataset_version = ?
                ORDER BY created_at DESC""", (version,)).fetchall()
        return [{**dict(row), "metrics": json.loads(row["metrics"]),
                 "rows": json.loads(row["rows"])} for row in rows]

    def run(self, run_id):
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return ({**dict(row), "metrics": json.loads(row["metrics"]),
                 "rows": json.loads(row["rows"])} if row else None)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
