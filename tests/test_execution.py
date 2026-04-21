"""Unit tests for agentpipe.execution — agent loop, engine, recovery, state."""

import json

import pytest

from agentpipe.common import ToolCall
from agentpipe.core.condition import Condition, Edge
from agentpipe.core.constraint import Constraint
from agentpipe.core.pipeline import Pipeline
from agentpipe.core.task import Permissions, TaskDefinition
from agentpipe.execution.state import (
    InvalidTransitionError,
    RunStatus,
    TaskStatus,
    validate_run_transition,
    validate_task_transition,
)

# Reuse mock models from conftest
from tests.conftest import FailingModelProvider as FailNTimesModel
from tests.conftest import MockModelProvider as MockModel


class TestStateMachine:
    def test_valid_task_transitions(self):
        validate_task_transition(TaskStatus.PENDING, TaskStatus.RUNNING)
        validate_task_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED)
        validate_task_transition(TaskStatus.RUNNING, TaskStatus.FAILED)
        validate_task_transition(TaskStatus.FAILED, TaskStatus.RUNNING)

    def test_invalid_task_transition(self):
        with pytest.raises(InvalidTransitionError):
            validate_task_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)

    def test_valid_run_transitions(self):
        validate_run_transition(RunStatus.PENDING, RunStatus.RUNNING)
        validate_run_transition(RunStatus.RUNNING, RunStatus.COMPLETED)

    def test_invalid_run_transition(self):
        with pytest.raises(InvalidTransitionError):
            validate_run_transition(RunStatus.FAILED, RunStatus.RUNNING)


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_basic_loop(self):
        from agentpipe.execution.agent_loop import AgentLoop
        from agentpipe.tools.registry import create_default_registry

        task = TaskDefinition(name="t", goal="do something", primary_model="m")
        reg = create_default_registry()
        loop = AgentLoop(provider=MockModel(), tool_registry=reg)
        result = await loop.run(task, {"input": "test"})
        assert result.completed
        assert result.iterations >= 1

    @pytest.mark.asyncio
    async def test_permission_enforcement(self):
        """Model tries to call shell but permissions deny it."""
        from agentpipe.execution.agent_loop import AgentLoop
        from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason
        from agentpipe.tools.registry import create_default_registry

        class ShellAttemptModel(ModelProvider):
            _called = False

            async def chat(self, messages, tools=None, parameters=None):
                if not self._called:
                    self._called = True
                    return ModelResponse(
                        tool_calls=[
                            ToolCall(id="c1", name="shell", arguments={"command": "echo hack"})
                        ],
                        stop_reason=StopReason.TOOL_USE,
                    )
                return ModelResponse(
                    tool_calls=[
                        ToolCall(
                            id="c2",
                            name="submit_result",
                            arguments={"result": json.dumps({"text": "done"})},
                        )
                    ],
                    stop_reason=StopReason.TOOL_USE,
                )

        task = TaskDefinition(
            name="t",
            goal="do something",
            primary_model="m",
            permissions=Permissions({"*": "deny", "read": "allow"}),
        )
        reg = create_default_registry()
        loop = AgentLoop(provider=ShellAttemptModel(), tool_registry=reg)
        result = await loop.run(task, {})
        assert result.completed
        # Check shell was denied
        tool_msgs = [m for m in result.conversation.messages if m.role == "tool"]
        assert any("not permitted" in (m.content or "") for m in tool_msgs)

    @pytest.mark.asyncio
    async def test_max_iterations(self):
        from agentpipe.execution.agent_loop import AgentLoop
        from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason
        from agentpipe.tools.registry import create_default_registry

        class NeverFinishes(ModelProvider):
            async def chat(self, messages, tools=None, parameters=None):
                return ModelResponse(
                    tool_calls=[ToolCall(id="c0", name="file_read", arguments={"path": "x"})],
                    stop_reason=StopReason.TOOL_USE,
                )

        task = TaskDefinition(name="t", goal="g", primary_model="m", max_iterations=3)
        reg = create_default_registry()
        loop = AgentLoop(provider=NeverFinishes(), tool_registry=reg)
        result = await loop.run(task, {})
        assert not result.completed
        assert result.iterations == 3

    @pytest.mark.asyncio
    async def test_on_before_iteration_hook(self):
        from agentpipe.execution.agent_loop import AgentLoop
        from agentpipe.tools.registry import create_default_registry

        hook_calls = []

        def hook(iteration, task):
            hook_calls.append(iteration)
            return None

        task = TaskDefinition(name="t", goal="g", primary_model="m")
        reg = create_default_registry()
        loop = AgentLoop(provider=MockModel(), tool_registry=reg, on_before_iteration=hook)
        await loop.run(task, {})
        assert len(hook_calls) >= 1

    @pytest.mark.asyncio
    async def test_on_before_iteration_modifies_task(self):
        from agentpipe.execution.agent_loop import AgentLoop
        from agentpipe.tools.registry import create_default_registry

        def hook(iteration, task):
            if iteration == 0:
                return task.model_copy(update={"goal": "NEW GOAL"})
            return None

        task = TaskDefinition(name="t", goal="old goal", primary_model="m")
        reg = create_default_registry()
        loop = AgentLoop(provider=MockModel(), tool_registry=reg, on_before_iteration=hook)
        result = await loop.run(task, {})
        assert result.completed
        user_msgs = [m.content for m in result.conversation.messages if m.role == "user"]
        assert any("NEW GOAL" in (msg or "") for msg in user_msgs)


class TestDAGExecutor:
    @pytest.mark.asyncio
    async def test_sequential(self):
        from agentpipe.execution.engine import DAGExecutor
        from agentpipe.execution.recovery import RecoveryManager
        from agentpipe.execution.runner import TaskRunner
        from agentpipe.tools.registry import create_default_registry

        p = Pipeline(
            name="seq",
            tasks=[
                TaskDefinition(name="a", goal="A", primary_model="m"),
                TaskDefinition(name="b", goal="B", primary_model="m", depends_on="a"),
            ],
        )
        reg = create_default_registry()
        runner = TaskRunner({"m": MockModel()}, reg)
        executor = DAGExecutor(runner, RecoveryManager(runner))
        run = await executor.execute(p, {"input": "test"})
        assert run.status.value == "completed"

    @pytest.mark.asyncio
    async def test_parallel(self):
        from agentpipe.execution.engine import DAGExecutor
        from agentpipe.execution.recovery import RecoveryManager
        from agentpipe.execution.runner import TaskRunner
        from agentpipe.tools.registry import create_default_registry

        p = Pipeline(
            name="par",
            tasks=[
                TaskDefinition(name="s", goal="S", primary_model="m"),
                TaskDefinition(name="l", goal="L", primary_model="m", depends_on="s"),
                TaskDefinition(name="r", goal="R", primary_model="m", depends_on="s"),
                TaskDefinition(name="e", goal="E", primary_model="m", depends_on=["l", "r"]),
            ],
        )
        reg = create_default_registry()
        runner = TaskRunner({"m": MockModel()}, reg)
        executor = DAGExecutor(runner, RecoveryManager(runner))
        run = await executor.execute(p, {})
        assert run.status.value == "completed"
        for name in ["s", "l", "r", "e"]:
            assert run.task_records[name].status.value == "completed"

    @pytest.mark.asyncio
    async def test_condition_routing(self):
        from agentpipe.execution.engine import DAGExecutor
        from agentpipe.execution.recovery import RecoveryManager
        from agentpipe.execution.runner import TaskRunner
        from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason
        from agentpipe.tools.registry import create_default_registry

        class EvalModel(ModelProvider):
            async def chat(self, messages, tools=None, parameters=None):
                return ModelResponse(
                    tool_calls=[
                        ToolCall(
                            id="c0",
                            name="submit_result",
                            arguments={
                                "result": json.dumps({"quality_score": 0.9, "text": "good"})
                            },
                        )
                    ],
                    stop_reason=StopReason.TOOL_USE,
                )

        p = Pipeline(
            name="cond",
            tasks=[
                TaskDefinition(name="eval", goal="Evaluate", primary_model="m"),
                TaskDefinition(name="publish", goal="Publish", primary_model="m"),
                TaskDefinition(name="improve", goal="Improve", primary_model="m"),
            ],
            edges=[
                Edge(
                    upstream="eval",
                    downstream="publish",
                    condition=Condition(expression="quality_score > 0.8"),
                ),
                Edge(
                    upstream="eval",
                    downstream="improve",
                    condition=Condition(expression="quality_score <= 0.8"),
                ),
            ],
        )
        reg = create_default_registry()
        runner = TaskRunner({"m": EvalModel()}, reg)
        executor = DAGExecutor(runner, RecoveryManager(runner))
        run = await executor.execute(p, {})
        assert run.task_records["publish"].status.value == "completed"
        assert run.task_records["improve"].status.value == "skipped"


class TestRecovery:
    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        from agentpipe.execution.engine import DAGExecutor
        from agentpipe.execution.recovery import RecoveryManager
        from agentpipe.execution.runner import TaskRunner
        from agentpipe.tools.registry import create_default_registry

        p = Pipeline(
            name="retry",
            tasks=[
                TaskDefinition(
                    name="flaky",
                    goal="Flaky task",
                    primary_model="m",
                    constraints=[Constraint(type="max_retries", value=2, on_violation="fail")],
                ),
            ],
        )
        reg = create_default_registry()
        runner = TaskRunner({"m": FailNTimesModel(fail_count=1)}, reg)
        executor = DAGExecutor(runner, RecoveryManager(runner))
        run = await executor.execute(p, {})
        assert run.status.value == "completed"
