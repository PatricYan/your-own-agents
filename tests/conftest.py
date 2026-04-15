"""Shared test fixtures for agentpipe tests."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agentpipe.core.pipeline import Pipeline
from agentpipe.core.task import TaskDefinition
from agentpipe.execution.conversation import Message, ToolCall
from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason
from agentpipe.tools.base import ToolDefinition


class MockModelProvider(ModelProvider):
    """A mock model provider for testing that supports multi-turn and tool calls."""

    def __init__(
        self,
        responses: list[ModelResponse] | None = None,
        default_content: str = "mock response",
    ):
        self._responses = list(responses) if responses else []
        self._default_content = default_content
        self._call_index = 0
        self.call_log: list[dict] = []

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> ModelResponse:
        self.call_log.append(
            {
                "messages": [m.to_dict() for m in messages],
                "tools": [t.name for t in tools] if tools else [],
                "parameters": parameters,
            }
        )

        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
            self._call_index += 1
            return resp

        # Default: call submit_result with the default content
        return ModelResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_0",
                    name="submit_result",
                    arguments={"result": json.dumps({"text": self._default_content})},
                )
            ],
            stop_reason=StopReason.TOOL_USE,
        )


class FailingModelProvider(ModelProvider):
    """A model provider that fails a configurable number of times before succeeding."""

    def __init__(self, fail_count: int = 1, success_response: str = "recovered"):
        self._fail_count = fail_count
        self._attempts = 0
        self._success_response = success_response

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> ModelResponse:
        self._attempts += 1
        if self._attempts <= self._fail_count:
            raise RuntimeError(f"Simulated failure (attempt {self._attempts}/{self._fail_count})")
        return ModelResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_0",
                    name="submit_result",
                    arguments={"result": json.dumps({"text": self._success_response})},
                )
            ],
            stop_reason=StopReason.TOOL_USE,
        )


@pytest.fixture
def mock_provider():
    return MockModelProvider()


@pytest.fixture
def failing_provider():
    return FailingModelProvider(fail_count=1)


@pytest.fixture
def simple_pipeline():
    """A simple two-task pipeline using Airflow-style depends_on."""
    return Pipeline(
        name="test-pipeline",
        tasks=[
            TaskDefinition(
                name="task-1",
                goal="Process the input data and produce a summary",
                primary_model="test-model",
            ),
            TaskDefinition(
                name="task-2",
                goal="Take the summary and produce a final report",
                primary_model="test-model",
                depends_on=["task-1"],  # Airflow-style dependency
            ),
        ],
        execution_strategy="fail_fast",
    )


@pytest.fixture
def parallel_pipeline():
    """A pipeline with two parallel branches merging — Airflow-style depends_on."""
    return Pipeline(
        name="parallel-pipeline",
        tasks=[
            TaskDefinition(
                name="start", goal="Initialize the workflow", primary_model="test-model"
            ),
            TaskDefinition(
                name="branch-a",
                goal="Process branch A",
                primary_model="test-model",
                depends_on=["start"],
            ),
            TaskDefinition(
                name="branch-b",
                goal="Process branch B",
                primary_model="test-model",
                depends_on=["start"],
            ),
            TaskDefinition(
                name="merge",
                goal="Merge results from both branches",
                primary_model="test-model",
                depends_on=["branch-a", "branch-b"],
            ),
        ],
        execution_strategy="fail_fast",
    )
