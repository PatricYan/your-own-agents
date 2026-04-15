"""YAML pipeline definition loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agentpipe.core.condition import Condition, Edge
from agentpipe.core.constraint import Constraint
from agentpipe.core.pipeline import ExecutionStrategy, Pipeline
from agentpipe.core.task import TaskDefinition


def load_pipeline_from_yaml(path: str | Path) -> Pipeline:
    """Load a pipeline definition from a YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        A validated Pipeline instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the YAML is invalid or missing required fields.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Pipeline file not found: {path}")

    raw = yaml.safe_load(path.read_text())
    return load_pipeline_from_dict(raw)


def load_pipeline_from_yaml_string(content: str) -> Pipeline:
    """Load a pipeline definition from a YAML string."""
    raw = yaml.safe_load(content)
    return load_pipeline_from_dict(raw)


def load_pipeline_from_dict(raw: dict[str, Any]) -> Pipeline:
    """Load a pipeline definition from a dictionary.

    Args:
        raw: Dictionary with pipeline definition.

    Returns:
        A validated Pipeline instance.
    """
    if not isinstance(raw, dict):
        raise ValueError("Pipeline definition must be a YAML mapping")

    tasks = _parse_tasks(raw.get("tasks", []))
    edges = _parse_edges(raw.get("edges", []))

    strategy = raw.get("execution_strategy", "fail_fast")
    try:
        execution_strategy = ExecutionStrategy(strategy)
    except ValueError:
        raise ValueError(f"Invalid execution_strategy: {strategy}") from None

    return Pipeline(
        name=raw.get("name", "unnamed-pipeline"),
        tasks=tasks,
        edges=edges,
        execution_strategy=execution_strategy,
        max_concurrency=raw.get("max_concurrency"),
        description=raw.get("description"),
    )


def _parse_tasks(
    raw_tasks: list[dict[str, Any]],
    task_store: Any | None = None,
) -> list[TaskDefinition]:
    """Parse task definitions from raw YAML data.

    If a task has a 'ref' field, it references a reusable task definition
    stored in the workspace. The ref is resolved and merged with any
    pipeline-specific overrides.
    """
    tasks = []
    for raw_task in raw_tasks:
        # Handle reusable task references
        if "ref" in raw_task and task_store is not None:
            ref_name = raw_task["ref"]
            try:
                ref_data = task_store.load_task(ref_name)
                # Merge: pipeline-specific fields override ref defaults
                merged = {**ref_data, **{k: v for k, v in raw_task.items() if k != "ref"}}
                raw_task = merged
            except FileNotFoundError:
                raise ValueError(f"Reusable task reference '{ref_name}' not found") from None

        constraints = []
        for raw_constraint in raw_task.get("constraints", []):
            constraints.append(Constraint(**raw_constraint))

        # Handle sub_pipeline
        sub_pipeline = None
        if "sub_pipeline" in raw_task and raw_task["sub_pipeline"]:
            sub_pipeline = load_pipeline_from_dict(raw_task["sub_pipeline"])

        # permissions: dict, file path string, or Permissions object
        raw_perms = raw_task.get("permissions", {})

        task = TaskDefinition(
            name=raw_task["name"],
            goal=raw_task.get("goal", ""),
            system_prompt=raw_task.get("system_prompt"),
            prompt_template=raw_task.get("prompt_template"),
            models=raw_task.get("models", []),
            primary_model=raw_task.get("primary_model"),
            fallback_models=raw_task.get("fallback_models", []),
            permissions=raw_perms,  # validator handles str/dict/Permissions
            tools=raw_task.get("tools", []),
            depends_on=raw_task.get("depends_on", []),
            max_iterations=raw_task.get("max_iterations", 20),
            max_tool_calls=raw_task.get("max_tool_calls"),
            input_schema=raw_task.get("input_schema"),
            output_schema=raw_task.get("output_schema"),
            constraints=constraints,
            is_reusable=raw_task.get("is_reusable", False),
            sub_pipeline=sub_pipeline,
            metadata=raw_task.get("metadata", {}),
        )
        tasks.append(task)
    return tasks


def _parse_edges(raw_edges: list[dict[str, Any]]) -> list[Edge]:
    """Parse edge definitions from raw YAML data."""
    edges = []
    for raw_edge in raw_edges:
        condition = None
        if "condition" in raw_edge and raw_edge["condition"]:
            raw_cond = raw_edge["condition"]
            condition = Condition(
                expression=raw_cond.get("expression", ""),
                description=raw_cond.get("description"),
            )
        edge = Edge(
            source_task=raw_edge["source"],
            target_task=raw_edge["target"],
            condition=condition,
        )
        edges.append(edge)
    return edges
