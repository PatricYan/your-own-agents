"""Agent entity: top-level container for pipeline, models, and tool configuration."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from agentpipe.core.pipeline import Pipeline
from agentpipe.models.registry import ModelConfig


class Agent(BaseModel):
    """A named, top-level entity that encapsulates a pipeline of autonomous agent-tasks.

    Each task in the pipeline runs as an autonomous agent with its own model,
    tools, and goal. The Agent orchestrates their execution as a DAG.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str | None = None
    pipeline: Pipeline
    model_configs: list[ModelConfig] = Field(default_factory=list)
    workspace: str | None = None  # Shared workspace path for all agent-tasks
    default_tools: list[str] = Field(default_factory=list)  # Default tools for all tasks
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Agent name must be non-empty")
        return v.strip()

    @model_validator(mode="after")
    def validate_agent(self) -> Agent:
        if not self.model_configs:
            raise ValueError("Agent must have at least one model configuration")
        return self

    async def execute(
        self,
        input_data: dict[str, Any],
        providers: dict[str, Any] | None = None,
        tool_registry: Any | None = None,
        on_status_change=None,
        on_before_iteration=None,
    ) -> dict[str, Any]:
        """Execute this agent's pipeline of autonomous tasks.

        Args:
            input_data: Initial input data for the pipeline.
            providers: Optional mapping of model name -> ModelProvider.
            tool_registry: Optional ToolRegistry. Creates default if not provided.
            on_status_change: Optional callback for task status changes.
            on_before_iteration: Optional hook called before each agent iteration.
                Signature: (iteration: int, task: TaskDefinition) -> TaskDefinition | None
                Return a modified task to change permissions/goal/prompt mid-run,
                or None to keep unchanged.

        Returns:
            Final output from the pipeline execution.
        """
        from agentpipe.execution.engine import DAGExecutor
        from agentpipe.execution.recovery import RecoveryManager
        from agentpipe.execution.runner import TaskRunner
        from agentpipe.models.adapters import create_provider
        from agentpipe.tools.registry import create_default_registry

        # Build tool registry
        if tool_registry is None:
            tool_registry = create_default_registry(workspace=self.workspace)

        if providers is not None:
            # Backward compat: shared provider dict (not recommended)
            runner = TaskRunner(
                providers=providers,
                tool_registry=tool_registry,
                on_before_iteration=on_before_iteration,
            )
        else:
            # Preferred: each task gets its own fresh provider instance
            config_map = {c.name: c for c in self.model_configs}

            def _provider_factory(model_name: str):
                config = config_map.get(model_name)
                if config is None:
                    raise RuntimeError(f"No model config for '{model_name}'")
                return create_provider(config)

            runner = TaskRunner(
                tool_registry=tool_registry,
                on_before_iteration=on_before_iteration,
                provider_factory=_provider_factory,
            )

        recovery = RecoveryManager(runner)
        executor = DAGExecutor(runner, recovery, on_status_change=on_status_change)

        run = await executor.execute(self.pipeline, input_data)
        return run._final_output
