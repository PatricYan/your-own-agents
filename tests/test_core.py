"""Unit tests for agentpipe.core — Task, Pipeline, Condition, Constraint, Visualize."""

import pytest

from agentpipe.core.condition import Condition, Edge, evaluate_condition, validate_expression
from agentpipe.core.constraint import Constraint, ConstraintType, ViolationAction
from agentpipe.core.pipeline import Pipeline
from agentpipe.core.task import Permissions, TaskDefinition, load_text_or_file


class TestTaskDefinition:
    def test_basic_task(self):
        t = TaskDefinition(name="t", goal="do it", primary_model="m")
        assert t.name == "t"
        assert t.goal == "do it"
        assert t.primary_model == "m"

    def test_goal_from_file(self):
        t = TaskDefinition(name="t", goal="examples/goals/research.md", primary_model="m")
        assert "Research" in t.goal

    def test_system_prompt_from_file(self):
        t = TaskDefinition(
            name="t",
            goal="g",
            primary_model="m",
            system_prompt="examples/prompts/code-reviewer.md",
        )
        assert "code reviewer" in t.system_prompt

    def test_permissions_from_file(self):
        t = TaskDefinition(
            name="t",
            goal="g",
            primary_model="m",
            permissions="examples/permissions/developer.yaml",
        )
        assert t.permissions.allows("read")
        assert t.permissions.get_level("bash", "git status").value == "allow"

    def test_depends_on_single_string(self):
        t = TaskDefinition(name="b", goal="g", primary_model="m", depends_on="a")
        assert t.depends_on == ["a"]

    def test_depends_on_list(self):
        t = TaskDefinition(name="d", goal="g", primary_model="m", depends_on=["b", "c"])
        assert t.depends_on == ["b", "c"]

    def test_models_list(self):
        t = TaskDefinition(name="t", goal="g", models=["gpt-4o", "claude", "llama"])
        assert t.primary_model == "gpt-4o"
        assert t.fallback_models == ["claude", "llama"]

    def test_effective_tools_from_permissions(self):
        t = TaskDefinition(
            name="t",
            goal="g",
            primary_model="m",
            permissions=Permissions({"*": "deny", "read": "allow", "bash": "allow"}),
        )
        eff = t.effective_tools()
        assert "file_read" in eff
        assert "shell" in eff
        assert "edit" not in eff

    def test_explicit_tools_override_permissions(self):
        t = TaskDefinition(
            name="t",
            goal="g",
            primary_model="m",
            permissions=Permissions({"bash": "deny"}),
            tools=["shell", "web_fetch"],
        )
        assert t.effective_tools() == ["shell", "web_fetch"]

    def test_missing_goal_raises(self):
        with pytest.raises(ValueError, match="goal"):
            TaskDefinition(name="t", goal="", primary_model="m")

    def test_missing_model_raises(self):
        with pytest.raises(ValueError, match="model"):
            TaskDefinition(name="t", goal="g")


class TestLoadTextOrFile:
    def test_inline_string(self):
        assert load_text_or_file("hello world") == "hello world"

    def test_from_md_file(self):
        result = load_text_or_file("examples/goals/research.md")
        assert "Research" in result

    def test_missing_file_returns_string(self):
        assert load_text_or_file("nonexistent.md") == "nonexistent.md"

    def test_empty_string(self):
        assert load_text_or_file("") == ""


class TestPipeline:
    def test_depends_on_generates_edges(self):
        p = Pipeline(
            name="test",
            tasks=[
                TaskDefinition(name="a", goal="A", primary_model="m"),
                TaskDefinition(name="b", goal="B", primary_model="m", depends_on="a"),
                TaskDefinition(name="c", goal="C", primary_model="m", depends_on=["a", "b"]),
            ],
        )
        assert len(p.edges) == 3
        assert p.get_upstream_tasks("c") == ["a", "b"]

    def test_topological_sort(self):
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
        with pytest.raises(ValueError, match="cycle"):
            Pipeline(
                name="cycle",
                tasks=[
                    TaskDefinition(name="a", goal="A", primary_model="m", depends_on="b"),
                    TaskDefinition(name="b", goal="B", primary_model="m", depends_on="a"),
                ],
            )

    def test_invalid_depends_on_reference(self):
        with pytest.raises(ValueError, match="not in the pipeline"):
            Pipeline(
                name="bad",
                tasks=[
                    TaskDefinition(name="a", goal="A", primary_model="m", depends_on="nonexistent"),
                ],
            )

    def test_mixed_depends_on_and_explicit_edges(self):
        p = Pipeline(
            name="mixed",
            tasks=[
                TaskDefinition(name="a", goal="A", primary_model="m"),
                TaskDefinition(name="b", goal="B", primary_model="m", depends_on="a"),
                TaskDefinition(name="c", goal="C", primary_model="m"),
            ],
            edges=[Edge(source_task="a", target_task="c", condition=Condition(expression="x > 1"))],
        )
        assert len(p.edges) == 2

    def test_render_dag_ascii(self):
        p = Pipeline(
            name="test",
            tasks=[
                TaskDefinition(name="a", goal="A", primary_model="m"),
                TaskDefinition(name="b", goal="B", primary_model="m", depends_on="a"),
            ],
        )
        output = p.render_dag("ascii")
        assert "a" in output
        assert "b" in output

    def test_render_dag_mermaid(self):
        p = Pipeline(
            name="test",
            tasks=[
                TaskDefinition(name="a", goal="A", primary_model="m"),
                TaskDefinition(name="b", goal="B", primary_model="m", depends_on="a"),
            ],
        )
        output = p.render_dag("mermaid")
        assert "graph TD" in output


class TestCondition:
    def test_validate_expression_valid(self):
        assert validate_expression("score > 0.8")

    def test_validate_expression_invalid(self):
        with pytest.raises(ValueError):
            validate_expression("import os")

    def test_evaluate_true(self):
        c = Condition(expression="score > 0.5")
        assert evaluate_condition(c, {"score": 0.9})

    def test_evaluate_false(self):
        c = Condition(expression="score > 0.5")
        assert not evaluate_condition(c, {"score": 0.3})

    def test_evaluate_callable(self):
        assert evaluate_condition(lambda d: d["x"] > 0, {"x": 1})

    def test_evaluate_empty_expression(self):
        c = Condition(expression="")
        assert evaluate_condition(c, {})


class TestConstraint:
    def test_max_retries(self):
        c = Constraint(type=ConstraintType.MAX_RETRIES, value=3, on_violation=ViolationAction.FAIL)
        assert c.value == 3

    def test_timeout(self):
        c = Constraint(type=ConstraintType.TIMEOUT, value=60, on_violation=ViolationAction.FAIL)
        assert c.value == 60

    def test_invalid_retries_value(self):
        with pytest.raises(ValueError):
            Constraint(type=ConstraintType.MAX_RETRIES, value=-1, on_violation=ViolationAction.FAIL)

    def test_invalid_timeout_value(self):
        with pytest.raises(ValueError):
            Constraint(type=ConstraintType.TIMEOUT, value=0, on_violation=ViolationAction.FAIL)
