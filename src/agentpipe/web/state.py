"""Shared server state: tracks running pipelines and broadcasts events."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LiveTask:
    """Live state of a single task during execution."""

    name: str
    status: str = "pending"  # pending, running, completed, failed, skipped
    model: str | None = None
    iteration: int = 0
    tool_calls: int = 0
    started_at: float | None = None
    completed_at: float | None = None
    duration_ms: int | None = None
    error: str | None = None
    output: dict[str, Any] = field(default_factory=dict)

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
        }


@dataclass
class LiveRun:
    """Live state of a pipeline execution."""

    run_id: str
    pipeline_name: str
    status: str = "pending"
    tasks: dict[str, LiveTask] = field(default_factory=dict)
    started_at: float | None = None
    completed_at: float | None = None
    result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "pipeline_name": self.pipeline_name,
            "status": self.status,
            "tasks": {n: t.to_dict() for n, t in self.tasks.items()},
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class ServerState:
    """Shared state across the web server: runs, pipelines, event broadcast."""

    def __init__(self) -> None:
        self.runs: dict[str, LiveRun] = {}
        self._ws_clients: set[asyncio.Queue] = set()
        self._pending_updates: dict[str, dict[str, Any]] = {}  # run_id -> task updates
        self._pause_events: dict[str, asyncio.Event] = {}

    # -- WebSocket broadcast --

    def add_ws_client(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._ws_clients.add(q)
        return q

    def remove_ws_client(self, q: asyncio.Queue) -> None:
        self._ws_clients.discard(q)

    async def broadcast(self, event: dict[str, Any]) -> None:
        msg = json.dumps(event, default=str)
        dead = []
        for q in self._ws_clients:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._ws_clients.discard(q)

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

    # -- Live control --

    def pause_run(self, run_id: str) -> None:
        if run_id in self._pause_events:
            self._pause_events[run_id].clear()
            if run_id in self.runs:
                self.runs[run_id].status = "paused"

    def resume_run(self, run_id: str) -> None:
        if run_id in self._pause_events:
            self._pause_events[run_id].set()
            if run_id in self.runs:
                self.runs[run_id].status = "running"

    def is_paused(self, run_id: str) -> bool:
        ev = self._pause_events.get(run_id)
        return ev is not None and not ev.is_set()

    async def wait_if_paused(self, run_id: str) -> None:
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
