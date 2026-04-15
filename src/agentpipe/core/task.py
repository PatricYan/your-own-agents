"""Task definition model: each task is an autonomous agent in the pipeline."""

from __future__ import annotations

import uuid
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from agentpipe.core.constraint import Constraint


class PermissionLevel(StrEnum):
    """Permission level for a tool, matching OpenCode's model."""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class Permissions(BaseModel):
    """Granular permissions controlling what an agent-task can do.

    Modeled after OpenCode's permission system. Each tool has its own
    permission level: allow, ask, or deny.
    """

    default: PermissionLevel = PermissionLevel.DENY

    read: PermissionLevel = PermissionLevel.ALLOW
    edit: PermissionLevel = PermissionLevel.DENY
    write: PermissionLevel = PermissionLevel.DENY
    file_delete: PermissionLevel = PermissionLevel.DENY
    bash: PermissionLevel = PermissionLevel.DENY
    glob: PermissionLevel = PermissionLevel.ALLOW
    grep: PermissionLevel = PermissionLevel.ALLOW
    list: PermissionLevel = PermissionLevel.ALLOW
    web_fetch: PermissionLevel = PermissionLevel.DENY
    submit_result: PermissionLevel = PermissionLevel.ALLOW

    _TOOL_MAP: dict[str, str] = {
        "file_read": "read",
        "read": "read",
        "edit": "edit",
        "file_write": "write",
        "write": "write",
        "file_delete": "file_delete",
        "shell": "bash",
        "bash": "bash",
        "glob": "glob",
        "grep": "grep",
        "list": "list",
        "list_dir": "list",
        "web_fetch": "web_fetch",
        "submit_result": "submit_result",
    }

    def get_level(self, tool_name: str) -> PermissionLevel:
        field_name = self._TOOL_MAP.get(tool_name)
        if field_name is None:
            return self.default
        return getattr(self, field_name, self.default)

    def allows(self, tool_name: str) -> bool:
        return self.get_level(tool_name) in (PermissionLevel.ALLOW, PermissionLevel.ASK)

    def is_denied(self, tool_name: str) -> bool:
        return self.get_level(tool_name) == PermissionLevel.DENY

    def needs_approval(self, tool_name: str) -> bool:
        return self.get_level(tool_name) == PermissionLevel.ASK

    def allowed_tool_names(self) -> list[str]:
        canonical_tools = [
            "file_read",
            "edit",
            "file_write",
            "file_delete",
            "shell",
            "glob",
            "grep",
            "list",
            "web_fetch",
            "submit_result",
        ]
        return [name for name in canonical_tools if self.allows(name)]


def load_permissions(value: str | dict | Permissions) -> Permissions:
    """Load Permissions from a dict, a YAML file path, or pass through."""
    if isinstance(value, Permissions):
        return value
    if isinstance(value, dict):
        return Permissions(**value)
    # Treat as file path
    path = Path(value)
    if path.exists() and path.suffix in (".yaml", ".yml", ".json"):
        import json

        import yaml

        raw = (
            yaml.safe_load(path.read_text())
            if path.suffix != ".json"
            else json.loads(path.read_text())
        )
        if isinstance(raw, dict):
            return Permissions(**raw)
    return Permissions()


def load_goal(value: str) -> str:
    """Load goal text from a string or from a file path (.md, .txt)."""
    if not value:
        return value
    path = Path(value)
    if path.exists() and path.suffix in (".md", ".txt"):
        return path.read_text().strip()
    return value


class TaskDefinition(BaseModel):
    """An autonomous agent task within a pipeline.

    Each task is an agent with its own model, tools, goal, and loop.

    **Configuration from files**: ``goal`` and ``permissions`` can be
    either inline values or file paths:

    - ``goal: goals/research.md`` loads the goal from a Markdown file
    - ``permissions: permissions/read-only.yaml`` loads permissions from a YAML file

    **Multiple models**: ``models`` is an ordered list of model names.
    The first is primary; the rest are fallbacks. This replaces
    ``primary_model`` + ``fallback_models`` (both still work).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str

    # Agent identity and goal (can be a file path: goals/my-goal.md)
    goal: str
    system_prompt: str | None = None

    # Models — ordered list: first is primary, rest are fallbacks
    models: list[str] = Field(default_factory=list)

    # Legacy single-model fields (still work, merged into models)
    primary_model: str | None = None
    fallback_models: list[str] = Field(default_factory=list)

    # Permissions (can be a file path: permissions/read-only.yaml)
    permissions: Permissions = Field(default_factory=Permissions)

    # Tools override (if set, overrides permissions-derived list)
    tools: list[str] = Field(default_factory=list)

    # Airflow-style dependencies
    depends_on: list[str] | str = Field(default_factory=list)

    # Agent loop configuration
    max_iterations: int = 20
    max_tool_calls: int | None = None

    # I/O schemas
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None

    # Constraints
    constraints: list[Constraint] = Field(default_factory=list)

    # Composition
    is_reusable: bool = False
    sub_pipeline: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Legacy
    prompt_template: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Task name must be non-empty")
        return v.strip()

    @field_validator("goal", mode="before")
    @classmethod
    def validate_goal(cls, v: str | None, info) -> str:
        if v and v.strip():
            return load_goal(v)
        pt = info.data.get("prompt_template")
        if pt and pt.strip():
            return pt
        if info.data.get("sub_pipeline") is not None:
            return "Execute sub-pipeline"
        raise ValueError("Task must have a goal")

    @field_validator("permissions", mode="before")
    @classmethod
    def validate_permissions(cls, v: Any) -> Permissions:
        if isinstance(v, Permissions):
            return v
        if isinstance(v, str | dict):
            return load_permissions(v)
        return Permissions()

    @field_validator("depends_on", mode="before")
    @classmethod
    def normalize_depends_on(cls, v: list[str] | str) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v

    @model_validator(mode="after")
    def merge_model_fields(self) -> TaskDefinition:
        """Merge models list with primary_model/fallback_models.

        If ``models`` is set, it takes priority. Otherwise, build from
        ``primary_model`` + ``fallback_models``.
        """
        if self.models:
            # models list is authoritative
            if not self.primary_model:
                self.primary_model = self.models[0]
            if not self.fallback_models and len(self.models) > 1:
                self.fallback_models = self.models[1:]
        elif self.primary_model:
            # Build models list from legacy fields
            self.models = [self.primary_model, *self.fallback_models]
        # Validate: need at least one model (unless sub_pipeline)
        if not self.primary_model and not self.models and self.sub_pipeline is None:
            raise ValueError("Task must have at least one model (via 'models' or 'primary_model')")
        return self

    def effective_tools(self) -> list[str]:
        if self.tools:
            return self.tools
        return self.permissions.allowed_tool_names()
