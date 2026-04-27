"""Streaming log writer — saves FULL conversation context for debugging.

No truncation. Every message, tool call, tool result, and model response
is saved in full so the user can replay the exact conversation.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TaskLogWriter:
    """Writes full conversation logs as JSONL — no truncation.

    Every line: {"ts": "HH:MM:SS", "elapsed": "Ns", "event": "...", ...}
    """

    def __init__(self, task_name: str) -> None:
        from agentpipe import config

        self._task_name = task_name
        self._file = None
        self._path = None
        self._start = time.time()

        if config.LOGS_DIR:
            log_dir = Path(config.LOGS_DIR)
            log_dir.mkdir(parents=True, exist_ok=True)
            self._path = log_dir / f"{task_name}.jsonl"
            self._file = open(self._path, "w")  # noqa: SIM115
            self._write("start", {"task": task_name})

    def log_system_prompt(self, prompt: str) -> None:
        self._write("system", {"content": prompt})

    def log_user_message(self, content: str) -> None:
        self._write("user", {"content": content})

    def log_model_response(
        self, content: str | None, tool_calls: list[dict], stop_reason: str
    ) -> None:
        self._write(
            "assistant",
            {
                "content": content,
                "tool_calls": tool_calls,
                "stop_reason": stop_reason,
            },
        )

    def log_tool_call(self, name: str, args: dict, result: str) -> None:
        self._write(
            "tool",
            {
                "name": name,
                "args": args,
                "result": result,
                "ok": not result.startswith("Error:"),
            },
        )

    def log_tool_result(self, tool_call_id: str, result: str) -> None:
        self._write(
            "tool_result",
            {
                "id": tool_call_id,
                "result": result,
            },
        )

    def log_iteration(
        self,
        iteration: int,
        model_content: str | None,
        tool_calls: list[dict],
        tool_results: list[dict],
    ) -> None:
        self._write(
            "iter",
            {
                "n": iteration,
                "tools": [tc.get("name", "") for tc in tool_calls],
            },
        )

    def log_complete(self, result: Any) -> None:
        elapsed = time.time() - self._start
        self._write(
            "done",
            {
                "ok": result.completed,
                "iterations": result.iterations,
                "tool_calls": result.total_tool_calls,
                "tokens": result.total_tokens,
                "elapsed": f"{elapsed:.1f}s",
                "output": result.output,
                "error": result.error,
            },
        )
        # Save full conversation as the last entry
        self._write(
            "conversation",
            {
                "messages": result.conversation.to_list(),
            },
        )
        self.close()

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
            if self._path:
                logger.info("Log: %s", self._path)

    def _write(self, event: str, data: dict) -> None:
        if not self._file:
            return
        elapsed = time.time() - self._start
        line = {
            "ts": time.strftime("%H:%M:%S"),
            "elapsed": f"{elapsed:.1f}s",
            "event": event,
            **data,
        }
        self._file.write(json.dumps(line, default=str) + "\n")
        self._file.flush()
