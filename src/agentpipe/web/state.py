"""Shared server state: tracks running pipelines with revision-based change detection.

No WebSocket — clients use HTTP polling with ETag/cursor for efficiency.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LiveTask:
    """Live state of a single task during execution."""

    name: str
    status: str = "pending"
    model: str | None = None
    iteration: int = 0
    tool_calls: int = 0
    started_at: float | None = None
    completed_at: float | None = None
    duration_ms: int | None = None
    error: str | None = None
    output: dict[str, Any] = field(default_factory=dict)
    logs: list[dict[str, Any]] = field(default_factory=list)  # conversation + tool logs

    @property
    def log_count(self) -> int:
        """Current log entry count — used as cursor for pagination."""
        return len(self.logs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "model": self.model,
            "iteration": self.iteration,
            "tool_calls": self.tool_calls,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "output": self.output,
        }


@dataclass
class LiveRun:
    """Live state of a pipeline execution with revision tracking for ETags."""

    run_id: str
    pipeline_name: str
    status: str = "pending"
    tasks: dict[str, LiveTask] = field(default_factory=dict)
    started_at: float | None = None
    completed_at: float | None = None
    result: dict[str, Any] = field(default_factory=dict)
    _revision: int = 0

    def bump_revision(self) -> None:
        """Increment revision counter on any state mutation."""
        self._revision += 1

    @property
    def etag(self) -> str:
        """ETag value for HTTP conditional responses."""
        return f'"{self.run_id}-{self._revision}"'

    def to_dict(self) -> dict[str, Any]:
        import time as _time

        return {
            "run_id": self.run_id,
            "pipeline_name": self.pipeline_name,
            "status": self.status,
            "tasks": {n: t.to_dict() for n, t in self.tasks.items()},
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "started_time": _time.strftime("%H:%M:%S", _time.localtime(self.started_at))
            if self.started_at
            else None,
            "task_names": list(self.tasks.keys()),
        }


class ServerState:
    """Shared state across the web server: runs, pause/resume, task updates.

    No WebSocket — uses revision counters for ETag-based conditional polling.
    """

    def __init__(self) -> None:
        self.runs: dict[str, LiveRun] = {}
        self._pending_updates: dict[str, dict[str, Any]] = {}  # "run_id:task_name" -> updates
        self._pause_events: dict[str, asyncio.Event] = {}

    # -- Run lifecycle --

    def create_run(self, pipeline_name: str, task_names: list[str]) -> LiveRun:
        run_id = str(uuid.uuid4())[:8]
        run = LiveRun(
            run_id=run_id,
            pipeline_name=pipeline_name,
            started_at=time.time(),
            tasks={name: LiveTask(name=name) for name in task_names},
        )
        self.runs[run_id] = run
        self._pause_events[run_id] = asyncio.Event()
        self._pause_events[run_id].set()  # not paused
        return run

    # -- ETag support --

    def runs_etag(self) -> str:
        """Aggregate ETag for the runs list endpoint."""
        parts = [f"{r.run_id}:{r._revision}" for r in self.runs.values()]
        digest = hashlib.md5("|".join(parts).encode()).hexdigest()[:12]
        return f'"runs-{digest}"'

    # -- Live control --

    def pause_run(self, run_id: str) -> None:
        if run_id in self._pause_events:
            self._pause_events[run_id].clear()
            run = self.runs.get(run_id)
            if run:
                run.status = "paused"
                run.bump_revision()

    def resume_run(self, run_id: str) -> None:
        if run_id in self._pause_events:
            self._pause_events[run_id].set()
            run = self.runs.get(run_id)
            if run:
                run.status = "running"
                run.bump_revision()

    def is_paused(self, run_id: str) -> bool:
        ev = self._pause_events.get(run_id)
        return ev is not None and not ev.is_set()

    async def wait_if_paused(self, run_id: str) -> None:
        """Block until un-paused. Zero CPU cost — uses asyncio.Event.wait()."""
        ev = self._pause_events.get(run_id)
        if ev:
            await ev.wait()

    def set_task_update(self, run_id: str, task_name: str, updates: dict[str, Any]) -> None:
        """Queue a task update (permissions, goal, etc.) to be applied on next iteration."""
        key = f"{run_id}:{task_name}"
        self._pending_updates[key] = updates

    def pop_task_update(self, run_id: str, task_name: str) -> dict[str, Any] | None:
        key = f"{run_id}:{task_name}"
        return self._pending_updates.pop(key, None)
