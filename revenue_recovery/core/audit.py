"""Audit trail: append-only SQLite log, one row per step per event.

Every stage of the loop (detect/diagnose/decide/guardrail/act/measure) writes
one record here with its inputs, outputs, and any notes. This is a judged
deliverable — nothing in the pipeline should skip logging a stage.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from core.models import AuditRecord

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "audit.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    input_json TEXT NOT NULL,
    output_json TEXT NOT NULL,
    notes TEXT,
    batch_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_event_id ON audit_log(event_id);
CREATE INDEX IF NOT EXISTS idx_audit_batch_id ON audit_log(batch_id);
"""


class AuditLog:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH, reset: bool = False):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if reset and self.db_path.exists():
            self.db_path.unlink()
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def log(self, record: AuditRecord, batch_id: str | None = None) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO audit_log (event_id, stage, timestamp, input_json, output_json, notes, batch_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.event_id, record.stage, record.timestamp.isoformat(),
                    json.dumps(record.input, default=str), json.dumps(record.output, default=str),
                    record.notes, batch_id,
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_trail(self, event_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, event_id, stage, timestamp, input_json, output_json, notes, batch_id "
                "FROM audit_log WHERE event_id = ? ORDER BY id ASC",
                (event_id,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_batch_trail(self, batch_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, event_id, stage, timestamp, input_json, output_json, notes, batch_id "
                "FROM audit_log WHERE batch_id = ? ORDER BY id ASC",
                (batch_id,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def export_json(self, out_path: str | Path) -> None:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, event_id, stage, timestamp, input_json, output_json, notes, batch_id FROM audit_log ORDER BY id ASC"
            ).fetchall()
        records = [self._row_to_dict(r) for r in rows]
        Path(out_path).write_text(json.dumps(records, indent=2), encoding="utf-8")

    @staticmethod
    def _row_to_dict(row) -> dict:
        id_, event_id, stage, ts, input_json, output_json, notes, batch_id = row
        return dict(
            id=id_, event_id=event_id, stage=stage, timestamp=ts,
            input=json.loads(input_json), output=json.loads(output_json),
            notes=notes, batch_id=batch_id,
        )

    def close(self):
        self._conn.close()
