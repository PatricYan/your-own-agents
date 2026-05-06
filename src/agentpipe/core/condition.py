"""Condition and Edge models for pipeline branching logic."""

from __future__ import annotations

import ast
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Safe builtins allowed in condition expressions
_SAFE_BUILTINS = {
    "True": True,
    "False": False,
    "None": None,
    "abs": abs,
    "len": len,
    "min": min,
    "max": max,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "round": round,
}


class Condition(BaseModel):
    """A user-defined rule that evaluates task outputs to determine execution flow."""

    expression: str
    description: str | None = None


class Edge(BaseModel):
    """A directed connection between two tasks in a pipeline.

    In YAML::

        edges:
          - from: task-a
            to: task-b
            when:
              expression: "score > 0.8"
              description: "Only if quality is high"
    """

    upstream: str
    downstream: str
    condition: Condition | None = None


def validate_expression(expression: str) -> bool:
    """Validate that an expression is parseable and safe."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid condition expression: {e}") from e

    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            raise ValueError("Import statements not allowed in conditions")

    return True


def evaluate_condition(
    condition: Condition | Callable[..., bool],
    task_output: dict[str, Any],
) -> bool:
    """Evaluate a condition against task output data."""
    if callable(condition) and not isinstance(condition, Condition):
        return bool(condition(task_output))

    if not isinstance(condition, Condition):
        return True

    expression = condition.expression
    if not expression or not expression.strip():
        return True

    context: dict[str, Any] = {**_SAFE_BUILTINS}
    context["__builtins__"] = {}

    if isinstance(task_output, dict):
        context.update(task_output)

    try:
        result = eval(expression, context)  # noqa: S307
        return bool(result)
    except Exception as e:
        logger.warning("Condition evaluation failed for '%s': %s", expression, e)
        return False
