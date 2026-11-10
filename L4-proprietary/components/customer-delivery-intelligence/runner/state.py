"""运行状态字典 + SQLite 检查点持久化（原子写入、断点恢复）。"""
from __future__ import annotations
import json, sqlite3, time, os
from datetime import datetime, timezone
from typing import Any, Optional

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS cdi_checkpoints (
  task_id      TEXT PRIMARY KEY,
  state_json   TEXT NOT NULL,
  current_state TEXT NOT NULL,
  updated_at   REAL NOT NULL,
  schema_version INTEGER NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


class CheckpointStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        d = os.path.dirname(os.path.expanduser(db_path))
        if d:
            os.makedirs(d, exist_ok=True)
        self._conn = sqlite3.connect(os.path.expanduser(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(DDL)
        self._conn.commit()

    def save(self, state: dict[str, Any]) -> None:
        """原子 upsert 全量 state。"""
        state["updatedAt"] = now_iso()
        payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        self._conn.execute(
            """INSERT INTO cdi_checkpoints(task_id, state_json, current_state, updated_at, schema_version)
               VALUES(?,?,?,?,?)
               ON CONFLICT(task_id) DO UPDATE SET
                 state_json=excluded.state_json,
                 current_state=excluded.current_state,
                 updated_at=excluded.updated_at,
                 schema_version=excluded.schema_version""",
            (state["task_id"], payload, state["current_state"], time.time(), SCHEMA_VERSION),
        )
        self._conn.commit()

    def load(self, task_id: str) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            "SELECT state_json FROM cdi_checkpoints WHERE task_id=?", (task_id,)
        ).fetchone()
        return json.loads(row["state_json"]) if row else None

    def list_states(self, task_id: str):
        row = self._conn.execute(
            "SELECT current_state, updated_at FROM cdi_checkpoints WHERE task_id=?", (task_id,)
        ).fetchone()
        return dict(row) if row else None

    def all_tasks(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT task_id, current_state, updated_at FROM cdi_checkpoints ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, task_id: str) -> None:
        self._conn.execute("DELETE FROM cdi_checkpoints WHERE task_id=?", (task_id,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def new_state(task_id: str, input_norm: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "current_state": "N1_guard",
        "schema_version": SCHEMA_VERSION,
        "input_norm": input_norm,
        "raw": {"ones": {}, "oa": {}, "fetchedAt": None},
        "file_manifest": [],
        "completeness": {},
        "contracts": [],
        "artifacts": {},
        "hitl_decisions": {"gate1": None, "gate2": None},
        "audit": {"status": "in_progress", "checks": [], "missing_sources": [], "warnings": []},
        "errors": [],
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
