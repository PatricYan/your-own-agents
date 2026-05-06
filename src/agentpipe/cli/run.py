"""CLI 'run' command — run a pipeline. Everything is in the YAML file."""

from __future__ import annotations

import asyncio
import json
import signal
import time
from pathlib import Path
from typing import Any

from agentpipe.cli.main import ErrorCode, error_output
from agentpipe.core.task import Permissions
from agentpipe.execution.state import TaskStatus


class InteractiveController:
    """Ctrl+C to pause, modify, resume."""

    def __init__(self) -> None:
        self._paused = False

    def request_pause(self) -> None:
        self._paused = True

    def on_before_iteration(self, iteration: int, task: Any) -> Any:
        if not self._paused:
            return None

        perms = task.permissions
        perm_summary = ", ".join(
            f"{k}={perms.get_level(k).value}" for k in ["read", "edit", "bash", "glob", "webfetch"]
        )
        print(f"\n--- PAUSED [{task.name}] iteration {iteration} ---")
        print(f"  Goal: {task.goal[:80]}")
        print(f"  Perms: {perm_summary}")
        print("  r=resume  p <key> <allow|deny>  g <goal>  q=quit")

        updates: dict[str, Any] = {}
        while True:
            try:
                cmd = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not cmd or cmd in ("r", "resume"):
                break
            if cmd in ("q", "quit"):
                raise KeyboardInterrupt
            if cmd.startswith("p "):
                parts = cmd.split(maxsplit=2)
                if len(parts) == 3:
                    perm_dict = task.permissions.to_dict()
                    perm_dict[parts[1]] = parts[2]
                    updates["permissions"] = Permissions(perm_dict)
                    print(f"  {parts[1]} = {parts[2]}")
            elif cmd.startswith("g "):
                updates["goal"] = cmd[2:].strip()
                print("  Goal updated")

        self._paused = False
        return task.model_copy(update=updates) if updates else None


def cmd_run(args, workspace: Path, fmt: str) -> int:
    """Run a pipeline. Everything is in the YAML file."""
    from agentpipe.core.agent import Agent
    from agentpipe.loader.yaml_loader import load_config_from_yaml

    pipeline_path = Path(args.pipeline)
    if not pipeline_path.exists():
        error_output(ErrorCode.PIPELINE_INVALID, f"File not found: {pipeline_path}", fmt=fmt)
        return 1

    try:
        config = load_config_from_yaml(pipeline_path)
    except (FileNotFoundError, ValueError) as e:
        error_output(ErrorCode.PIPELINE_INVALID, str(e), fmt=fmt)
        return 1

    if not config.models:
        error_output(
            ErrorCode.MODEL_NOT_FOUND,
            "No models found. Add 'models' to the pipeline YAML, or set AGENTPIPE_MODELS in .env",
            fmt=fmt,
        )
        return 2

    pipeline = config.pipeline
    agent = Agent(name=pipeline.name, pipeline=pipeline, model_configs=config.models)

    watch = getattr(args, "watch", False)
    interactive = getattr(args, "interactive", False)
    start_time = time.time()

    # Show pipeline DAG before running
    if watch or interactive:
        print(f"Pipeline: {pipeline.name}")
        levels = pipeline.topological_sort()
        for i, level in enumerate(levels):
            task_descs = []
            for name in level:
                task = pipeline.get_task(name)
                task_descs.append(f"[{name}] ({task.primary_model})")
            if len(level) > 1:
                parallel = " | ".join(task_descs)
                print(f"  {i}: {parallel}  ← parallel")
            else:
                print(f"  {i}: {task_descs[0]}")
            # Show edges
            if i < len(levels) - 1:
                next_level = levels[i + 1]
                for next_name in next_level:
                    next_task = pipeline.get_task(next_name)
                    if next_task.depends_on:
                        for dep in next_task.depends_on:
                            if dep in level:
                                print(f"     ↓ {dep} → {next_name}")
        print()

    task_outputs: dict[str, dict] = {}

    def _ts() -> str:
        elapsed = time.time() - start_time
        return f"{time.strftime('%H:%M:%S')} +{elapsed:5.1f}s"

    def on_status(task_name: str, status: TaskStatus, details: dict) -> None:
        if not (watch or interactive):
            return
        ts = _ts()
        if status == TaskStatus.RUNNING:
            model = details.get("model", "")
            print(f"\n{ts} ▶ [{task_name}] model={model}")
            task = pipeline.get_task(task_name)
            if task.depends_on:
                for dep in task.depends_on:
                    if dep in task_outputs:
                        out_short = str(task_outputs[dep])[:150]
                        print(f"           input from [{dep}]: {out_short}")
        elif status == TaskStatus.COMPLETED:
            dur = details.get("duration_ms", 0) / 1000
            print(f"\n{ts} ✓ [{task_name}] completed ({dur:.1f}s)")
            output = details.get("output", {})
            if output:
                task_outputs[task_name] = output
                for k, v in output.items():
                    v_str = str(v)[:150]
                    print(f"           {k}: {v_str}")
        elif status == TaskStatus.FAILED:
            print(f"\n{ts} ✗ [{task_name}] failed: {details.get('error', '')}")
        elif status == TaskStatus.SKIPPED:
            print(f"\n{ts} ⊘ [{task_name}] skipped ({details.get('reason', '')})")

    def on_content(text: str) -> None:
        if watch or interactive:
            print(text, end="", flush=True)

    def on_tool_call(name: str, args: dict) -> None:
        if not (watch or interactive):
            return
        args_short = str(args)[:150]
        print(f"\n  {_ts()} → {name}({args_short})", flush=True)

    def on_permission_ask(tool_name: str, input_value: str) -> bool:
        if interactive:
            input_short = input_value[:80]
            print(f"\n  ⚠ {_ts()} Permission required: {tool_name}({input_short})")
            try:
                return input("  Allow? (y/n): ").strip().lower() in ("y", "yes")
            except (EOFError, KeyboardInterrupt):
                return False
        return False

    def on_iteration(iteration: int, phase: str, details: list) -> None:
        if not (watch or interactive):
            return
        if phase == "re-prompting":
            print(f"\n  [{_ts()}] iter {iteration}: re-prompting...", flush=True)
        elif phase == "acting":
            tool_names = [d.get("name", "") for d in details] if details else []
            print(f"\n  [{_ts()}] iter {iteration}: {', '.join(tool_names)}", flush=True)

    controller = None
    on_before = None
    if interactive:
        controller = InteractiveController()
        on_before = controller.on_before_iteration
        original = signal.getsignal(signal.SIGINT)

        def _pause(signum, frame):
            controller.request_pause()
            print("\n[Ctrl+C] Pausing...")
            signal.signal(signal.SIGINT, original or signal.default_int_handler)

        signal.signal(signal.SIGINT, _pause)
        print("Interactive mode: Ctrl+C to pause\n")

    try:
        result = asyncio.run(
            agent.execute(
                {},
                on_status_change=on_status,
                on_before_iteration=on_before,
                on_content=on_content,
                on_tool_call=on_tool_call,
                on_iteration=on_iteration,
                on_permission_ask=on_permission_ask if interactive else None,
            )
        )
    except KeyboardInterrupt:
        print("\nAborted.")
        return 1
    except Exception as e:
        error_output(ErrorCode.RECOVERY_EXHAUSTED, str(e), fmt=fmt)
        return 1

    elapsed = time.time() - start_time
    if fmt == "json":
        print(
            json.dumps(
                {"status": "completed", "result": result, "duration_ms": int(elapsed * 1000)},
                indent=2,
                default=str,
            )
        )
    else:
        from agentpipe import config

        print(f"\n{_ts()} Pipeline completed in {elapsed:.1f}s")
        if isinstance(result, dict):
            for k, v in result.items():
                print(f"  {k}: {v}")
        if config.LOGS_DIR:
            print(f"\nLogs: {config.LOGS_DIR}/")

    return 0
