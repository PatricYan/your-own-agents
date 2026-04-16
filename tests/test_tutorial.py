"""
Tutorial Test Suite: AgentPipe
==============================

This test file validates every major feature of AgentPipe.
Run with:  pytest tests/test_tutorial.py -v

Sections:
  1. Tools          — all 10 built-in tools work
  2. Permissions     — allow/ask/deny enforcement
  3. Dependencies    — Airflow-style depends_on (1 or many)
  4. Agent Loop      — think-act-observe cycle, submit_result, max_iterations
  5. Pipeline Engine — DAG execution, condition routing, parallel branches
  6. Human-in-Loop   — on_before_iteration hook modifies task mid-run
  7. Recovery        — retry, fallback model
  8. YAML Loader     — load pipeline from YAML with permissions + depends_on
  9. Storage         — definitions store + history store
  10. CLI             — argument parsing
"""

from __future__ import annotations

import json

import pytest

# ============================================================
# Shared mock model provider
# ============================================================
from agentpipe.execution.conversation import Message, ToolCall
from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason


class MockModel(ModelProvider):
    """A mock model that calls submit_result on the first opportunity."""

    def __init__(self, responses: list[ModelResponse] | None = None):
        self._responses = list(responses) if responses else []
        self._call_count = 0

    async def chat(self, messages, tools=None, parameters=None):
        self._call_count += 1
        if self._call_count <= len(self._responses):
            return self._responses[self._call_count - 1]
        # Default: call submit_result
        return ModelResponse(
            tool_calls=[
                ToolCall(
                    id="c0",
                    name="submit_result",
                    arguments={"result": json.dumps({"text": "mock output"})},
                )
            ],
            stop_reason=StopReason.TOOL_USE,
        )


class FailNTimesModel(ModelProvider):
    """Fails N times then succeeds."""

    def __init__(self, fail_count=1):
        self._fail_count = fail_count
        self._attempts = 0

    async def chat(self, messages, tools=None, parameters=None):
        self._attempts += 1
        if self._attempts <= self._fail_count:
            raise RuntimeError(f"fail #{self._attempts}")
        return ModelResponse(
            tool_calls=[
                ToolCall(
                    id="c0",
                    name="submit_result",
                    arguments={"result": json.dumps({"text": "recovered"})},
                )
            ],
            stop_reason=StopReason.TOOL_USE,
        )


# ============================================================
# 1. TOOLS — all 10 built-in tools
# ============================================================


class TestTools:
    """Test that every built-in tool can be instantiated and executed."""

    def test_registry_has_all_10_tools(self):
        from agentpipe.tools.registry import create_default_registry

        reg = create_default_registry()
        tools = sorted(reg.list_tools())
        assert tools == [
            "edit",
            "file_delete",
            "file_read",
            "file_write",
            "glob",
            "grep",
            "list",
            "shell",
            "submit_result",
            "web_fetch",
        ]

    @pytest.mark.asyncio
    async def test_file_read(self, tmp_path):
        from agentpipe.tools.builtin.file_read import FileReadTool

        f = tmp_path / "hello.txt"
        f.write_text("line1\nline2\nline3\n")
        tool = FileReadTool(base_dir=str(tmp_path))
        result = await tool.execute(path="hello.txt")
        assert "line1" in result
        assert "line3" in result

    @pytest.mark.asyncio
    async def test_file_read_offset_limit(self, tmp_path):
        from agentpipe.tools.builtin.file_read import FileReadTool

        f = tmp_path / "data.txt"
        f.write_text("a\nb\nc\nd\ne\n")
        tool = FileReadTool(base_dir=str(tmp_path))
        result = await tool.execute(path="data.txt", offset=2, limit=2)
        assert "b" in result
        assert "c" in result
        assert "a" not in result

    @pytest.mark.asyncio
    async def test_file_write(self, tmp_path):
        from agentpipe.tools.builtin.file_write import FileWriteTool

        tool = FileWriteTool(base_dir=str(tmp_path))
        result = await tool.execute(path="out.txt", content="hello world")
        assert "Successfully" in result
        assert (tmp_path / "out.txt").read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_edit(self, tmp_path):
        from agentpipe.tools.builtin.edit import EditTool

        f = tmp_path / "code.py"
        f.write_text("def foo():\n    return 1\n")
        tool = EditTool(base_dir=str(tmp_path))
        result = await tool.execute(
            file_path="code.py", old_string="return 1", new_string="return 42"
        )
        assert "Successfully" in result
        assert "return 42" in f.read_text()

    @pytest.mark.asyncio
    async def test_edit_not_found(self, tmp_path):
        from agentpipe.tools.builtin.edit import EditTool

        f = tmp_path / "code.py"
        f.write_text("hello")
        tool = EditTool(base_dir=str(tmp_path))
        result = await tool.execute(file_path="code.py", old_string="xyz", new_string="abc")
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_file_delete(self, tmp_path):
        from agentpipe.tools.builtin.file_delete import FileDeleteTool

        f = tmp_path / "remove_me.txt"
        f.write_text("bye")
        tool = FileDeleteTool(base_dir=str(tmp_path))
        result = await tool.execute(path="remove_me.txt")
        assert "Successfully" in result
        assert not f.exists()

    @pytest.mark.asyncio
    async def test_shell(self):
        from agentpipe.tools.builtin.shell import ShellTool

        tool = ShellTool()
        result = await tool.execute(command="echo hello_from_shell")
        assert "hello_from_shell" in result

    @pytest.mark.asyncio
    async def test_glob(self, tmp_path):
        from agentpipe.tools.builtin.glob import GlobTool

        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.txt").write_text("")
        tool = GlobTool(base_dir=str(tmp_path))
        result = await tool.execute(pattern="*.py")
        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result

    @pytest.mark.asyncio
    async def test_grep(self, tmp_path):
        from agentpipe.tools.builtin.grep import GrepTool

        (tmp_path / "test.py").write_text("def hello():\n    pass\ndef world():\n    pass\n")
        tool = GrepTool(base_dir=str(tmp_path))
        result = await tool.execute(pattern="def .*world")
        assert "world" in result
        assert "hello" not in result.split("\n")[-1]  # Only world line matched

    @pytest.mark.asyncio
    async def test_list_dir(self, tmp_path):
        from agentpipe.tools.builtin.list_dir import ListDirTool

        (tmp_path / "file.txt").write_text("")
        (tmp_path / "subdir").mkdir()
        tool = ListDirTool(base_dir=str(tmp_path))
        result = await tool.execute()
        assert "subdir/" in result
        assert "file.txt" in result

    @pytest.mark.asyncio
    async def test_submit_result(self):
        from agentpipe.tools.builtin.submit_result import SubmitResultTool

        tool = SubmitResultTool()
        tool.reset()
        assert tool.last_result is None
        result = await tool.execute(result='{"answer": 42}')
        assert "successfully" in result.lower()
        assert tool.last_result == '{"answer": 42}'


# ============================================================
# 2. PERMISSIONS — allow/ask/deny model
# ============================================================


class TestPermissions:
    """Test the OpenCode-style permission model."""

    def test_default_permissions(self):
        from agentpipe.core.task import Permissions

        p = Permissions()
        assert p.allows("file_read")  # read=allow by default
        assert p.allows("glob")  # glob=allow by default
        assert not p.allows("edit")  # edit=deny by default
        assert not p.allows("shell")  # bash=deny by default
        assert not p.allows("web_fetch")  # deny
        assert p.allows("submit_result")  # always on

    def test_custom_permissions(self):
        from agentpipe.core.task import Permissions

        p = Permissions({"edit": "allow", "bash": "ask"})
        assert p.allows("edit")
        assert p.allows("shell")  # ask counts as allowed
        assert not p.is_denied("shell")
        assert p.allows("file_write")  # edit covers file_write

    def test_denied_tools(self):
        from agentpipe.core.task import Permissions

        p = Permissions({"read": "deny", "bash": "deny"})
        assert p.is_denied("file_read")
        assert p.is_denied("shell")
        assert not p.allows("file_read")

    def test_allowed_tool_names(self):
        from agentpipe.core.task import Permissions

        p = Permissions({"edit": "allow", "bash": "allow"})
        names = p.allowed_tool_names()
        assert "file_read" in names  # default allow
        assert "edit" in names
        assert "shell" in names
        assert "file_write" in names  # edit=allow covers file_write

    def test_unknown_tool_uses_default(self):
        from agentpipe.core.task import Permissions

        p = Permissions({"*": "deny"})
        assert p.is_denied("some_unknown_tool")

    def test_effective_tools_from_permissions(self):
        from agentpipe.core.task import Permissions, TaskDefinition

        t = TaskDefinition(
            name="t",
            goal="g",
            primary_model="m",
            permissions=Permissions({"read": "allow", "edit": "allow", "bash": "deny"}),
        )
        eff = t.effective_tools()
        assert "file_read" in eff
        assert "edit" in eff
        assert "shell" not in eff

    def test_explicit_tools_override_permissions(self):
        from agentpipe.core.task import Permissions, TaskDefinition

        t = TaskDefinition(
            name="t",
            goal="g",
            primary_model="m",
            permissions=Permissions({"bash": "deny"}),
            tools=["shell", "web_fetch"],
        )
        assert t.effective_tools() == ["shell", "web_fetch"]


# ============================================================
# 3. DEPENDENCIES — Airflow-style depends_on
# ============================================================


class TestDependencies:
    """Test that depends_on works with 1 or more dependencies."""

    def test_single_string_dependency(self):
        from agentpipe.core.task import TaskDefinition

        t = TaskDefinition(name="b", goal="g", primary_model="m", depends_on="a")
        assert t.depends_on == ["a"]

    def test_list_dependency(self):
        from agentpipe.core.task import TaskDefinition

        t = TaskDefinition(name="d", goal="g", primary_model="m", depends_on=["b", "c"])
        assert t.depends_on == ["b", "c"]

    def test_empty_dependency(self):
        from agentpipe.core.task import TaskDefinition

        t = TaskDefinition(name="a", goal="g", primary_model="m")
        assert t.depends_on == []

    def test_pipeline_generates_edges_from_depends_on(self):
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition

        p = Pipeline(
            name="test",
            tasks=[
                TaskDefinition(name="a", goal="A", primary_model="m"),
                TaskDefinition(name="b", goal="B", primary_model="m", depends_on="a"),
                TaskDefinition(name="c", goal="C", primary_model="m", depends_on="a"),
                TaskDefinition(name="d", goal="D", primary_model="m", depends_on=["b", "c"]),
            ],
        )
        assert len(p.edges) == 4
        assert p.get_upstream_tasks("b") == ["a"]
        assert p.get_upstream_tasks("c") == ["a"]
        assert sorted(p.get_upstream_tasks("d")) == ["b", "c"]

    def test_topological_sort_respects_depends_on(self):
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition

        p = Pipeline(
            name="test",
            tasks=[
                TaskDefinition(name="a", goal="A", primary_model="m"),
                TaskDefinition(name="b", goal="B", primary_model="m", depends_on="a"),
                TaskDefinition(name="c", goal="C", primary_model="m", depends_on="a"),
                TaskDefinition(name="d", goal="D", primary_model="m", depends_on=["b", "c"]),
            ],
        )
        levels = p.topological_sort()
        assert levels[0] == ["a"]
        assert sorted(levels[1]) == ["b", "c"]
        assert levels[2] == ["d"]

    def test_cycle_detection(self):
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition

        with pytest.raises(ValueError, match="cycle"):
            Pipeline(
                name="cycle",
                tasks=[
                    TaskDefinition(name="a", goal="A", primary_model="m", depends_on="b"),
                    TaskDefinition(name="b", goal="B", primary_model="m", depends_on="a"),
                ],
            )

    def test_depends_on_invalid_reference(self):
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition

        with pytest.raises(ValueError, match="not in the pipeline"):
            Pipeline(
                name="bad",
                tasks=[
                    TaskDefinition(name="a", goal="A", primary_model="m", depends_on="nonexistent"),
                ],
            )

    def test_mixed_depends_on_and_explicit_edges(self):
        from agentpipe.core.condition import Condition, Edge
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition

        p = Pipeline(
            name="mixed",
            tasks=[
                TaskDefinition(name="a", goal="A", primary_model="m"),
                TaskDefinition(name="b", goal="B", primary_model="m", depends_on="a"),
                TaskDefinition(name="c", goal="C", primary_model="m"),
            ],
            edges=[
                Edge(
                    source_task="a", target_task="c", condition=Condition(expression="score > 0.5")
                ),
            ],
        )
        assert len(p.edges) == 2  # 1 from depends_on + 1 explicit


# ============================================================
# 4. AGENT LOOP — think-act-observe cycle
# ============================================================


class TestAgentLoop:
    """Test the agent loop execution."""

    @pytest.mark.asyncio
    async def test_basic_loop_with_submit_result(self):
        from agentpipe.core.task import TaskDefinition
        from agentpipe.execution.agent_loop import AgentLoop
        from agentpipe.tools.registry import create_default_registry

        task = TaskDefinition(name="t", goal="Do something", primary_model="m")
        reg = create_default_registry()
        loop = AgentLoop(provider=MockModel(), tool_registry=reg)
        result = await loop.run(task, {"input": "test"})

        assert result.completed
        assert result.output.get("text") == "mock output"
        assert result.iterations >= 1

    @pytest.mark.asyncio
    async def test_tool_permission_enforcement(self):
        """Model tries to call shell but permissions deny it."""
        from agentpipe.core.task import Permissions, TaskDefinition
        from agentpipe.execution.agent_loop import AgentLoop
        from agentpipe.tools.registry import create_default_registry

        # Model first tries shell, then submits result
        model = MockModel(
            responses=[
                ModelResponse(
                    tool_calls=[
                        ToolCall(id="c1", name="shell", arguments={"command": "echo hack"})
                    ],
                    stop_reason=StopReason.TOOL_USE,
                ),
            ]
        )
        task = TaskDefinition(
            name="t",
            goal="Do something",
            primary_model="m",
            permissions=Permissions({"bash": "deny"}),
        )
        reg = create_default_registry()
        loop = AgentLoop(provider=model, tool_registry=reg)
        result = await loop.run(task, {})

        # Should complete (after shell is denied, default response calls submit_result)
        assert result.completed
        # Check that shell was denied in the conversation
        tool_results = [m for m in result.conversation.messages if m.role == "tool"]
        denied = any("not permitted" in (m.content or "") for m in tool_results)
        assert denied, "Shell tool call should have been denied"

    @pytest.mark.asyncio
    async def test_max_iterations_limit(self):
        """Agent that never submits hits the iteration limit."""
        from agentpipe.core.task import TaskDefinition
        from agentpipe.execution.agent_loop import AgentLoop
        from agentpipe.tools.registry import create_default_registry

        # Model always returns content (never calls submit_result)
        class NeverFinishes(ModelProvider):
            async def chat(self, messages, tools=None, parameters=None):
                return ModelResponse(
                    tool_calls=[
                        ToolCall(id="c0", name="file_read", arguments={"path": "/dev/null"})
                    ],
                    stop_reason=StopReason.TOOL_USE,
                )

        task = TaskDefinition(name="t", goal="g", primary_model="m", max_iterations=3)
        reg = create_default_registry()
        loop = AgentLoop(provider=NeverFinishes(), tool_registry=reg)
        result = await loop.run(task, {})

        assert not result.completed
        assert result.iterations == 3
        assert "Max iterations" in (result.error or "")


# ============================================================
# 5. PIPELINE ENGINE — DAG execution
# ============================================================


class TestPipelineEngine:
    """Test the DAG executor with real agent loops."""

    @pytest.mark.asyncio
    async def test_sequential_pipeline(self):
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition
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
        providers = {"m": MockModel()}
        reg = create_default_registry()
        runner = TaskRunner(providers, reg)
        recovery = RecoveryManager(runner)
        executor = DAGExecutor(runner, recovery)

        run = await executor.execute(p, {"input": "test"})
        assert run.status.value == "completed"
        assert run.task_records["a"].status.value == "completed"
        assert run.task_records["b"].status.value == "completed"

    @pytest.mark.asyncio
    async def test_parallel_pipeline(self):
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition
        from agentpipe.execution.engine import DAGExecutor
        from agentpipe.execution.recovery import RecoveryManager
        from agentpipe.execution.runner import TaskRunner
        from agentpipe.tools.registry import create_default_registry

        p = Pipeline(
            name="par",
            tasks=[
                TaskDefinition(name="start", goal="Start", primary_model="m"),
                TaskDefinition(name="left", goal="Left", primary_model="m", depends_on="start"),
                TaskDefinition(name="right", goal="Right", primary_model="m", depends_on="start"),
                TaskDefinition(
                    name="end", goal="End", primary_model="m", depends_on=["left", "right"]
                ),
            ],
        )
        providers = {"m": MockModel()}
        reg = create_default_registry()
        runner = TaskRunner(providers, reg)
        recovery = RecoveryManager(runner)
        executor = DAGExecutor(runner, recovery)

        run = await executor.execute(p, {})
        assert run.status.value == "completed"
        for name in ["start", "left", "right", "end"]:
            assert run.task_records[name].status.value == "completed"

    @pytest.mark.asyncio
    async def test_condition_routing(self):
        """Test conditional branching: evaluate → publish OR improve."""
        from agentpipe.core.condition import Condition, Edge
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition
        from agentpipe.execution.engine import DAGExecutor
        from agentpipe.execution.recovery import RecoveryManager
        from agentpipe.execution.runner import TaskRunner
        from agentpipe.tools.registry import create_default_registry

        # Evaluate returns quality_score=0.9 → should route to publish
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
                TaskDefinition(name="evaluate", goal="Evaluate", primary_model="m"),
                TaskDefinition(name="publish", goal="Publish", primary_model="m"),
                TaskDefinition(name="improve", goal="Improve", primary_model="m"),
            ],
            edges=[
                Edge(
                    source_task="evaluate",
                    target_task="publish",
                    condition=Condition(expression="quality_score > 0.8"),
                ),
                Edge(
                    source_task="evaluate",
                    target_task="improve",
                    condition=Condition(expression="quality_score <= 0.8"),
                ),
            ],
        )
        providers = {"m": EvalModel()}
        reg = create_default_registry()
        runner = TaskRunner(providers, reg)
        recovery = RecoveryManager(runner)
        executor = DAGExecutor(runner, recovery)

        run = await executor.execute(p, {})
        assert run.status.value == "completed"
        assert run.task_records["evaluate"].status.value == "completed"
        assert run.task_records["publish"].status.value == "completed"
        assert run.task_records["improve"].status.value == "skipped"


# ============================================================
# 6. HUMAN-IN-THE-LOOP — on_before_iteration hook
# ============================================================


class TestHumanInLoop:
    """Test that the on_before_iteration hook can modify tasks mid-run."""

    @pytest.mark.asyncio
    async def test_update_permissions_mid_run(self):
        from agentpipe.core.task import Permissions, TaskDefinition
        from agentpipe.execution.agent_loop import AgentLoop
        from agentpipe.tools.registry import create_default_registry

        hook_calls = []

        def hook(iteration, task):
            hook_calls.append(iteration)
            if iteration == 0:
                # Grant bash on first iteration
                return task.model_copy(
                    update={
                        "permissions": Permissions({"read": "allow", "bash": "allow"}),
                    }
                )
            return None

        task = TaskDefinition(
            name="t",
            goal="g",
            primary_model="m",
            permissions=Permissions({"bash": "deny"}),
        )
        reg = create_default_registry()
        loop = AgentLoop(provider=MockModel(), tool_registry=reg, on_before_iteration=hook)
        result = await loop.run(task, {})

        assert result.completed
        assert len(hook_calls) >= 1

    @pytest.mark.asyncio
    async def test_update_goal_mid_run(self):
        from agentpipe.core.task import TaskDefinition
        from agentpipe.execution.agent_loop import AgentLoop
        from agentpipe.tools.registry import create_default_registry

        def hook(iteration, task):
            if iteration == 0:
                return task.model_copy(update={"goal": "New goal!"})
            return None

        task = TaskDefinition(name="t", goal="Old goal", primary_model="m")
        reg = create_default_registry()
        loop = AgentLoop(provider=MockModel(), tool_registry=reg, on_before_iteration=hook)
        result = await loop.run(task, {})

        assert result.completed
        # Check that the updated goal message was injected
        user_msgs = [m.content for m in result.conversation.messages if m.role == "user"]
        assert any("New goal" in (msg or "") for msg in user_msgs)

    @pytest.mark.asyncio
    async def test_hook_wired_through_agent_execute(self):
        """Test that on_before_iteration works through Agent.execute()."""
        from agentpipe.core.agent import Agent
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition
        from agentpipe.models.registry import ModelConfig
        from agentpipe.tools.registry import create_default_registry

        hook_fired = []

        def hook(iteration, task):
            hook_fired.append(task.name)
            return None

        p = Pipeline(
            name="test",
            tasks=[TaskDefinition(name="t", goal="g", primary_model="m")],
        )
        agent = Agent(
            name="a",
            pipeline=p,
            model_configs=[ModelConfig(name="m", provider="http", connection={"base_url": "x"})],
        )
        providers = {"m": MockModel()}
        reg = create_default_registry()
        await agent.execute(
            {"input": "x"},
            providers=providers,
            tool_registry=reg,
            on_before_iteration=hook,
        )
        assert len(hook_fired) > 0


# ============================================================
# 7. RECOVERY — retry + fallback
# ============================================================


class TestRecovery:
    """Test the recovery cascade."""

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        from agentpipe.core.constraint import Constraint
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition
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
        providers = {"m": FailNTimesModel(fail_count=1)}
        reg = create_default_registry()
        runner = TaskRunner(providers, reg)
        recovery = RecoveryManager(runner)
        executor = DAGExecutor(runner, recovery)

        run = await executor.execute(p, {})
        assert run.status.value == "completed"


# ============================================================
# 8. YAML LOADER — permissions + depends_on parsing
# ============================================================


class TestYamlLoader:
    """Test loading pipelines from YAML."""

    def test_load_pipeline_with_depends_on_and_permissions(self, tmp_path):
        from agentpipe.loader.yaml_loader import load_pipeline_from_yaml

        yaml_content = """
name: test-pipeline
execution_strategy: fail_fast

tasks:
  - name: reader
    goal: "Read files"
    primary_model: gpt-4o
    permissions:
      read: allow
      edit: deny
      bash: deny

  - name: writer
    goal: "Write output"
    primary_model: gpt-4o
    permissions:
      read: allow
      edit: allow
      write: allow
      bash: ask
    depends_on: reader

  - name: tester
    goal: "Run tests"
    primary_model: gpt-4o
    permissions:
      read: allow
      bash: allow
    depends_on:
      - writer
"""
        f = tmp_path / "pipeline.yaml"
        f.write_text(yaml_content)
        p = load_pipeline_from_yaml(f)

        assert p.name == "test-pipeline"
        assert len(p.tasks) == 3
        assert len(p.edges) == 2  # reader→writer + writer→tester

        reader = p.get_task("reader")
        assert reader.permissions.is_denied("edit")
        assert reader.permissions.allows("file_read")

        writer = p.get_task("writer")
        assert writer.permissions.allows("edit")
        assert writer.permissions.needs_approval("shell")
        assert writer.depends_on == ["reader"]

        tester = p.get_task("tester")
        assert tester.permissions.allows("shell")
        assert tester.depends_on == ["writer"]

    def test_load_pipeline_with_single_string_depends_on(self, tmp_path):
        from agentpipe.loader.yaml_loader import load_pipeline_from_yaml

        yaml_content = """
name: single-dep
tasks:
  - name: a
    goal: A
    primary_model: m
  - name: b
    goal: B
    primary_model: m
    depends_on: a
"""
        f = tmp_path / "p.yaml"
        f.write_text(yaml_content)
        p = load_pipeline_from_yaml(f)
        assert p.get_task("b").depends_on == ["a"]
        assert len(p.edges) == 1


# ============================================================
# 9. STORAGE — definitions + history
# ============================================================


class TestStorage:
    """Test file-based storage and SQLite history."""

    def test_definition_store_crud(self, tmp_path):
        from agentpipe.storage.definitions import DefinitionStore

        store = DefinitionStore(tmp_path)
        store.save_agent("test-agent", {"name": "test", "pipeline": {}})
        assert "test-agent" in store.list_agents()

        data = store.load_agent("test-agent")
        assert data["name"] == "test"

        store.delete_agent("test-agent")
        assert "test-agent" not in store.list_agents()

    def test_model_store_crud(self, tmp_path):
        from agentpipe.storage.definitions import DefinitionStore

        store = DefinitionStore(tmp_path)
        store.save_model("gpt4", {"name": "gpt4", "provider": "openai"})
        assert "gpt4" in store.list_models()
        store.delete_model("gpt4")
        assert "gpt4" not in store.list_models()

    def test_history_store(self, tmp_path):
        from agentpipe.storage.history import HistoryStore

        store = HistoryStore(tmp_path)
        store.save_run({"id": "run-1", "pipeline_name": "test", "status": "completed"})
        run = store.get_run("run-1")
        assert run is not None
        assert run["status"] == "completed"

        runs = store.list_runs()
        assert len(runs) == 1


# ============================================================
# 10. CLI — argument parsing
# ============================================================


class TestCLI:
    """Test CLI argument parsing."""

    def test_run_parser(self):
        from agentpipe.cli.main import build_parser

        parser = build_parser()
        args = parser.parse_args(
            ["run", "my-agent", "--input", '{"x": 1}', "--watch", "--interactive"]
        )
        assert args.agent_name == "my-agent"
        assert args.input_data == '{"x": 1}'
        assert args.watch is True
        assert args.interactive is True

    def test_models_register_parser(self):
        from agentpipe.cli.main import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "models",
                "register",
                "gpt-4o",
                "--provider",
                "openai",
                "--connection",
                '{"api_key_env": "KEY"}',
            ]
        )
        assert args.name == "gpt-4o"
        assert args.provider == "openai"

    def test_pipelines_validate_parser(self):
        from agentpipe.cli.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["pipelines", "validate", "my-pipeline.yaml"])
        assert args.path == "my-pipeline.yaml"

    def test_version(self, capsys):
        from agentpipe.cli.main import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit, match="0"):
            parser.parse_args(["--version"])


# ============================================================
# 11. CONVERSATION MODEL
# ============================================================


class TestConversation:
    """Test conversation data model."""

    def test_message_serialization(self):
        from agentpipe.execution.conversation import ToolCall

        msg = Message(
            role="assistant",
            content="hello",
            tool_calls=[ToolCall(id="c1", name="shell", arguments={"command": "ls"})],
        )
        d = msg.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "hello"
        assert len(d["tool_calls"]) == 1
        assert d["tool_calls"][0]["name"] == "shell"

    def test_conversation_flow(self):
        from agentpipe.execution.conversation import Conversation

        c = Conversation()
        c.add_system("You are an agent")
        c.add_user("Do something")
        c.add_assistant(content="I'll use a tool")
        c.add_tool_result("c1", "tool output")

        msgs = c.to_list()
        assert len(msgs) == 4
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"
        assert msgs[3]["role"] == "tool"


# ============================================================
# 12. STATE MACHINE
# ============================================================


class TestStateMachine:
    """Test task and run state transitions."""

    def test_valid_task_transitions(self):
        from agentpipe.execution.state import TaskStatus, validate_task_transition

        validate_task_transition(TaskStatus.PENDING, TaskStatus.RUNNING)
        validate_task_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED)
        validate_task_transition(TaskStatus.RUNNING, TaskStatus.FAILED)
        validate_task_transition(TaskStatus.FAILED, TaskStatus.RUNNING)  # retry

    def test_invalid_task_transition(self):
        from agentpipe.execution.state import (
            InvalidTransitionError,
            TaskStatus,
            validate_task_transition,
        )

        with pytest.raises(InvalidTransitionError):
            validate_task_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)

    def test_valid_run_transitions(self):
        from agentpipe.execution.state import RunStatus, validate_run_transition

        validate_run_transition(RunStatus.PENDING, RunStatus.RUNNING)
        validate_run_transition(RunStatus.RUNNING, RunStatus.COMPLETED)
        validate_run_transition(RunStatus.RUNNING, RunStatus.FAILED)

    def test_invalid_run_transition(self):
        from agentpipe.execution.state import (
            InvalidTransitionError,
            RunStatus,
            validate_run_transition,
        )

        with pytest.raises(InvalidTransitionError):
            validate_run_transition(RunStatus.FAILED, RunStatus.RUNNING)


# ============================================================
# 13. DAG VISUALIZATION
# ============================================================


class TestDAGVisualization:
    """Test pipeline DAG rendering."""

    def test_ascii_dag_sequential(self):
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition

        p = Pipeline(
            name="seq",
            tasks=[
                TaskDefinition(name="a", goal="A", primary_model="m1"),
                TaskDefinition(name="b", goal="B", primary_model="m2", depends_on="a"),
            ],
        )
        output = p.render_dag("ascii")
        assert "Pipeline: seq" in output
        assert "a (m1)" in output
        assert "b (m2)" in output
        assert "a --> b" in output

    def test_ascii_dag_parallel_branches(self):
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition

        p = Pipeline(
            name="par",
            tasks=[
                TaskDefinition(name="start", goal="S", primary_model="m"),
                TaskDefinition(name="left", goal="L", primary_model="m", depends_on="start"),
                TaskDefinition(name="right", goal="R", primary_model="m", depends_on="start"),
                TaskDefinition(
                    name="end", goal="E", primary_model="m", depends_on=["left", "right"]
                ),
            ],
        )
        output = p.render_dag("ascii")
        assert "start --> left" in output
        assert "start --> right" in output
        assert "left --> end" in output
        assert "right --> end" in output

    def test_ascii_dag_shows_conditions(self):
        from agentpipe.core.condition import Condition, Edge
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition

        p = Pipeline(
            name="cond",
            tasks=[
                TaskDefinition(name="eval", goal="E", primary_model="m"),
                TaskDefinition(name="good", goal="G", primary_model="m"),
                TaskDefinition(name="bad", goal="B", primary_model="m"),
            ],
            edges=[
                Edge(
                    source_task="eval",
                    target_task="good",
                    condition=Condition(expression="score > 0.8"),
                ),
                Edge(
                    source_task="eval",
                    target_task="bad",
                    condition=Condition(expression="score <= 0.8"),
                ),
            ],
        )
        output = p.render_dag("ascii")
        assert "[if score > 0.8]" in output
        assert "[if score <= 0.8]" in output

    def test_ascii_dag_shows_task_details(self):
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import Permissions, TaskDefinition

        p = Pipeline(
            name="detail",
            tasks=[
                TaskDefinition(
                    name="worker",
                    goal="Work",
                    primary_model="gpt-4o",
                    permissions=Permissions({"read": "allow", "edit": "allow", "bash": "deny"}),
                    max_iterations=15,
                ),
            ],
        )
        output = p.render_dag("ascii")
        assert "perms=" in output
        assert "max_iter=15" in output
        assert "model=gpt-4o" in output

    def test_mermaid_dag(self):
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition

        p = Pipeline(
            name="merm",
            tasks=[
                TaskDefinition(name="a", goal="A", primary_model="m"),
                TaskDefinition(name="b", goal="B", primary_model="m", depends_on="a"),
            ],
        )
        output = p.render_dag("mermaid")
        assert output.startswith("graph TD")
        assert "a --> b" in output

    def test_mermaid_dag_with_conditions(self):
        from agentpipe.core.condition import Condition, Edge
        from agentpipe.core.pipeline import Pipeline
        from agentpipe.core.task import TaskDefinition

        p = Pipeline(
            name="cond-merm",
            tasks=[
                TaskDefinition(name="x", goal="X", primary_model="m"),
                TaskDefinition(name="y", goal="Y", primary_model="m"),
            ],
            edges=[
                Edge(source_task="x", target_task="y", condition=Condition(expression="ok == True"))
            ],
        )
        output = p.render_dag("mermaid")
        assert '-->|"ok == True"|' in output

    def test_cli_dag_command(self, tmp_path):
        """Test the CLI pipelines dag command."""
        yaml_content = """
name: cli-test
tasks:
  - name: a
    goal: A
    primary_model: m
  - name: b
    goal: B
    primary_model: m
    depends_on: a
"""
        f = tmp_path / "p.yaml"
        f.write_text(yaml_content)

        from agentpipe.cli.main import main

        # ASCII
        exit_code = main(["pipelines", "dag", str(f)])
        assert exit_code == 0

    def test_cli_dag_mermaid(self, tmp_path):
        yaml_content = """
name: merm-test
tasks:
  - name: x
    goal: X
    primary_model: m
  - name: y
    goal: Y
    primary_model: m
    depends_on: x
"""
        f = tmp_path / "p.yaml"
        f.write_text(yaml_content)

        from agentpipe.cli.main import main

        exit_code = main(["pipelines", "dag", str(f), "--mermaid"])
        assert exit_code == 0
