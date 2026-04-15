"""Task runner: executes tasks as autonomous agents via the agent loop."""

from __future__ import annotations

import logging
from typing import Any

from agentpipe.core.task import TaskDefinition
from agentpipe.execution.agent_loop import AgentLoop, BeforeIterationHook, IterationCallback
from agentpipe.models.provider import ModelProvider
from agentpipe.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class TaskRunner:
    """Runs individual tasks as autonomous agents.

    Each task is executed as an agent loop: the model thinks, uses tools,
    observes results, and iterates until the goal is accomplished.
    """

    def __init__(
        self,
        providers: dict[str, ModelProvider],
        tool_registry: ToolRegistry,
        on_before_iteration: BeforeIterationHook | None = None,
    ) -> None:
        self._providers = providers
        self._tool_registry = tool_registry
        self._on_before_iteration = on_before_iteration

    async def run_task(
        self,
        task: TaskDefinition,
        input_data: dict[str, Any],
        model_name: str | None = None,
        on_iteration: IterationCallback | None = None,
    ) -> dict[str, Any]:
        """Execute a task as an autonomous agent.

        Args:
            task: The task definition (agent configuration).
            input_data: Input data from upstream tasks or user.
            model_name: Override model (for fallback). Defaults to task's primary_model.
            on_iteration: Optional callback for per-iteration progress.

        Returns:
            Dictionary with the task's output data.

        Raises:
            RuntimeError: If the model provider is not found or execution fails.
        """
        model = model_name or task.primary_model
        if not model:
            raise RuntimeError(f"No model assigned to task '{task.name}'")

        provider = self._providers.get(model)
        if provider is None:
            raise RuntimeError(f"Model provider '{model}' not found for task '{task.name}'")

        logger.info("Agent '%s' starting with model '%s'", task.name, model)

        agent_loop = AgentLoop(
            provider=provider,
            tool_registry=self._tool_registry,
            on_iteration=on_iteration,
            on_before_iteration=self._on_before_iteration,
        )

        result = await agent_loop.run(task, input_data)

        if not result.completed:
            if result.error:
                raise RuntimeError(f"Agent '{task.name}' failed: {result.error}")
            logger.warning(
                "Agent '%s' did not complete within %d iterations",
                task.name,
                task.max_iterations,
            )

        logger.info(
            "Agent '%s' finished: %d iterations, %d tool calls",
            task.name,
            result.iterations,
            result.total_tool_calls,
        )

        return result.output
