"""DAG execution engine: topological sort scheduling with async concurrency."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agentpipe.core.condition import evaluate_condition
from agentpipe.core.constraint import (
    ConstraintType,
    ConstraintViolationError,
    ViolationAction,
    check_quality_threshold,
    get_constraint,
)
from agentpipe.core.pipeline import ExecutionStrategy, Pipeline
from agentpipe.execution.recovery import RecoveryManager
from agentpipe.execution.runner import TaskRunner
from agentpipe.execution.state import (
    RunStatus,
    TaskStatus,
    validate_run_transition,
    validate_task_transition,
)

logger = logging.getLogger(__name__)


class TaskExecutionRecord:
    """Tracks the execution state of a single task."""

    def __init__(self, task_name: str) -> None:
        self.task_name = task_name
        self.status = TaskStatus.PENDING
        self.model_used: str | None = None
        self.input_data: dict[str, Any] = {}
        self.output_data: dict[str, Any] = {}
        self.started_at: float | None = None
        self.completed_at: float | None = None
        self.duration_ms: int | None = None
        self.retry_count: int = 0
        self.recovery_log: list[dict] = []
        self.error: str | None = None

    def set_status(self, new_status: TaskStatus) -> None:
        validate_task_transition(self.status, new_status)
        self.status = new_status


class ExecutionRun:
    """Tracks the state of a complete pipeline execution."""

    def __init__(self, pipeline_name: str) -> None:
        self.id = str(uuid.uuid4())
        self.pipeline_name = pipeline_name
        self.status = RunStatus.PENDING
        self.task_records: dict[str, TaskExecutionRecord] = {}
        self.started_at: float | None = None
        self.completed_at: float | None = None
        self.error: str | None = None
        self._final_output: dict[str, Any] = {}

    def set_status(self, new_status: RunStatus) -> None:
        validate_run_transition(self.status, new_status)
        self.status = new_status


class DAGExecutor:
    """Executes a pipeline DAG with async concurrency, conditions, and recovery."""

    def __init__(
        self,
        runner: TaskRunner,
        recovery: RecoveryManager,
        on_status_change: Callable[[str, TaskStatus, dict], None] | None = None,
        history_store: Any | None = None,
    ) -> None:
        self._runner = runner
        self._recovery = recovery
        self._on_status_change = on_status_change
        self._history_store = history_store

    async def execute(
        self,
        pipeline: Pipeline,
        initial_input: dict[str, Any],
        max_concurrency: int | None = None,
    ) -> ExecutionRun:
        """Execute a pipeline and return the execution run record."""
        # Snapshot pipeline for immutability (FR-014)
        pipeline = pipeline.model_copy(deep=True)

        run = ExecutionRun(pipeline_name=pipeline.name)

        # Initialize task records
        for task in pipeline.tasks:
            run.task_records[task.name] = TaskExecutionRecord(task.name)

        run.set_status(RunStatus.RUNNING)
        run.started_at = time.time()

        concurrency = max_concurrency or pipeline.max_concurrency
        semaphore = asyncio.Semaphore(concurrency) if concurrency else None

        # Track outputs for data passing between tasks
        task_outputs: dict[str, dict[str, Any]] = {}
        # Track which tasks should be skipped due to conditions
        skipped_tasks: set[str] = set()

        try:
            levels = pipeline.topological_sort()

            for level in levels:
                tasks_to_run = []
                task_names_to_run = []

                for task_name in level:
                    record = run.task_records[task_name]

                    # Check if this task was skipped
                    if task_name in skipped_tasks:
                        record.set_status(TaskStatus.SKIPPED)
                        self._emit_status(task_name, TaskStatus.SKIPPED, {})
                        continue

                    if record.status == TaskStatus.SKIPPED:
                        continue

                    # Check if upstream conditions allow this task to run
                    if not self._should_execute(task_name, pipeline, task_outputs, run):
                        record.set_status(TaskStatus.SKIPPED)
                        skipped_tasks.add(task_name)
                        self._emit_status(
                            task_name, TaskStatus.SKIPPED, {"reason": "condition not met"}
                        )
                        # Skip all downstream tasks too
                        self._mark_downstream_skipped(task_name, pipeline, skipped_tasks)
                        continue

                    task_def = pipeline.get_task(task_name)

                    # Gather input from upstream tasks
                    upstream_names = pipeline.get_upstream_tasks(task_name)
                    if upstream_names:
                        merged_input: dict[str, Any] = {}
                        for upstream in upstream_names:
                            if upstream in task_outputs:
                                merged_input.update(task_outputs[upstream])
                        task_input = merged_input
                    else:
                        task_input = initial_input

                    task_names_to_run.append(task_name)
                    tasks_to_run.append(
                        self._execute_task(task_def, task_input, record, semaphore, pipeline)
                    )

                if tasks_to_run:
                    results = await asyncio.gather(*tasks_to_run, return_exceptions=True)

                    for i, task_name in enumerate(task_names_to_run):
                        record = run.task_records[task_name]
                        result = results[i]

                        if isinstance(result, Exception):
                            record.error = str(result)
                            if record.status not in (TaskStatus.FAILED, TaskStatus.SKIPPED):
                                with contextlib.suppress(Exception):
                                    record.set_status(TaskStatus.FAILED)
                            if pipeline.execution_strategy == ExecutionStrategy.FAIL_FAST:
                                raise result
                        elif isinstance(result, dict):
                            task_outputs[task_name] = result

            # Determine final run status
            has_failures = any(r.status == TaskStatus.FAILED for r in run.task_records.values())
            run.set_status(RunStatus.FAILED if has_failures else RunStatus.COMPLETED)

        except Exception as e:
            run.error = str(e)
            if run.status == RunStatus.RUNNING:
                run.set_status(RunStatus.FAILED)
            logger.error("Pipeline '%s' failed: %s", pipeline.name, e)

        run.completed_at = time.time()

        # Collect final output from exit tasks
        exit_tasks = pipeline.get_exit_tasks()
        final_output: dict[str, Any] = {}
        for exit_task in exit_tasks:
            if exit_task in task_outputs:
                final_output.update(task_outputs[exit_task])

        run._final_output = final_output

        # Persist to history if store is available
        if self._history_store:
            self._persist_run(run)

        return run

    def _should_execute(
        self,
        task_name: str,
        pipeline: Pipeline,
        task_outputs: dict[str, dict[str, Any]],
        run: ExecutionRun,
    ) -> bool:
        """Determine if a task should execute based on incoming edge conditions."""
        # Get all incoming edges for this task
        incoming_edges = [e for e in pipeline.edges if e.target_task == task_name]

        if not incoming_edges:
            return True  # Entry task, always execute

        # For a task to run, at least one incoming edge must be active
        for edge in incoming_edges:
            source_record = run.task_records.get(edge.source_task)
            if source_record is None or source_record.status != TaskStatus.COMPLETED:
                continue  # Source not completed

            # If edge has no condition, it's active
            if edge.condition is None:
                return True

            # Evaluate condition against source task's output
            source_output = task_outputs.get(edge.source_task, {})
            if evaluate_condition(edge.condition, source_output):
                return True

        # Check if all incoming edges have been processed
        all_sources_done = all(
            run.task_records.get(e.source_task, TaskExecutionRecord("")).status
            in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED)
            for e in incoming_edges
        )

        return not all_sources_done  # True if some sources haven't finished yet

    def _mark_downstream_skipped(
        self, task_name: str, pipeline: Pipeline, skipped: set[str]
    ) -> None:
        """Mark all downstream tasks as skipped (cascade)."""
        for edge in pipeline.get_downstream_edges(task_name):
            if edge.target_task not in skipped:
                # Only skip if ALL incoming edges would be from skipped tasks
                all_incoming = [e for e in pipeline.edges if e.target_task == edge.target_task]
                all_skipped = all(
                    e.source_task in skipped or e.source_task == task_name for e in all_incoming
                )
                if all_skipped:
                    skipped.add(edge.target_task)
                    self._mark_downstream_skipped(edge.target_task, pipeline, skipped)

    async def _execute_task(
        self,
        task_def,
        input_data: dict[str, Any],
        record: TaskExecutionRecord,
        semaphore: asyncio.Semaphore | None,
        pipeline: Pipeline,
    ) -> dict[str, Any]:
        """Execute a single task with recovery and constraint support."""
        if semaphore:
            async with semaphore:
                return await self._run_with_recovery(task_def, input_data, record)
        return await self._run_with_recovery(task_def, input_data, record)

    async def _run_with_recovery(
        self,
        task_def,
        input_data: dict[str, Any],
        record: TaskExecutionRecord,
    ) -> dict[str, Any]:
        """Run a task with timeout enforcement, quality checks, and recovery."""
        record.set_status(TaskStatus.RUNNING)
        record.started_at = time.time()
        record.input_data = input_data
        record.model_used = task_def.primary_model

        self._emit_status(record.task_name, TaskStatus.RUNNING, {"model": task_def.primary_model})

        # Get timeout constraint
        timeout_constraint = get_constraint(task_def.constraints, ConstraintType.TIMEOUT)
        timeout_seconds = float(timeout_constraint.value) if timeout_constraint else None

        attempt = 0
        max_retries = self._recovery._get_max_retries(task_def)
        last_error: Exception | None = None

        while attempt <= max_retries:
            try:
                # Apply timeout if configured
                if timeout_seconds:
                    result = await asyncio.wait_for(
                        self._runner.run_task(task_def, input_data),
                        timeout=timeout_seconds,
                    )
                else:
                    result = await self._runner.run_task(task_def, input_data)

                # Check quality threshold constraint
                quality_constraint = get_constraint(
                    task_def.constraints, ConstraintType.QUALITY_THRESHOLD
                )
                if quality_constraint and not check_quality_threshold(result, quality_constraint):
                    raise ConstraintViolationError(
                        quality_constraint,
                        f"Quality threshold {quality_constraint.value} not met",
                    )

                record.output_data = result
                record.completed_at = time.time()
                record.duration_ms = int((record.completed_at - record.started_at) * 1000)
                record.set_status(TaskStatus.COMPLETED)
                self._emit_status(
                    record.task_name,
                    TaskStatus.COMPLETED,
                    {
                        "duration_ms": record.duration_ms,
                    },
                )
                return result

            except TimeoutError:
                last_error = TimeoutError(
                    f"Task '{task_def.name}' timed out after {timeout_seconds}s"
                )
                record.recovery_log.append(
                    {
                        "tier": "timeout",
                        "attempt": attempt,
                        "error": str(last_error),
                    }
                )
                if timeout_constraint and timeout_constraint.on_violation == ViolationAction.FAIL:
                    break
                # Otherwise fall through to recovery

            except ConstraintViolationError as cv:
                last_error = cv
                record.recovery_log.append(
                    {
                        "tier": "constraint",
                        "constraint": cv.constraint.type.value,
                        "attempt": attempt,
                        "error": str(cv),
                    }
                )
                if cv.constraint.on_violation == ViolationAction.FAIL:
                    break
                elif cv.constraint.on_violation == ViolationAction.SKIP:
                    record.completed_at = time.time()
                    record.duration_ms = int((record.completed_at - record.started_at) * 1000)
                    record.set_status(TaskStatus.SKIPPED)
                    self._emit_status(
                        record.task_name,
                        TaskStatus.SKIPPED,
                        {
                            "reason": "constraint_skip",
                        },
                    )
                    return {}

            except Exception as e:
                last_error = e
                record.retry_count = attempt

                # Attempt recovery
                recovered = await self._recovery.attempt_recovery(task_def, input_data, e, attempt)
                if recovered is not None:
                    record.output_data = recovered
                    record.completed_at = time.time()
                    record.duration_ms = int((record.completed_at - record.started_at) * 1000)
                    record.set_status(TaskStatus.COMPLETED)
                    self._emit_status(
                        record.task_name,
                        TaskStatus.COMPLETED,
                        {
                            "duration_ms": record.duration_ms,
                            "recovered": True,
                        },
                    )
                    return recovered

            attempt += 1

        # All recovery exhausted
        record.error = str(last_error)
        record.completed_at = time.time()
        record.duration_ms = int((record.completed_at - record.started_at) * 1000)
        record.set_status(TaskStatus.FAILED)
        self._emit_status(record.task_name, TaskStatus.FAILED, {"error": str(last_error)})
        raise RuntimeError(f"Task '{task_def.name}' failed after {attempt} attempts: {last_error}")

    def _emit_status(self, task_name: str, status: TaskStatus, details: dict) -> None:
        """Emit a status change event."""
        if self._on_status_change:
            self._on_status_change(task_name, status, details)

    def _persist_run(self, run: ExecutionRun) -> None:
        """Persist execution run to history store."""
        try:
            run_data = {
                "id": run.id,
                "pipeline_name": run.pipeline_name,
                "status": run.status.value,
                "started_at": datetime.fromtimestamp(run.started_at, tz=UTC).isoformat()
                if run.started_at
                else None,
                "completed_at": datetime.fromtimestamp(run.completed_at, tz=UTC).isoformat()
                if run.completed_at
                else None,
                "error": run.error,
            }
            self._history_store.save_run(run_data)

            for name, record in run.task_records.items():
                task_data = {
                    "id": str(uuid.uuid4()),
                    "run_id": run.id,
                    "task_name": name,
                    "status": record.status.value,
                    "model_used": record.model_used,
                    "input_data": record.input_data,
                    "output_data": record.output_data,
                    "started_at": datetime.fromtimestamp(record.started_at, tz=UTC).isoformat()
                    if record.started_at
                    else None,
                    "completed_at": datetime.fromtimestamp(record.completed_at, tz=UTC).isoformat()
                    if record.completed_at
                    else None,
                    "duration_ms": record.duration_ms,
                    "retry_count": record.retry_count,
                    "recovery_log": record.recovery_log,
                    "error": record.error,
                }
                self._history_store.save_task_execution(task_data)
        except Exception as e:
            logger.warning("Failed to persist execution run: %s", e)
