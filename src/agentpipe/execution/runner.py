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


def _wrap_content_cb(cb: Any, task_name: str) -> Any:
    """Wrap a task-aware on_content callback with a per-task closure."""

    def wrapper(text: str) -> None:
        cb(text, task_name=task_name)

    return wrapper


def _wrap_tool_call_cb(cb: Any, task_name: str) -> Any:
    """Wrap a task-aware on_tool_call callback with a per-task closure."""

    def wrapper(name_: str, args: dict) -> None:
        cb(name_, args, task_name=task_name)

    return wrapper


def _wrap_iteration_cb(cb: Any, task_name: str) -> Any:
    """Wrap a task-aware on_iteration callback with a per-task closure."""

    def wrapper(iteration: int, phase: str, details: list) -> None:
        cb(iteration, phase, details, task_name=task_name)

    return wrapper


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
        on_content: Any | None = None,
        on_tool_call: Any | None = None,
        on_iteration: Any | None = None,
        on_permission_ask: Any | None = None,
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
        self._on_content = on_content
        self._on_tool_call = on_tool_call
        self._on_iteration = on_iteration
        self._on_permission_ask = on_permission_ask

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

        from agentpipe.execution.log_writer import TaskLogWriter

        logger.info("Agent '%s' starting with model '%s'", task.name, model)
        log_writer = TaskLogWriter(task.name)

        # Create per-task callback wrappers that capture the task name.
        # This is critical for parallel tasks — without wrappers, a shared
        # _current_task_name dict causes a race condition where logs from
        # concurrent tasks get attributed to whichever task started last.
        task_on_content = self._on_content
        task_on_tool_call = self._on_tool_call
        task_on_iteration = self._on_iteration or on_iteration

        if self._on_content and hasattr(self._on_content, "_task_aware"):
            task_on_content = _wrap_content_cb(self._on_content, task.name)
        if self._on_tool_call and hasattr(self._on_tool_call, "_task_aware"):
            task_on_tool_call = _wrap_tool_call_cb(self._on_tool_call, task.name)
        if task_on_iteration and hasattr(task_on_iteration, "_task_aware"):
            task_on_iteration = _wrap_iteration_cb(task_on_iteration, task.name)

        agent_loop = AgentLoop(
            provider=provider,
            tool_registry=self._tool_registry,
            on_iteration=task_on_iteration,
            on_before_iteration=self._on_before_iteration,
            on_content=task_on_content,
            on_tool_call=task_on_tool_call,
            on_permission_ask=self._on_permission_ask,
            log_writer=log_writer,
        )

        try:
            result = await agent_loop.run(task, input_data)
            log_writer.log_complete(result)
        except Exception:
            log_writer.close()
            raise

        logger.info(
            "Agent '%s' finished: completed=%s, %d iterations, %d tool calls, %d tokens",
            task.name,
            result.completed,
            result.iterations,
            result.total_tool_calls,
            result.total_tokens,
        )

        if not result.completed and result.error:
            raise RuntimeError(f"Agent '{task.name}' failed: {result.error}")

        return result.output

    # Logs are now written incrementally by TaskLogWriter — no batch save needed.
