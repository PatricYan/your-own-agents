"""REST API + WebSocket server for pipeline visualization and control."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

from agentpipe.web.state import ServerState

# Shared state — injected at startup
_state = ServerState()
_workspace: Path = Path(".")


def get_state() -> ServerState:
    return _state


# ============================================================
# REST API Endpoints
# ============================================================


async def api_list_pipelines(request: Request) -> JSONResponse:
    """GET /api/pipelines — list all agents and their pipelines."""
    from agentpipe.storage.definitions import DefinitionStore

    store = DefinitionStore(_workspace)
    agents = []
    for name in store.list_agents():
        data = store.load_agent(name)
        agents.append({"name": name, "pipeline": data.get("pipeline", {}).get("name", name)})
    return JSONResponse({"agents": agents})


async def api_get_pipeline(request: Request) -> JSONResponse:
    """GET /api/pipelines/{name} — get pipeline DAG structure."""
    name = request.path_params["name"]
    from agentpipe.storage.definitions import DefinitionStore

    store = DefinitionStore(_workspace)
    try:
        data = store.load_agent(name)
    except FileNotFoundError:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)

    from agentpipe.loader.yaml_loader import load_pipeline_from_dict

    try:
        pipeline = load_pipeline_from_dict(data.get("pipeline", {}))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # Build node/edge structure for the frontend
    nodes = []
    for task in pipeline.tasks:
        perms = task.permissions
        nodes.append(
            {
                "id": task.name,
                "goal": task.goal,
                "model": task.primary_model,
                "permissions": perms.to_dict(),
                "depends_on": task.depends_on,
                "max_iterations": task.max_iterations,
                "system_prompt": task.system_prompt,
            }
        )

    edges = []
    for edge in pipeline.edges:
        e: dict[str, Any] = {"source": edge.source_task, "target": edge.target_task}
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
        }
    )


async def api_run_pipeline(request: Request) -> JSONResponse:
    """POST /api/pipelines/{name}/run — start a pipeline execution."""
    name = request.path_params["name"]
    body = await request.json()
    input_data = body.get("input", {})

    from agentpipe.loader.yaml_loader import load_pipeline_from_dict
    from agentpipe.models.adapters import create_provider
    from agentpipe.models.registry import ModelConfig
    from agentpipe.storage.definitions import DefinitionStore

    store = DefinitionStore(_workspace)
    try:
        agent_data = store.load_agent(name)
    except FileNotFoundError:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)

    pipeline = load_pipeline_from_dict(agent_data.get("pipeline", {}))

    # Build model providers
    providers = {}
    for mc_name in agent_data.get("model_configs", []):
        try:
            mc_data = store.load_model(mc_name)
            mc = ModelConfig(**mc_data)
            providers[mc.name] = create_provider(mc)
        except Exception:
            pass

    # Create live run
    task_names = [t.name for t in pipeline.tasks]
    live_run = _state.create_run(pipeline.name, task_names)
    live_run.status = "running"

    # Status callback — updates live state + broadcasts via WebSocket
    async def on_status(task_name, status, details):
        lt = live_run.tasks.get(task_name)
        if lt:
            lt.status = status.value
            if status.value == "running":
                lt.model = details.get("model")
                lt.started_at = time.time()
            elif status.value in ("completed", "failed"):
                lt.completed_at = time.time()
                lt.duration_ms = details.get("duration_ms", 0)
                lt.error = details.get("error")
        await _state.broadcast(
            {
                "type": "task_status",
                "run_id": live_run.run_id,
                "task": task_name,
                "status": status.value,
                "details": details,
            }
        )

    def on_status_sync(task_name, status, details):
        asyncio.get_event_loop().create_task(on_status(task_name, status, details))

    # Before-iteration hook — checks for pauses and queued task updates
    def on_before_iteration(iteration, task):
        # Check for queued updates from the API
        updates = _state.pop_task_update(live_run.run_id, task.name)
        lt = live_run.tasks.get(task.name)
        if lt:
            lt.iteration = iteration
        if updates:
            return task.model_copy(update=updates)
        return None

    # Run in background
    async def _execute():
        from agentpipe.execution.engine import DAGExecutor
        from agentpipe.execution.recovery import RecoveryManager
        from agentpipe.execution.runner import TaskRunner
        from agentpipe.tools.registry import create_default_registry

        registry = create_default_registry(workspace=str(_workspace))
        runner = TaskRunner(providers, registry, on_before_iteration=on_before_iteration)
        recovery = RecoveryManager(runner)
        executor = DAGExecutor(runner, recovery, on_status_change=on_status_sync)

        try:
            run = await executor.execute(pipeline, input_data)
            live_run.status = run.status.value
            live_run.completed_at = time.time()
            live_run.result = run._final_output
        except Exception:
            live_run.status = "failed"
            live_run.completed_at = time.time()

        await _state.broadcast(
            {
                "type": "run_complete",
                "run_id": live_run.run_id,
                "status": live_run.status,
            }
        )

    asyncio.get_event_loop().create_task(_execute())

    return JSONResponse({"run_id": live_run.run_id, "status": "started"})


async def api_list_runs(request: Request) -> JSONResponse:
    """GET /api/runs — list all runs."""
    runs = [r.to_dict() for r in _state.runs.values()]
    return JSONResponse({"runs": runs})


async def api_get_run(request: Request) -> JSONResponse:
    """GET /api/runs/{run_id} — get run status."""
    run_id = request.path_params["run_id"]
    run = _state.runs.get(run_id)
    if not run:
        return JSONResponse({"error": "Run not found"}, status_code=404)
    return JSONResponse(run.to_dict())


async def api_pause_run(request: Request) -> JSONResponse:
    """POST /api/runs/{run_id}/pause — pause a running pipeline."""
    run_id = request.path_params["run_id"]
    _state.pause_run(run_id)
    await _state.broadcast({"type": "run_paused", "run_id": run_id})
    return JSONResponse({"status": "paused", "run_id": run_id})


async def api_resume_run(request: Request) -> JSONResponse:
    """POST /api/runs/{run_id}/resume — resume a paused pipeline."""
    run_id = request.path_params["run_id"]
    _state.resume_run(run_id)
    await _state.broadcast({"type": "run_resumed", "run_id": run_id})
    return JSONResponse({"status": "running", "run_id": run_id})


async def api_update_task(request: Request) -> JSONResponse:
    """PATCH /api/runs/{run_id}/tasks/{task_name} — update task config mid-run.

    Body: {"permissions": {...}, "goal": "...", "system_prompt": "...", "max_iterations": N}
    """
    run_id = request.path_params["run_id"]
    task_name = request.path_params["task_name"]
    body = await request.json()

    # Build update dict
    updates: dict[str, Any] = {}
    if "permissions" in body:
        from agentpipe.core.task import Permissions

        updates["permissions"] = Permissions(body["permissions"])
    if "goal" in body:
        updates["goal"] = body["goal"]
    if "system_prompt" in body:
        updates["system_prompt"] = body["system_prompt"]
    if "max_iterations" in body:
        updates["max_iterations"] = body["max_iterations"]

    _state.set_task_update(run_id, task_name, updates)

    await _state.broadcast(
        {
            "type": "task_updated",
            "run_id": run_id,
            "task": task_name,
            "updates": {k: str(v) for k, v in body.items()},
        }
    )

    return JSONResponse({"status": "queued", "task": task_name, "updates": list(updates.keys())})


async def api_list_models(request: Request) -> JSONResponse:
    """GET /api/models — list registered models."""
    from agentpipe.storage.definitions import DefinitionStore

    store = DefinitionStore(_workspace)
    models = []
    for name in store.list_models():
        data = store.load_model(name)
        models.append(data)
    return JSONResponse({"models": models})


# ============================================================
# WebSocket endpoint
# ============================================================


async def ws_events(websocket: WebSocket) -> None:
    """WebSocket /ws — stream live execution events to the frontend."""
    await websocket.accept()
    queue = _state.add_ws_client()
    try:
        while True:
            msg = await queue.get()
            await websocket.send_text(msg)
    except Exception:
        pass
    finally:
        _state.remove_ws_client(queue)


# ============================================================
# App factory
# ============================================================


def create_app(workspace: str = ".", static_dir: str | None = None) -> Starlette:
    """Create the Starlette ASGI application."""
    global _workspace
    _workspace = Path(workspace).resolve()

    routes = [
        Route("/api/pipelines", api_list_pipelines),
        Route("/api/pipelines/{name}", api_get_pipeline),
        Route("/api/pipelines/{name}/run", api_run_pipeline, methods=["POST"]),
        Route("/api/runs", api_list_runs),
        Route("/api/runs/{run_id}", api_get_run),
        Route("/api/runs/{run_id}/pause", api_pause_run, methods=["POST"]),
        Route("/api/runs/{run_id}/resume", api_resume_run, methods=["POST"]),
        Route("/api/runs/{run_id}/tasks/{task_name}", api_update_task, methods=["PATCH"]),
        Route("/api/models", api_list_models),
        WebSocketRoute("/ws", ws_events),
    ]

    # Serve React build if available
    if static_dir:
        static_path = Path(static_dir)
        if static_path.exists():
            routes.append(Mount("/", app=StaticFiles(directory=str(static_path), html=True)))

    middleware = [
        Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
    ]

    return Starlette(routes=routes, middleware=middleware)
