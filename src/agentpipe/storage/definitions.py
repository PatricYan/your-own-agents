"""Workspace-level file storage for agent and model definitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class DefinitionStore:
    """File-based storage for agent and model definitions in a workspace directory."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._agents_dir = workspace / ".agentpipe" / "agents"
        self._models_dir = workspace / ".agentpipe" / "models"
        self._tasks_dir = workspace / ".agentpipe" / "tasks"
        self._agents_dir.mkdir(parents=True, exist_ok=True)
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._tasks_dir.mkdir(parents=True, exist_ok=True)

    # --- Agent operations ---

    def save_agent(self, name: str, data: dict[str, Any]) -> Path:
        """Save an agent definition as YAML."""
        path = self._agents_dir / f"{name}.yaml"
        path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        return path

    def load_agent(self, name: str) -> dict[str, Any]:
        """Load an agent definition by name."""
        path = self._agents_dir / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Agent '{name}' not found")
        return yaml.safe_load(path.read_text())

    def list_agents(self) -> list[str]:
        """List all saved agent names."""
        return [p.stem for p in self._agents_dir.glob("*.yaml")]

    def delete_agent(self, name: str) -> None:
        """Delete an agent definition."""
        path = self._agents_dir / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Agent '{name}' not found")
        path.unlink()

    # --- Model operations ---

    def save_model(self, name: str, data: dict[str, Any]) -> Path:
        """Save a model configuration as YAML."""
        path = self._models_dir / f"{name}.yaml"
        path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        return path

    def load_model(self, name: str) -> dict[str, Any]:
        """Load a model configuration by name."""
        path = self._models_dir / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Model '{name}' not found")
        return yaml.safe_load(path.read_text())

    def list_models(self) -> list[str]:
        """List all saved model configuration names."""
        return [p.stem for p in self._models_dir.glob("*.yaml")]

    def delete_model(self, name: str) -> None:
        """Delete a model configuration."""
        path = self._models_dir / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Model '{name}' not found")
        path.unlink()

    # --- Reusable task operations ---

    def save_task(self, name: str, data: dict[str, Any]) -> Path:
        """Save a reusable task definition as YAML."""
        path = self._tasks_dir / f"{name}.yaml"
        path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        return path

    def load_task(self, name: str) -> dict[str, Any]:
        """Load a reusable task definition by name."""
        path = self._tasks_dir / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Reusable task '{name}' not found")
        return yaml.safe_load(path.read_text())

    def list_tasks(self) -> list[str]:
        """List all saved reusable task names."""
        return [p.stem for p in self._tasks_dir.glob("*.yaml")]
