"""Execution state machine for pipeline and task status tracking."""

from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    """Status of a task within a pipeline execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RunStatus(StrEnum):
    """Status of an overall pipeline execution run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Valid state transitions
_TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.SKIPPED},
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: {TaskStatus.RUNNING},  # Allow retry
    TaskStatus.SKIPPED: set(),
}

_RUN_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.PENDING: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.RUNNING: {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED},
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
    RunStatus.CANCELLED: set(),
}


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""


def validate_task_transition(current: TaskStatus, target: TaskStatus) -> None:
    """Validate that a task state transition is allowed.

    Raises:
        InvalidTransitionError: If the transition is not valid.
    """
    if target not in _TASK_TRANSITIONS[current]:
        raise InvalidTransitionError(f"Invalid task transition: {current.value} -> {target.value}")


def validate_run_transition(current: RunStatus, target: RunStatus) -> None:
    """Validate that a run state transition is allowed.

    Raises:
        InvalidTransitionError: If the transition is not valid.
    """
    if target not in _RUN_TRANSITIONS[current]:
        raise InvalidTransitionError(f"Invalid run transition: {current.value} -> {target.value}")
