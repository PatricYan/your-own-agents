"""Pipeline model: DAG definition with validation."""

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from agentpipe.core.condition import Edge
from agentpipe.core.task import TaskDefinition


class ExecutionStrategy(StrEnum):
    """Strategy for handling task failures in a pipeline."""

    FAIL_FAST = "fail_fast"
    CONTINUE_ON_FAILURE = "continue_on_failure"


class Pipeline(BaseModel):
    """A directed acyclic graph (DAG) of tasks defining execution flow.

    Dependencies can be declared in two ways (both supported simultaneously):

    1. **Airflow-style** (preferred): each task lists ``depends_on: [task_a, task_b]``
    2. **Explicit edges**: a top-level ``edges`` list with optional conditions

    During validation the pipeline merges both into a single edge set.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    tasks: list[TaskDefinition]
    edges: list[Edge] = Field(default_factory=list)
    execution_strategy: ExecutionStrategy = ExecutionStrategy.FAIL_FAST
    max_concurrency: int | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_pipeline(self) -> Pipeline:
        """Validate the pipeline DAG structure."""
        if not self.tasks:
            raise ValueError("Pipeline must contain at least one task")

        task_names = {t.name for t in self.tasks}
        if len(task_names) != len(self.tasks):
            raise ValueError("Task names must be unique within a pipeline")

        # ---- Merge Airflow-style depends_on into edges ----
        existing_pairs = {(e.upstream, e.downstream) for e in self.edges}
        for task in self.tasks:
            for up in task.depends_on:
                if up not in task_names:
                    raise ValueError(
                        f"Task '{task.name}' depends_on '{up}' which is not in the pipeline"
                    )
                if (up, task.name) not in existing_pairs:
                    self.edges.append(Edge(upstream=up, downstream=task.name))
                    existing_pairs.add((up, task.name))

        # ---- Standard edge validation ----
        for edge in self.edges:
            if edge.upstream not in task_names:
                raise ValueError(f"Edge upstream '{edge.upstream}' not found in tasks")
            if edge.downstream not in task_names:
                raise ValueError(f"Edge downstream '{edge.downstream}' not found in tasks")
            if edge.upstream == edge.downstream:
                raise ValueError(f"Self-loop detected on task '{edge.upstream}'")

        # Cycle detection
        if self.edges:
            _detect_cycles(task_names, self.edges)

        # Validate condition expressions on edges
        for edge in self.edges:
            if edge.condition and edge.condition.expression:
                from agentpipe.core.condition import validate_expression

                try:
                    validate_expression(edge.condition.expression)
                except ValueError as e:
                    raise ValueError(
                        f"Invalid condition on edge {edge.upstream} -> {edge.downstream}: {e}"
                    ) from e

        return self

    # -- query helpers (unchanged) --

    def topological_sort(self) -> list[list[str]]:
        """Return tasks grouped by execution level (parallel groups)."""
        task_names = {t.name for t in self.tasks}
        return _topological_sort_levels(task_names, self.edges)

    def get_task(self, name: str) -> TaskDefinition:
        for task in self.tasks:
            if task.name == name:
                return task
        raise KeyError(f"Task '{name}' not found in pipeline")

    def get_downstream_edges(self, task_name: str) -> list[Edge]:
        return [e for e in self.edges if e.upstream == task_name]

    def get_upstream_tasks(self, task_name: str) -> list[str]:
        return [e.upstream for e in self.edges if e.downstream == task_name]

    def get_entry_tasks(self) -> list[str]:
        downstreams = {e.downstream for e in self.edges}
        return [t.name for t in self.tasks if t.name not in downstreams]

    def get_exit_tasks(self) -> list[str]:
        upstreams = {e.upstream for e in self.edges}
        return [t.name for t in self.tasks if t.name not in upstreams]

    def render_dag(self, fmt: str = "ascii") -> str:
        """Render the pipeline DAG as a visual diagram.

        Args:
            fmt: Output format — ``"ascii"`` (terminal) or ``"mermaid"`` (Markdown/GitHub).

        Returns:
            String containing the rendered DAG.
        """
        from agentpipe.core.visualize import render_ascii, render_mermaid

        if fmt == "mermaid":
            return render_mermaid(self)
        return render_ascii(self)


# ---------- graph algorithms (unchanged) ----------


def _detect_cycles(task_names: set[str], edges: list[Edge]) -> None:
    in_degree: dict[str, int] = defaultdict(int)
    adjacency: dict[str, list[str]] = defaultdict(list)
    for name in task_names:
        in_degree[name] = 0
    for edge in edges:
        adjacency[edge.upstream].append(edge.downstream)
        in_degree[edge.downstream] += 1
    queue = deque(name for name in task_names if in_degree[name] == 0)
    visited_count = 0
    while queue:
        node = queue.popleft()
        visited_count += 1
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    if visited_count != len(task_names):
        raise ValueError("Pipeline contains circular dependencies (cycle detected)")


def _topological_sort_levels(task_names: set[str], edges: list[Edge]) -> list[list[str]]:
    in_degree: dict[str, int] = defaultdict(int)
    adjacency: dict[str, list[str]] = defaultdict(list)
    for name in task_names:
        in_degree[name] = 0
    for edge in edges:
        adjacency[edge.upstream].append(edge.downstream)
        in_degree[edge.downstream] += 1
    levels: list[list[str]] = []
    current_level = sorted(name for name in task_names if in_degree[name] == 0)
    while current_level:
        levels.append(current_level)
        next_level = []
        for node in current_level:
            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    next_level.append(neighbor)
        current_level = sorted(next_level)
    return levels
