"""CLI 'run' command handler: execute an agent's pipeline."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import yaml

from agentpipe.cli.main import ErrorCode, error_output
from agentpipe.execution.state import TaskStatus

# ---------------------------------------------------------------------------
# Interactive controller — lets the user interrupt and modify agents mid-run
# ---------------------------------------------------------------------------


class InteractiveController:
    """Manages user interrupts during agent execution.

    In --interactive mode, the user can press Ctrl+C at any time to pause.
    When paused, they can:
      - View current task state
      - Update permissions (grant/revoke shell, file_write, etc.)
      - Update the goal or system prompt
      - Resume autonomous execution

    The controller implements the on_before_iteration hook protocol.
    """

    def __init__(self) -> None:
        self._paused = False
        self._pending_update: dict[str, Any] | None = None
        self._current_task_name: str = ""
        self._current_iteration: int = 0

    def request_pause(self) -> None:
        """Called from signal handler to request a pause."""
        self._paused = True

    def on_before_iteration(self, iteration: int, task) -> Any:
        """Hook called before each agent iteration."""
        from agentpipe.core.task import Permissions

        self._current_task_name = task.name
        self._current_iteration = iteration

        if not self._paused:
            return None

        # --- Paused: interactive menu ---
        print(f"\n--- PAUSED at [{task.name}] iteration {iteration} ---")
        print(f"  Goal: {task.goal}")
        print(f"  Model: {task.primary_model}")
        perms = task.permissions
        perm_summary = ", ".join(
            f"{k}={perms.get_level(k).value}" for k in ["read", "edit", "bash", "glob", "webfetch"]
        )
        print(f"  Permissions: {perm_summary}")
        print()
        print("Commands:")
        print("  r / resume          - Continue autonomous execution")
        print("  p <key> <allow|deny> - Set permission (e.g. 'p bash allow')")
        print("  g <new goal>        - Update the goal")
        print("  s <new prompt>      - Update the system prompt")
        print("  q / quit            - Abort the pipeline")
        print()

        updates: dict[str, Any] = {}
        while True:
            try:
                cmd = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nResuming...")
                break

            if not cmd:
                continue

            if cmd in ("r", "resume"):
                break

            if cmd in ("q", "quit"):
                print("Aborting...")
                raise KeyboardInterrupt

            if cmd.startswith("p "):
                parts = cmd.split(maxsplit=2)
                if len(parts) == 3:
                    perm_name, value = parts[1], parts[2].lower()
                    valid_perms = {"read", "edit", "bash", "glob", "grep", "list", "webfetch"}
                    valid_levels = {"allow", "ask", "deny"}
                    if perm_name in valid_perms and value in valid_levels:
                        perm_dict = task.permissions.to_dict()
                        perm_dict[perm_name] = value
                        updates["permissions"] = Permissions(perm_dict)
                        print(f"  {perm_name} = {value}")
                    else:
                        print(
                            f"  Invalid. Use: p <{'|'.join(sorted(valid_perms))}> <allow|ask|deny>"
                        )
                else:
                    print("  Usage: p <permission> <allow|ask|deny>")

            elif cmd.startswith("g "):
                new_goal = cmd[2:].strip()
                if new_goal:
                    updates["goal"] = new_goal
                    print(f"  Goal updated: {new_goal}")

            elif cmd.startswith("s "):
                new_prompt = cmd[2:].strip()
                if new_prompt:
                    updates["system_prompt"] = new_prompt
                    print("  System prompt updated")

            else:
                print(f"  Unknown command: {cmd}")

        self._paused = False

        if updates:
            return task.model_copy(update=updates)
        return None


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


def cmd_run(args, workspace: Path, fmt: str) -> int:
    """Execute the 'run' command.

    The pipeline argument can be:
    1. A YAML file path — loads pipeline + models from the file
    2. A registered agent name — loads from the workspace store (legacy)
    """
    from agentpipe.core.agent import Agent
    from agentpipe.models.registry import ModelConfig, load_models_from_file

    pipeline_arg = args.pipeline
    pipeline_path = Path(pipeline_arg)

    # Parse input
    input_data = _parse_input(args, fmt)
    if input_data is None:
        return 3

    # Load pipeline and models
    if pipeline_path.exists() and pipeline_path.suffix in (".yaml", ".yml", ".json"):
        # Load from YAML file — self-contained, no registration needed
        from agentpipe.loader.yaml_loader import load_config_from_yaml

        try:
            config = load_config_from_yaml(pipeline_path)
        except (FileNotFoundError, ValueError) as e:
            error_output(ErrorCode.PIPELINE_INVALID, str(e), fmt=fmt)
            return 1

        pipeline = config.pipeline
        model_configs = config.models

        # Also load from --models flag if provided
        if getattr(args, "models_file", None):
            try:
                model_configs = load_models_from_file(args.models_file)
            except (FileNotFoundError, ValueError) as e:
                error_output(ErrorCode.MODEL_NOT_FOUND, str(e), fmt=fmt)
                return 2

        if not model_configs:
            error_output(
                ErrorCode.MODEL_NOT_FOUND,
                "No models configured. Add a 'models' section to the pipeline YAML "
                "or use --models <file>",
                fmt=fmt,
            )
            return 2

        agent = Agent(name=pipeline.name, pipeline=pipeline, model_configs=model_configs)

    else:
        # Legacy: load from registered agent in workspace store
        from agentpipe.loader.yaml_loader import load_pipeline_from_dict
        from agentpipe.storage.definitions import DefinitionStore

        store = DefinitionStore(workspace)
        try:
            agent_data = store.load_agent(pipeline_arg)
        except FileNotFoundError:
            error_output(
                ErrorCode.AGENT_NOT_FOUND,
                f"'{pipeline_arg}' is not a YAML file and not a registered agent",
                fmt=fmt,
            )
            return 2

        model_configs = []
        for mc_name in agent_data.get("model_configs", []):
            try:
                mc_data = store.load_model(mc_name)
                model_configs.append(ModelConfig(**mc_data))
            except FileNotFoundError:
                error_output(ErrorCode.MODEL_NOT_FOUND, f"Model '{mc_name}' not found", fmt=fmt)
                return 2

        loaded_pipeline = load_pipeline_from_dict(agent_data.get("pipeline", {}))
        agent = Agent(name=pipeline_arg, pipeline=loaded_pipeline, model_configs=model_configs)

    # Status callback for --watch mode
    watch = getattr(args, "watch", False)
    interactive = getattr(args, "interactive", False)
    start_time = time.time()

    def on_status_change(task_name: str, status: TaskStatus, details: dict) -> None:
        if watch or interactive:
            if status == TaskStatus.RUNNING:
                model = details.get("model", "")
                print(f"[{task_name}] Running... (model: {model})")
            elif status == TaskStatus.COMPLETED:
                duration = details.get("duration_ms", 0) / 1000
                recovered = " (recovered)" if details.get("recovered") else ""
                print(f"[{task_name}] Completed ({duration:.1f}s){recovered}")
            elif status == TaskStatus.FAILED:
                err = details.get("error", "unknown error")
                print(f"[{task_name}] Failed: {err}")

    # Interactive mode: set up controller and Ctrl+C handler
    controller = None
    on_before_iteration = None

    if interactive:
        controller = InteractiveController()
        on_before_iteration = controller.on_before_iteration

        original_handler = None

        import signal

        def _sigint_handler(signum, frame):
            if controller:
                controller.request_pause()
                print("\n[Ctrl+C] Pausing after current iteration... (press again to force quit)")
                # Restore default handler so a second Ctrl+C force-quits
                signal.signal(signal.SIGINT, original_handler or signal.default_int_handler)

        original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, _sigint_handler)

        print("Interactive mode: press Ctrl+C at any time to pause and modify the running agent.")
        print()

    # Execute (Agent.execute uses provider_factory by default — each task gets its own provider)
    try:
        result = asyncio.run(
            agent.execute(
                input_data,
                on_status_change=on_status_change,
                on_before_iteration=on_before_iteration,
            )
        )
    except KeyboardInterrupt:
        print("\nAborted by user.")
        return 1
    except Exception as e:
        error_output(ErrorCode.RECOVERY_EXHAUSTED, str(e), fmt=fmt)
        return 1

    # Output result
    if fmt == "json":
        output = {
            "status": "completed",
            "result": result,
            "duration_ms": int((time.time() - start_time) * 1000),
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        elapsed = time.time() - start_time
        print(f"\nExecution completed in {elapsed:.1f}s")
        print("\nResult:")
        if isinstance(result, dict):
            for k, v in result.items():
                print(f"  {k}: {v}")
        else:
            print(f"  {result}")

    return 0


def _parse_input(args, fmt: str) -> dict[str, Any] | None:
    """Parse input data from --input or --input-file."""
    if hasattr(args, "input_data") and args.input_data:
        try:
            data = json.loads(args.input_data)
            if not isinstance(data, dict):
                data = {"input": data}
            return data
        except json.JSONDecodeError as e:
            error_output(ErrorCode.INPUT_INVALID, f"Invalid JSON input: {e}", fmt=fmt)
            return None

    if hasattr(args, "input_file") and args.input_file:
        path = Path(args.input_file)
        if not path.exists():
            error_output(ErrorCode.INPUT_INVALID, f"Input file not found: {path}", fmt=fmt)
            return None
        content = path.read_text()
        try:
            if path.suffix in (".yaml", ".yml"):
                data = yaml.safe_load(content)
            else:
                data = json.loads(content)
            if not isinstance(data, dict):
                data = {"input": data}
            return data
        except Exception as e:
            error_output(ErrorCode.INPUT_INVALID, f"Cannot parse input file: {e}", fmt=fmt)
            return None

    return {"input": ""}
