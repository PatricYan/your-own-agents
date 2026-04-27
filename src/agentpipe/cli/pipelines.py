"""CLI pipeline tools: validate, dag."""

from __future__ import annotations

import json
from pathlib import Path

from agentpipe.cli.main import ErrorCode, error_output


def cmd_validate(args, workspace: Path, fmt: str) -> int:
    from agentpipe.loader.yaml_loader import load_pipeline_from_yaml

    path = Path(args.path)
    try:
        pipeline = load_pipeline_from_yaml(path)
    except FileNotFoundError:
        error_output(ErrorCode.INPUT_INVALID, f"File not found: {path}", fmt=fmt)
        return 1
    except ValueError as e:
        code = ErrorCode.CYCLE_DETECTED if "cycle" in str(e).lower() else ErrorCode.PIPELINE_INVALID
        error_output(code, str(e), fmt=fmt)
        return 1

    models = set()
    for task in pipeline.tasks:
        if task.primary_model:
            models.add(task.primary_model)
        models.update(task.fallback_models)

    if fmt == "json":
        print(
            json.dumps(
                {
                    "status": "valid",
                    "name": pipeline.name,
                    "tasks": len(pipeline.tasks),
                    "edges": len(pipeline.edges),
                    "models": sorted(models),
                }
            )
        )
    else:
        print(f"Pipeline '{pipeline.name}' is valid.")
        print(
            f"  Tasks: {len(pipeline.tasks)}, Edges: {len(pipeline.edges)}, Models: {', '.join(sorted(models)) or 'none'}"
        )

    return 0


def cmd_dag(args, workspace: Path, fmt: str) -> int:
    from agentpipe.loader.yaml_loader import load_pipeline_from_yaml

    path = Path(args.path)
    try:
        pipeline = load_pipeline_from_yaml(path)
    except FileNotFoundError:
        error_output(ErrorCode.INPUT_INVALID, f"File not found: {path}", fmt=fmt)
        return 1
    except ValueError as e:
        error_output(ErrorCode.PIPELINE_INVALID, str(e), fmt=fmt)
        return 1

    fmt_type = "mermaid" if getattr(args, "mermaid", False) else "ascii"
    print(pipeline.render_dag(fmt_type))
    return 0
