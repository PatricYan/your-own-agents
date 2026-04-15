"""Recovery strategies for failed task execution."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agentpipe.core.constraint import ConstraintType
from agentpipe.core.task import TaskDefinition
from agentpipe.execution.runner import TaskRunner

logger = logging.getLogger(__name__)


class RecoveryManager:
    """Manages recovery strategies for failed tasks.

    Implements a three-tier recovery cascade:
      Tier 1: Retry with same parameters (exponential backoff)
      Tier 2: Retry with fallback models
      Tier 3: Subtask decomposition
    """

    def __init__(self, runner: TaskRunner) -> None:
        self._runner = runner

    async def attempt_recovery(
        self,
        task: TaskDefinition,
        input_data: dict[str, Any],
        error: Exception,
        attempt: int,
    ) -> dict[str, Any] | None:
        """Attempt to recover from a task failure.

        Args:
            task: The failed task definition.
            input_data: The input data that was used.
            error: The exception that caused the failure.
            attempt: Current attempt number (0-indexed).

        Returns:
            Output data if recovery succeeds, None if all strategies exhausted.
        """
        recovery_log: list[dict[str, Any]] = []

        # Tier 1: Retry with same parameters
        max_retries = self._get_max_retries(task)
        if attempt < max_retries:
            backoff = min(2**attempt, 30)  # Cap at 30 seconds
            logger.info(
                "Task '%s': Tier 1 retry (attempt %d/%d, backoff %.1fs)",
                task.name,
                attempt + 1,
                max_retries,
                backoff,
            )
            await asyncio.sleep(backoff)
            try:
                result = await self._runner.run_task(task, input_data)
                return result
            except Exception as retry_err:
                recovery_log.append(
                    {
                        "tier": 1,
                        "strategy": "retry",
                        "attempt": attempt + 1,
                        "error": str(retry_err),
                    }
                )
                logger.debug("Task '%s': Tier 1 retry failed: %s", task.name, retry_err)

        # Tier 2: Fallback models
        for fallback_model in task.fallback_models:
            logger.info("Task '%s': Tier 2 fallback to model '%s'", task.name, fallback_model)
            try:
                result = await self._runner.run_task(task, input_data, model_name=fallback_model)
                return result
            except Exception as fallback_err:
                recovery_log.append(
                    {
                        "tier": 2,
                        "strategy": "fallback_model",
                        "model": fallback_model,
                        "error": str(fallback_err),
                    }
                )
                logger.debug(
                    "Task '%s': Tier 2 fallback '%s' failed: %s",
                    task.name,
                    fallback_model,
                    fallback_err,
                )

        # Tier 3: Subtask decomposition
        # Check if any constraint has on_violation=decompose
        from agentpipe.core.constraint import ViolationAction

        should_decompose = any(
            c.on_violation == ViolationAction.DECOMPOSE for c in task.constraints
        )
        if should_decompose and task.primary_model:
            logger.info("Task '%s': Tier 3 subtask decomposition", task.name)
            try:
                result = await self._attempt_decomposition(task, input_data, error)
                if result is not None:
                    return result
            except Exception as decompose_err:
                recovery_log.append(
                    {
                        "tier": 3,
                        "strategy": "decompose",
                        "error": str(decompose_err),
                    }
                )
                logger.debug("Task '%s': Tier 3 decomposition failed: %s", task.name, decompose_err)

        # All recovery exhausted
        logger.warning("Task '%s': All recovery strategies exhausted", task.name)
        return None

    async def _attempt_decomposition(
        self,
        task: TaskDefinition,
        input_data: dict[str, Any],
        error: Exception,
    ) -> dict[str, Any] | None:
        """Attempt to decompose a failed task into subtasks.

        Prompts the model to break down the task, then executes the subtasks
        sequentially and aggregates the results.
        """
        decompose_prompt = (
            f"The following task failed with error: {error}\n\n"
            f"Original task: {task.prompt_template}\n\n"
            f"Please break this task into 2-3 smaller, simpler steps. "
            f"For each step, provide the instruction on a new line prefixed with 'STEP: '.\n"
            f"Input data: {input_data}"
        )

        try:
            # Use the primary model to get decomposition
            response = await self._runner.run_task(
                TaskDefinition(
                    name=f"{task.name}_decompose",
                    prompt_template=decompose_prompt,
                    primary_model=task.primary_model,
                ),
                input_data,
            )

            # Parse steps from response
            response_text = response.get("text", response.get("raw", ""))
            steps = [
                line.replace("STEP:", "").strip()
                for line in str(response_text).split("\n")
                if line.strip().startswith("STEP:")
            ]

            if not steps:
                logger.debug("Task '%s': Decomposition produced no steps", task.name)
                return None

            # Execute subtasks sequentially
            current_input = input_data
            for i, step in enumerate(steps):
                subtask = TaskDefinition(
                    name=f"{task.name}_subtask_{i}",
                    prompt_template=step + "\n\nInput: {input}",
                    primary_model=task.primary_model,
                )
                current_input = await self._runner.run_task(subtask, current_input)

            return current_input

        except Exception as e:
            logger.debug("Task '%s': Decomposition execution failed: %s", task.name, e)
            return None

    def _get_max_retries(self, task: TaskDefinition) -> int:
        """Get the max retries constraint value for a task."""
        for constraint in task.constraints:
            if constraint.type == ConstraintType.MAX_RETRIES:
                return int(constraint.value)
        return 0  # Default: no retries
