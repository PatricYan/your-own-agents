"""Task runner: executes tasks as autonomous agents via the agent loop.

Each task gets its own provider instance (own HTTP session, own context).
No state is shared between agents in the same pipeline.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from agentpipe.core.task import TaskDefinition
from agentpipe.execution.agent_loop import AgentLoop, BeforeIterationHook, IterationCallback
from agentpipe.models.provider import ModelProvider
from agentpipe.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Type for a factory that creates a fresh provider from a model name
ProviderFactory = Callable[[str], ModelProvider]


class TaskRunner:
    """Runs individual tasks as autonomous agents.

    Each task gets its own provider instance — no shared sessions or state
    between agents in the same pipeline. This ensures:
    - Each agent has its own HTTP connection
    - Each agent has its own conversation context
    - Parallel agents don't interfere with each other
    """

    def __init__(
        self,
        providers: dict[str, ModelProvider] | None = None,
        tool_registry: ToolRegistry | None = None,
        on_before_iteration: BeforeIterationHook | None = None,
        provider_factory: ProviderFactory | None = None,
    ) -> None:
        """Initialize the task runner.

        Args:
            providers: Shared provider map (backward compat — used if provider_factory is None).
            tool_registry: Tool registry for agent tool access.
            on_before_iteration: Hook for human-in-the-loop control.
            provider_factory: Factory that creates a fresh provider for each task.
                If provided, this is used instead of the shared providers dict.
        """
        self._providers = providers or {}
        self._tool_registry = tool_registry or ToolRegistry()
        self._on_before_iteration = on_before_iteration
        self._provider_factory = provider_factory

    def _get_provider(self, model_name: str) -> ModelProvider:
        """Get a provider for a model — creates a new instance if factory is set."""
        if self._provider_factory:
            return self._provider_factory(model_name)
        provider = self._providers.get(model_name)
        if provider is None:
            raise RuntimeError(f"Model provider '{model_name}' not found")
        return provider

    async def run_task(
        self,
        task: TaskDefinition,
        input_data: dict[str, Any],
        model_name: str | None = None,
        on_iteration: IterationCallback | None = None,
    ) -> dict[str, Any]:
        """Execute a task as an autonomous agent with its own provider instance."""
        model = model_name or task.primary_model
        if not model:
            raise RuntimeError(f"No model assigned to task '{task.name}'")

        # Each task gets its own provider (own session, own context)
        provider = self._get_provider(model)

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
            "Agent '%s' finished: %d iterations, %d tool calls, %d tokens",
            task.name,
            result.iterations,
            result.total_tool_calls,
            result.total_tokens,
        )

        return result.output
