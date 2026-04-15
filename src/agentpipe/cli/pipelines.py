"""CLI handlers for 'agents' and 'pipelines' commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from agentpipe.cli.main import ErrorCode, error_output


def cmd_agents(args, workspace: Path, fmt: str) -> int:
    """Dispatch agents subcommands."""
    cmd = args.agents_command
    if cmd == "create":
        return _agents_create(args, workspace, fmt)
    elif cmd == "list":
        return _agents_list(workspace, fmt)
    elif cmd == "inspect":
        return _agents_inspect(args, workspace, fmt)
    elif cmd == "delete":
        return _agents_delete(args, workspace, fmt)
    else:
        print("Usage: agentpipe agents {create|list|inspect|delete}", file=sys.stderr)
        return 1


def cmd_pipelines(args, workspace: Path, fmt: str) -> int:
    """Dispatch pipelines subcommands."""
    cmd = args.pipelines_command
    if cmd == "validate":
        return _pipelines_validate(args, workspace, fmt)
    elif cmd == "dag":
        return _pipelines_dag(args, workspace, fmt)
    elif cmd == "inspect":
        return _pipelines_inspect(args, workspace, fmt)
    else:
        print("Usage: agentpipe pipelines {validate|dag|inspect}", file=sys.stderr)
        return 1


def _agents_create(args, workspace: Path, fmt: str) -> int:
    """Create a new agent from a pipeline definition file."""
    from agentpipe.loader.json_loader import load_pipeline_from_json
    from agentpipe.loader.yaml_loader import load_pipeline_from_yaml
    from agentpipe.storage.definitions import DefinitionStore

    store = DefinitionStore(workspace)
    pipeline_path = Path(args.pipeline)

    # Check if agent already exists
    if args.name in store.list_agents():
        error_output(ErrorCode.PIPELINE_INVALID, f"Agent '{args.name}' already exists", fmt=fmt)
        return 1

    # Load and validate pipeline
    try:
        if pipeline_path.suffix in (".yaml", ".yml"):
            pipeline = load_pipeline_from_yaml(pipeline_path)
        elif pipeline_path.suffix == ".json":
            pipeline = load_pipeline_from_json(pipeline_path)
        else:
            error_output(
                ErrorCode.INPUT_INVALID, f"Unsupported file format: {pipeline_path.suffix}", fmt=fmt
            )
            return 1
    except FileNotFoundError:
        error_output(ErrorCode.INPUT_INVALID, f"Pipeline file not found: {pipeline_path}", fmt=fmt)
        return 1
    except ValueError as e:
        error_output(ErrorCode.PIPELINE_INVALID, str(e), fmt=fmt)
        return 1

    # Collect model names referenced in pipeline
    model_names = set()
    for task in pipeline.tasks:
        if task.primary_model:
            model_names.add(task.primary_model)
        model_names.update(task.fallback_models)

    # Verify models exist
    for model_name in model_names:
        if model_name not in store.list_models():
            error_output(
                ErrorCode.MODEL_NOT_FOUND,
                f"Model '{model_name}' not found. Register it first with: agentpipe models register",
                fmt=fmt,
            )
            return 2

    # Save agent
    pipeline_raw = yaml.safe_load(pipeline_path.read_text())
    agent_data = {
        "name": args.name,
        "description": args.description or "",
        "pipeline": pipeline_raw,
        "model_configs": list(model_names),
    }
    store.save_agent(args.name, agent_data)

    if fmt == "json":
        print(json.dumps({"status": "created", "name": args.name, "tasks": len(pipeline.tasks)}))
    else:
        print(f"Agent '{args.name}' created successfully.")
        print(f"  Pipeline: {pipeline.name}")
        print(f"  Tasks: {len(pipeline.tasks)}")
        print(f"  Models: {', '.join(sorted(model_names))}")

    return 0


def _agents_list(workspace: Path, fmt: str) -> int:
    """List all agents in the workspace."""
    from agentpipe.storage.definitions import DefinitionStore

    store = DefinitionStore(workspace)
    agents = store.list_agents()

    if fmt == "json":
        print(json.dumps({"agents": agents}))
    else:
        if not agents:
            print("No agents found.")
        else:
            print("Agents:")
            for name in agents:
                print(f"  - {name}")

    return 0


def _agents_inspect(args, workspace: Path, fmt: str) -> int:
    """Show detailed agent configuration."""
    from agentpipe.storage.definitions import DefinitionStore

    store = DefinitionStore(workspace)

    try:
        data = store.load_agent(args.name)
    except FileNotFoundError:
        error_output(ErrorCode.AGENT_NOT_FOUND, f"Agent '{args.name}' not found", fmt=fmt)
        return 2

    if fmt == "json":
        print(json.dumps(data, indent=2, default=str))
    else:
        print(f"Agent: {data.get('name', args.name)}")
        print(f"  Description: {data.get('description', 'N/A')}")
        pipeline = data.get("pipeline", {})
        tasks = pipeline.get("tasks", [])
        edges = pipeline.get("edges", [])
        print(f"  Pipeline: {pipeline.get('name', 'unnamed')}")
        print(f"  Tasks ({len(tasks)}):")
        for t in tasks:
            print(f"    - {t.get('name', '?')} (model: {t.get('primary_model', 'N/A')})")
        print(f"  Edges ({len(edges)}):")
        for e in edges:
            cond = ""
            if e.get("condition"):
                cond = f" [if {e['condition'].get('expression', '')}]"
            print(f"    {e.get('source', '?')} -> {e.get('target', '?')}{cond}")
        print(f"  Models: {', '.join(data.get('model_configs', []))}")

    return 0


def _agents_delete(args, workspace: Path, fmt: str) -> int:
    """Delete an agent definition."""
    from agentpipe.storage.definitions import DefinitionStore

    store = DefinitionStore(workspace)

    try:
        store.delete_agent(args.name)
    except FileNotFoundError:
        error_output(ErrorCode.AGENT_NOT_FOUND, f"Agent '{args.name}' not found", fmt=fmt)
        return 2

    if fmt == "json":
        print(json.dumps({"status": "deleted", "name": args.name}))
    else:
        print(f"Agent '{args.name}' deleted.")

    return 0


def _pipelines_validate(args, workspace: Path, fmt: str) -> int:
    """Validate a pipeline definition file."""
    from agentpipe.loader.json_loader import load_pipeline_from_json
    from agentpipe.loader.yaml_loader import load_pipeline_from_yaml

    path = Path(args.path)

    try:
        if path.suffix in (".yaml", ".yml"):
            pipeline = load_pipeline_from_yaml(path)
        elif path.suffix == ".json":
            pipeline = load_pipeline_from_json(path)
        else:
            error_output(
                ErrorCode.INPUT_INVALID, f"Unsupported file format: {path.suffix}", fmt=fmt
            )
            return 1
    except FileNotFoundError:
        error_output(ErrorCode.INPUT_INVALID, f"File not found: {path}", fmt=fmt)
        return 1
    except ValueError as e:
        msg = str(e)
        code = ErrorCode.CYCLE_DETECTED if "cycle" in msg.lower() else ErrorCode.PIPELINE_INVALID
        error_output(code, msg, fmt=fmt)
        return 1

    # Collect referenced models
    model_names = set()
    for task in pipeline.tasks:
        if task.primary_model:
            model_names.add(task.primary_model)
        model_names.update(task.fallback_models)

    if fmt == "json":
        print(
            json.dumps(
                {
                    "status": "valid",
                    "name": pipeline.name,
                    "tasks": len(pipeline.tasks),
                    "edges": len(pipeline.edges),
                    "models_referenced": sorted(model_names),
                }
            )
        )
    else:
        print(f"Pipeline '{pipeline.name}' is valid.")
        print(f"  Tasks: {len(pipeline.tasks)}")
        print(f"  Edges: {len(pipeline.edges)}")
        print(f"  Models referenced: {', '.join(sorted(model_names)) or 'none'}")
        print("  No cycles detected.")

    return 0


def _pipelines_dag(args, workspace: Path, fmt: str) -> int:
    """Render the pipeline DAG visually (like Airflow's graph view)."""
    from agentpipe.loader.json_loader import load_pipeline_from_json
    from agentpipe.loader.yaml_loader import load_pipeline_from_yaml

    path = Path(args.path)

    try:
        if path.suffix in (".yaml", ".yml"):
            pipeline = load_pipeline_from_yaml(path)
        elif path.suffix == ".json":
            pipeline = load_pipeline_from_json(path)
        else:
            error_output(
                ErrorCode.INPUT_INVALID, f"Unsupported file format: {path.suffix}", fmt=fmt
            )
            return 1
    except FileNotFoundError:
        error_output(ErrorCode.INPUT_INVALID, f"File not found: {path}", fmt=fmt)
        return 1
    except ValueError as e:
        error_output(ErrorCode.PIPELINE_INVALID, str(e), fmt=fmt)
        return 1

    diagram_fmt = "mermaid" if getattr(args, "mermaid", False) else "ascii"

    if fmt == "json":
        print(json.dumps({"dag": pipeline.render_dag(diagram_fmt)}, indent=2))
    else:
        print(pipeline.render_dag(diagram_fmt))

    return 0


def _pipelines_inspect(args, workspace: Path, fmt: str) -> int:
    """Inspect a pipeline's structure from an agent."""
    from agentpipe.storage.definitions import DefinitionStore

    store = DefinitionStore(workspace)

    try:
        data = store.load_agent(args.agent_name)
    except FileNotFoundError:
        error_output(ErrorCode.AGENT_NOT_FOUND, f"Agent '{args.agent_name}' not found", fmt=fmt)
        return 2

    pipeline_data = data.get("pipeline", {})
    if fmt == "json":
        print(json.dumps(pipeline_data, indent=2, default=str))
    else:
        print(f"Pipeline: {pipeline_data.get('name', 'unnamed')}")
        print(f"Strategy: {pipeline_data.get('execution_strategy', 'fail_fast')}")
        tasks = pipeline_data.get("tasks", [])
        for t in tasks:
            print(f"\n  Task: {t.get('name', '?')}")
            print(f"    Model: {t.get('primary_model', 'N/A')}")
            fallbacks = t.get("fallback_models", [])
            if fallbacks:
                print(f"    Fallbacks: {', '.join(fallbacks)}")
            constraints = t.get("constraints", [])
            if constraints:
                for c in constraints:
                    print(
                        f"    Constraint: {c.get('type')}={c.get('value')} (on_violation={c.get('on_violation')})"
                    )

    return 0
