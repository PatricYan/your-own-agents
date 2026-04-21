"""Unit tests for agentpipe.loader — YAML and JSON pipeline loading."""

import json

from agentpipe.loader.yaml_loader import load_pipeline_from_yaml, load_pipeline_from_yaml_string


class TestYamlLoader:
    def test_load_simple_pipeline(self, tmp_path):
        yaml_content = """
name: test
tasks:
  - name: a
    goal: Do A
    primary_model: m
"""
        f = tmp_path / "p.yaml"
        f.write_text(yaml_content)
        p = load_pipeline_from_yaml(f)
        assert p.name == "test"
        assert len(p.tasks) == 1

    def test_load_with_depends_on(self, tmp_path):
        yaml_content = """
name: deps
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
        assert len(p.edges) == 1
        assert p.get_task("b").depends_on == ["a"]

    def test_load_with_permissions(self, tmp_path):
        yaml_content = """
name: perms
tasks:
  - name: a
    goal: A
    primary_model: m
    permissions:
      "*": deny
      read: allow
      bash: allow
"""
        f = tmp_path / "p.yaml"
        f.write_text(yaml_content)
        p = load_pipeline_from_yaml(f)
        task = p.get_task("a")
        assert task.permissions.allows("read")
        assert task.permissions.allows("shell")
        assert task.permissions.is_denied("edit")

    def test_load_with_file_permissions(self):
        """Load a real example that uses file-path permissions."""
        p = load_pipeline_from_yaml("examples/04-permissions-demo.yaml")
        reviewer = p.get_task("reviewer")
        assert reviewer.permissions.is_denied("edit")
        assert reviewer.permissions.allows("read")

    def test_load_with_file_goal(self):
        """Load a real example that uses file-path goals."""
        p = load_pipeline_from_yaml("examples/07-file-config.yaml")
        researcher = p.get_task("researcher")
        assert "Research" in researcher.goal

    def test_load_from_string(self):
        yaml_str = """
name: inline
tasks:
  - name: x
    goal: do X
    primary_model: m
"""
        p = load_pipeline_from_yaml_string(yaml_str)
        assert p.name == "inline"

    def test_all_examples_validate(self):
        """Every example pipeline should load without error."""
        import glob as g
        from pathlib import Path

        for f in sorted(g.glob("examples/0*.yaml")):  # 01-08 only, skip models.yaml
            p = load_pipeline_from_yaml(Path(f))
            assert p.name, f"Pipeline in {f} has no name"
            assert len(p.tasks) > 0, f"Pipeline in {f} has no tasks"


class TestJsonLoader:
    def test_load_from_json(self, tmp_path):
        from agentpipe.loader.json_loader import load_pipeline_from_json

        data = {
            "name": "json-test",
            "tasks": [{"name": "a", "goal": "A", "primary_model": "m"}],
        }
        f = tmp_path / "p.json"
        f.write_text(json.dumps(data))
        p = load_pipeline_from_json(f)
        assert p.name == "json-test"
