"""SQLite execution history storage for pipeline runs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class HistoryStore:
    """SQLite-backed storage for execution run history."""

    def __init__(self, workspace: Path) -> None:
        db_dir = workspace / ".agentpipe"
        db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = db_dir / "history.db"
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_runs (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT,
                    pipeline_name TEXT,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    trigger_type TEXT,
                    error TEXT,
                    pipeline_snapshot TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_executions (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    model_used TEXT,
                    input_data TEXT,
                    output_data TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    duration_ms INTEGER,
                    retry_count INTEGER DEFAULT 0,
                    recovery_log TEXT,
                    error TEXT,
                    FOREIGN KEY (run_id) REFERENCES execution_runs(id)
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    def save_run(self, run_data: dict[str, Any]) -> None:
        """Save or update an execution run record."""
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO execution_runs
                   (id, agent_id, pipeline_name, status, started_at, completed_at,
                    trigger_type, error, pipeline_snapshot)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_data["id"],
                    run_data.get("agent_id", ""),
                    run_data.get("pipeline_name", ""),
                    run_data["status"],
                    run_data.get("started_at"),
                    run_data.get("completed_at"),
                    run_data.get("trigger", "cli"),
                    run_data.get("error"),
                    json.dumps(run_data.get("pipeline_snapshot", {})),
                ),
            )

    def save_task_execution(self, task_data: dict[str, Any]) -> None:
        """Save or update a task execution record."""
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO task_executions
                   (id, run_id, task_name, status, model_used, input_data, output_data,
                    started_at, completed_at, duration_ms, retry_count, recovery_log, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_data["id"],
                    task_data["run_id"],
                    task_data["task_name"],
                    task_data["status"],
                    task_data.get("model_used"),
                    json.dumps(task_data.get("input_data", {})),
                    json.dumps(task_data.get("output_data", {})),
                    task_data.get("started_at"),
                    task_data.get("completed_at"),
                    task_data.get("duration_ms"),
                    task_data.get("retry_count", 0),
                    json.dumps(task_data.get("recovery_log", [])),
                    task_data.get("error"),
                ),
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Get a specific execution run with its task executions."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM execution_runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                return None

            run = dict(row)
            tasks = conn.execute(
                "SELECT * FROM task_executions WHERE run_id = ? ORDER BY started_at",
                (run_id,),
            ).fetchall()
            run["task_executions"] = [dict(t) for t in tasks]
            return run

    def list_runs(
        self,
        agent_name: str | None = None,
        limit: int = 20,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List recent execution runs."""
        query = "SELECT * FROM execution_runs WHERE 1=1"
        params: list[Any] = []

        if agent_name:
            query += " AND pipeline_name LIKE ?"
            params.append(f"%{agent_name}%")
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
