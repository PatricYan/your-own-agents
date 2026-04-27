"""Agent — loads a pipeline and its models, then executes it."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

from agentpipe.core.pipeline import Pipeline
from agentpipe.models.registry import ModelConfig


class Agent(BaseModel):
    """Pipeline + model configs. Call execute() to run."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    pipeline: Pipeline
    model_configs: list[ModelConfig] = Field(default_factory=list)
    workspace: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Agent name must be non-empty")
        return v.strip()

    async def execute(
        self,
        input_data: dict[str, Any],
        providers: dict[str, Any] | None = None,
        tool_registry: Any | None = None,
        on_status_change=None,
        on_before_iteration=None,
        on_content=None,
        on_tool_call=None,
        on_iteration=None,
        on_permission_ask=None,
    ) -> dict[str, Any]:
        """Execute the pipeline. Each task gets its own model provider."""
        from agentpipe.execution.engine import DAGExecutor
        from agentpipe.execution.recovery import RecoveryManager
        from agentpipe.execution.runner import TaskRunner
        from agentpipe.models.adapters import create_provider
        from agentpipe.tools.registry import create_default_registry

        if tool_registry is None:
            tool_registry = create_default_registry(workspace=self.workspace)

        runner_kwargs = {
            "tool_registry": tool_registry,
            "on_before_iteration": on_before_iteration,
            "on_content": on_content,
            "on_tool_call": on_tool_call,
            "on_iteration": on_iteration,
            "on_permission_ask": on_permission_ask,
        }

        if providers is not None:
            runner = TaskRunner(providers=providers, **runner_kwargs)
        else:
            config_map = {c.name: c for c in self.model_configs}

            def _provider_factory(model_name: str):
                config = config_map.get(model_name)
                if config is None:
                    raise RuntimeError(
                        f"Model '{model_name}' not found. "
                        f"Available: {list(config_map.keys())}. "
                        f"Check 'models' in your pipeline YAML."
                    )
                return create_provider(config)

            runner = TaskRunner(provider_factory=_provider_factory, **runner_kwargs)

        recovery = RecoveryManager(runner)
        executor = DAGExecutor(runner, recovery, on_status_change=on_status_change)
        run = await executor.execute(self.pipeline, input_data)
        return run._final_output
