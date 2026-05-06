"""Constraint definitions for task execution limits."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, field_validator


class ConstraintType(StrEnum):
    """Types of constraints that can be applied to tasks."""

    MAX_RETRIES = "max_retries"
    TIMEOUT = "timeout"
    QUALITY_THRESHOLD = "quality_threshold"
    CUSTOM = "custom"


class ViolationAction(StrEnum):
    """Actions to take when a constraint is violated."""

    FAIL = "fail"
    SKIP = "skip"
    FALLBACK = "fallback"
    DECOMPOSE = "decompose"


class Constraint(BaseModel):
    """A user-defined limit on task execution behavior."""

    type: ConstraintType
    value: Any
    on_violation: ViolationAction
    description: str | None = None

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: Any, info) -> Any:
        constraint_type = info.data.get("type")
        if constraint_type == ConstraintType.MAX_RETRIES:
            if not isinstance(v, int) or v < 0:
                raise ValueError("max_retries must be a non-negative integer")
        elif constraint_type == ConstraintType.TIMEOUT:
            if not isinstance(v, int | float) or v <= 0:
                raise ValueError("timeout must be a positive number (seconds)")
        elif constraint_type == ConstraintType.QUALITY_THRESHOLD:  # noqa: SIM102
            if not isinstance(v, int | float) or not (0 <= v <= 1):
                raise ValueError("quality_threshold must be a float between 0 and 1")
        return v


class ConstraintViolationError(Exception):
    """Raised when a constraint is violated during task execution."""

    def __init__(self, constraint: Constraint, message: str) -> None:
        self.constraint = constraint
        super().__init__(message)


def check_quality_threshold(output: dict[str, Any], constraint: Constraint) -> bool:
    """Check if task output meets a quality threshold constraint.

    Looks for 'quality_score', 'score', or 'confidence' in the output dict.
    Returns True if quality meets or exceeds the threshold.
    """
    threshold = float(constraint.value)

    # Try common quality score field names
    for key in ("quality_score", "score", "confidence", "quality"):
        if key in output:
            try:
                score = float(output[key])
                return score >= threshold
            except (ValueError, TypeError):
                continue

    # If no quality field found, assume it passes
    return True


def get_constraint(constraints: list[Constraint], ctype: ConstraintType) -> Constraint | None:
    """Get the first constraint of a given type from a list."""
    for c in constraints:
        if c.type == ctype:
            return c
    return None
