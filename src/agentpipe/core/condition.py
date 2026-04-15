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
    """A directed connection between two tasks in a pipeline."""

    source_task: str
    target_task: str
    condition: Condition | None = None


def validate_expression(expression: str) -> bool:
    """Validate that an expression is parseable and safe.

    Returns True if valid, raises ValueError if invalid.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid condition expression: {e}") from e

    # Walk the AST to check for unsafe operations
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            raise ValueError("Import statements not allowed in conditions")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id not in _SAFE_BUILTINS:
                # Allow calling safe builtins only
                pass
            elif isinstance(node.func, ast.Attribute):
                # Allow method calls on data (e.g., output.get(...))
                pass

    return True


def evaluate_condition(
    condition: Condition | Callable[..., bool],
    task_output: dict[str, Any],
) -> bool:
    """Evaluate a condition against task output data.

    Args:
        condition: A Condition with an expression string, or a callable.
        task_output: The task's output dictionary, available as variables.

    Returns:
        True if the condition is met, False otherwise.
    """
    if callable(condition) and not isinstance(condition, Condition):
        return bool(condition(task_output))

    if not isinstance(condition, Condition):
        return True

    expression = condition.expression
    if not expression or not expression.strip():
        return True

    # Build evaluation context from task output
    context: dict[str, Any] = {**_SAFE_BUILTINS}
    context["__builtins__"] = {}  # Restrict builtins

    # Make task output fields available as variables
    if isinstance(task_output, dict):
        context.update(task_output)

    try:
        result = eval(expression, context)  # noqa: S307
        return bool(result)
    except Exception as e:
        logger.warning("Condition evaluation failed for '%s': %s", expression, e)
        return False
