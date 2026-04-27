"""REST API server for pipeline visualization and control.

Pipelines are loaded from YAML files in the pipelines directory
(configured via AGENTPIPE_PIPELINES_DIR). No WebSocket — uses HTTP
conditional polling with ETags and cursor-based log pagination.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from agentpipe.web.state import ServerState

logger = logging.getLogger("agentpipe.api")

_state = ServerState()
_workspace: Path = Path(".")
_pipelines_dir: Path = Path("examples")


def _scan_pipelines() -> dict[str, Path]:
    """Scan the pipelines directory for YAML files. Returns name -> path."""
    pipelines = {}
    for f in sorted(_pipelines_dir.glob("*.yaml")):
        if f.stem == "models":
            continue  # skip models.yaml
        pipelines[f.stem] = f
    for f in sorted(_pipelines_dir.glob("*.yml")):
        if f.stem == "models":
            continue
        pipelines[f.stem] = f
    return pipelines


def _load_pipeline_config(path: Path):
    """Load pipeline + models from a YAML file."""
    from agentpipe.loader.yaml_loader import load_config_from_yaml

    return load_config_from_yaml(path)


# ============================================================
# REST API Endpoints
# ============================================================


async def api_list_pipelines(request: Request) -> JSONResponse:
    """GET /api/pipelines — list all pipeline YAML files."""
    pipelines = _scan_pipelines()
    items = []
    for name, path in pipelines.items():
        try:
            config = _load_pipeline_config(path)
            items.append({"name": name, "pipeline": config.pipeline.name, "file": str(path)})
        except Exception as e:
            items.append({"name": name, "pipeline": name, "file": str(path), "error": str(e)})
    return JSONResponse({"pipelines": items})


async def api_get_pipeline(request: Request) -> JSONResponse:
    """GET /api/pipelines/{name} — get pipeline DAG structure."""
    name = request.path_params["name"]
    pipelines = _scan_pipelines()

    if name not in pipelines:
        return JSONResponse({"error": f"Pipeline '{name}' not found"}, status_code=404)

    try:
        config = _load_pipeline_config(pipelines[name])
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    pipeline = config.pipeline

    nodes = []
    for task in pipeline.tasks:
        nodes.append(
            {
                "id": task.name,
                "goal": task.goal,
                "model": task.primary_model,
                "permissions": task.permissions.to_dict(),
                "depends_on": task.depends_on,
                "max_iterations": task.max_iterations,
                "system_prompt": task.system_prompt,
                "model_routing": task.model_routing,
            }
        )

    edges = []
    for edge in pipeline.edges:
        e: dict[str, Any] = {"from": edge.upstream, "to": edge.downstream}
        if edge.condition:
            e["condition"] = edge.condition.expression
        edges.append(e)

    return JSONResponse(
        {
            "name": pipeline.name,
            "strategy": pipeline.execution_strategy.value,
            "nodes": nodes,
            "edges": edges,
            "levels": pipeline.topological_sort(),
            "models": [{"name": m.name, "provider": m.provider} for m in config.models],
        }
    )


async def api_run_pipeline(request: Request) -> JSONResponse:
    """POST /api/pipelines/{name}/run — start a pipeline execution."""
    name = request.path_params["name"]
    body = await request.json()
    input_data = body.get("input", {})

    pipelines = _scan_pipelines()
    if name not in pipelines:
        return JSONResponse({"error": f"Pipeline '{name}' not found"}, status_code=404)

    try:
        config = _load_pipeline_config(pipelines[name])
    except Exception as e:
        return JSONResponse({"error": f"Failed to load pipeline: {e}"}, status_code=400)

    pipeline = config.pipeline
    model_configs = config.models

    if not model_configs:
        return JSONResponse(
            {"error": "No models configured. Add 'models' to the pipeline YAML."},
            status_code=400,
        )

    # Create live run
    task_names = [t.name for t in pipeline.tasks]
    live_run = _state.create_run(pipeline.name, task_names)
    live_run.status = "running"
    live_run.bump_revision()
    logger.info(
        "Pipeline '%s' started (run_id: %s, tasks: %s)",
        name,
        live_run.run_id,
        " → ".join(task_names),
    )

    # Status callback — logs to console, stores in run state (polled by frontend)
    def on_status_sync(task_name, status, details):
        lt = live_run.tasks.get(task_name)
        if lt:
            lt.status = status.value
            if status.value == "running":
                lt.model = details.get("model")
                lt.started_at = time.time()
                logger.info("[%s] Running... (model: %s)", task_name, lt.model)
            elif status.value == "completed":
                lt.completed_at = time.time()
                lt.duration_ms = details.get("duration_ms", 0)
                lt.output = details.get("output", {})
                logger.info("[%s] Completed (%.1fs)", task_name, lt.duration_ms / 1000)
            elif status.value == "failed":
                lt.completed_at = time.time()
                lt.error = details.get("error")
                logger.error("[%s] Failed: %s", task_name, lt.error)
            live_run.bump_revision()

    async def on_before_iteration(iteration, task):
        # Efficient pause — zero CPU cost, instant resume via asyncio.Event.wait()
        await _state.wait_if_paused(live_run.run_id)

        updates = _state.pop_task_update(live_run.run_id, task.name)
        lt = live_run.tasks.get(task.name)
        if lt:
            lt.iteration = iteration
            live_run.bump_revision()
        if updates:
            return task.model_copy(update=updates)
        return None

    # Task-aware callbacks: receive task_name as a keyword arg from the
    # per-task closures created in TaskRunner.run_task(). This eliminates
    # the race condition where a shared _current_task_name dict caused
    # parallel tasks' logs to be attributed to whichever task started last.

    def on_content_sync(text: str, task_name: str = "") -> None:
        """Store streaming model output in task logs."""
        lt = live_run.tasks.get(task_name)
        if lt:
            lt.logs.append({"type": "content", "text": text})
            live_run.bump_revision()

    on_content_sync._task_aware = True  # type: ignore[attr-defined]

    def on_tool_call_sync(name_: str, args: dict, task_name: str = "") -> None:
        """Store tool calls in task logs + log to console."""
        logger.info("  [%s] → %s(%s)", task_name, name_, str(args)[:80])
        lt = live_run.tasks.get(task_name)
        if lt:
            lt.tool_calls += 1
            lt.logs.append({"type": "tool_call", "name": name_, "args": str(args)[:200]})
            live_run.bump_revision()

    on_tool_call_sync._task_aware = True  # type: ignore[attr-defined]

    def on_iteration_sync(iteration: int, phase: str, details: list, task_name: str = "") -> None:
        """Store iteration events in task logs."""
        lt = live_run.tasks.get(task_name)
        if lt:
            lt.iteration = iteration
            lt.logs.append({"type": "iteration", "iteration": iteration, "phase": phase})
            live_run.bump_revision()

    on_iteration_sync._task_aware = True  # type: ignore[attr-defined]

    # Run in background
    async def _execute():
        from agentpipe.core.agent import Agent
        from agentpipe.tools.registry import create_default_registry

        agent = Agent(name=name, pipeline=pipeline, model_configs=model_configs)
        registry = create_default_registry(workspace=str(_workspace))

        try:
            result = await agent.execute(
                input_data,
                tool_registry=registry,
                on_status_change=on_status_sync,
                on_before_iteration=on_before_iteration,
                on_content=on_content_sync,
                on_tool_call=on_tool_call_sync,
                on_iteration=on_iteration_sync,
            )
            live_run.status = "completed"
            live_run.completed_at = time.time()
            live_run.result = result
            live_run.bump_revision()
            elapsed = live_run.completed_at - (live_run.started_at or live_run.completed_at)
            logger.info("Pipeline '%s' completed in %.1fs", name, elapsed)
        except Exception as e:
            live_run.status = "failed"
            live_run.completed_at = time.time()
            live_run.result = {"error": str(e)}
            live_run.bump_revision()
            logger.error("Pipeline '%s' failed: %s", name, e)

    asyncio.get_event_loop().create_task(_execute())

    return JSONResponse({"run_id": live_run.run_id, "status": "started"})


async def api_list_runs(request: Request) -> JSONResponse | Response:
    """GET /api/runs — list all runs. Supports ETag conditional response."""
    etag = _state.runs_etag()

    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})

    runs = [r.to_dict() for r in _state.runs.values()]
    return JSONResponse({"runs": runs}, headers={"ETag": etag})


async def api_get_run(request: Request) -> JSONResponse | Response:
    """GET /api/runs/{run_id} — get run status. Supports ETag conditional response."""
    run_id = request.path_params["run_id"]
    run = _state.runs.get(run_id)
    if not run:
        return JSONResponse({"error": "Run not found"}, status_code=404)

    etag = run.etag
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})

    return JSONResponse(run.to_dict(), headers={"ETag": etag})


async def api_get_task_logs(request: Request) -> JSONResponse:
    """GET /api/runs/{run_id}/tasks/{task_name}/logs — get task logs with cursor pagination.

    Query params:
        after (int): Return only log entries at index >= after. Default: 0.
    """
    run_id = request.path_params["run_id"]
    task_name = request.path_params["task_name"]
    run = _state.runs.get(run_id)
    if not run:
        return JSONResponse({"error": "Run not found"}, status_code=404)
    task = run.tasks.get(task_name)
    if not task:
        return JSONResponse({"error": f"Task '{task_name}' not found"}, status_code=404)

    after = int(request.query_params.get("after", "0"))
    logs_slice = task.logs[after:]
    cursor = task.log_count

    return JSONResponse({"logs": logs_slice, "cursor": cursor, "status": task.status})


async def api_pause_run(request: Request) -> JSONResponse:
    """POST /api/runs/{run_id}/pause"""
    run_id = request.path_params["run_id"]
    _state.pause_run(run_id)
    logger.info("Run %s PAUSED", run_id)
    return JSONResponse({"status": "paused", "run_id": run_id})


async def api_resume_run(request: Request) -> JSONResponse:
    """POST /api/runs/{run_id}/resume"""
    run_id = request.path_params["run_id"]
    _state.resume_run(run_id)
    logger.info("Run %s RESUMED", run_id)
    return JSONResponse({"status": "running", "run_id": run_id})


async def api_update_task(request: Request) -> JSONResponse:
    """PATCH /api/runs/{run_id}/tasks/{task_name} — update task mid-run.

    Saves override files to {LOGS_DIR}/permissions/, {LOGS_DIR}/goals/, {LOGS_DIR}/prompts/.
    Original files on disk are never modified.
    """
    run_id = request.path_params["run_id"]
    task_name = request.path_params["task_name"]
    body = await request.json()

    updates: dict[str, Any] = {}
    saved_files: list[str] = []
    ts = time.strftime("%Y%m%d_%H%M%S")

    if "permissions" in body:
        from agentpipe.core.task import Permissions

        perms = Permissions(body["permissions"])
        updates["permissions"] = perms
        path = _save_override("permissions", task_name, ts, body["permissions"])
        if path:
            saved_files.append(path)

    if "goal" in body:
        updates["goal"] = body["goal"]
        path = _save_override("goals", task_name, ts, body["goal"])
        if path:
            saved_files.append(path)

    if "system_prompt" in body:
        updates["system_prompt"] = body["system_prompt"]
        path = _save_override("prompts", task_name, ts, body["system_prompt"])
        if path:
            saved_files.append(path)

    if "max_iterations" in body:
        updates["max_iterations"] = body["max_iterations"]

    _state.set_task_update(run_id, task_name, updates)

    # Bump revision so polling clients see the update
    run = _state.runs.get(run_id)
    if run:
        run.bump_revision()

    return JSONResponse(
        {
            "status": "queued",
            "task": task_name,
            "updates": list(updates.keys()),
            "saved_files": saved_files,
        }
    )


def _save_override(category: str, task_name: str, timestamp: str, content: Any) -> str | None:
    """Save an override file to {LOGS_DIR}/{category}/{task_name}_{timestamp}.yaml|md.

    Never overwrites existing files. Returns the saved file path or None.
    """
    from agentpipe import config

    if not config.LOGS_DIR:
        return None

    override_dir = Path(config.LOGS_DIR) / category
    override_dir.mkdir(parents=True, exist_ok=True)

    if category == "permissions":
        filename = f"{task_name}_{timestamp}.yaml"
        filepath = override_dir / filename
        import yaml

        header = (
            f"# Permission override for task: {task_name}\n"
            f"# Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"# This file was created by the UI. Original files are unchanged.\n"
        )
        if isinstance(content, dict):
            filepath.write_text(header + yaml.dump(content, default_flow_style=False))
        else:
            filepath.write_text(header + str(content))
    elif category in ("goals", "prompts"):
        filename = f"{task_name}_{timestamp}.md"
        filepath = override_dir / filename
        header = (
            f"<!-- Override for task: {task_name} -->\n"
            f"<!-- Time: {time.strftime('%Y-%m-%d %H:%M:%S')} -->\n"
            f"<!-- Created by UI. Original files unchanged. -->\n\n"
        )
        filepath.write_text(header + str(content))
    else:
        return None

    logger.info("Override saved: %s", filepath)
    return str(filepath)


async def api_reload(request: Request) -> JSONResponse:
    """POST /api/reload — rescan pipelines directory and reload config.

    Call this after editing YAML files on disk to pick up changes
    without restarting the server.
    """
    global _pipelines_dir
    # Re-read config from env (in case env vars changed)
    import importlib

    from agentpipe import config

    importlib.reload(config)

    _pipelines_dir = Path(config.PIPELINES_DIR)
    if not _pipelines_dir.is_absolute():
        _pipelines_dir = _workspace / _pipelines_dir

    pipelines = _scan_pipelines()
    return JSONResponse(
        {
            "status": "reloaded",
            "pipelines_dir": str(_pipelines_dir),
            "pipelines_found": list(pipelines.keys()),
        }
    )


# ============================================================
# App factory
# ============================================================


def create_app(workspace: str = ".") -> Starlette:
    """Create the ASGI application."""
    global _workspace, _pipelines_dir
    _workspace = Path(workspace).resolve()

    from agentpipe import config

    _pipelines_dir = Path(config.PIPELINES_DIR)
    if not _pipelines_dir.is_absolute():
        _pipelines_dir = _workspace / _pipelines_dir

    routes = [
        Route("/api/pipelines", api_list_pipelines),
        Route("/api/pipelines/{name}", api_get_pipeline),
        Route("/api/pipelines/{name}/run", api_run_pipeline, methods=["POST"]),
        Route("/api/runs", api_list_runs),
        Route("/api/runs/{run_id}", api_get_run),
        Route("/api/runs/{run_id}/pause", api_pause_run, methods=["POST"]),
        Route("/api/runs/{run_id}/resume", api_resume_run, methods=["POST"]),
        Route("/api/runs/{run_id}/tasks/{task_name}/logs", api_get_task_logs),
        Route("/api/runs/{run_id}/tasks/{task_name}", api_update_task, methods=["PATCH"]),
        Route("/api/reload", api_reload, methods=["POST"]),
    ]

    middleware = [
        Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
    ]

    return Starlette(routes=routes, middleware=middleware)
