"""Task definition model: each task is an autonomous agent in the pipeline."""

from __future__ import annotations

import fnmatch
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from agentpipe.core.constraint import Constraint


class PermissionLevel(StrEnum):
    """Permission level for a tool — matches OpenCode exactly."""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


# Default permissions — read-only. Tasks can only read and search
# by default. Edit, write, delete, shell, network are all denied.
# You must explicitly grant permissions for anything destructive.
_DEFAULTS: dict[str, Any] = {
    "*": "deny",
    "read": "allow",
    "glob": "allow",
    "grep": "allow",
    "list": "allow",
    "submit_result": "allow",
}


class Permissions:
    """Granular permissions controlling what an agent-task can do.

    Follows OpenCode's permission format exactly::

        # Simple: set all tools at once
        permission: allow

        # Per-tool: global default + overrides
        permission:
          "*": ask
          read: allow
          edit: deny
          bash:
            "*": deny
            "git *": allow
            "npm *": allow
            "rm *": deny

    Rules:
    - ``"*"`` sets the global default for tools not listed
    - Each tool key is a string (``allow``/``ask``/``deny``) or an object
      with granular wildcard patterns
    - Granular rules: last matching pattern wins
    - ``allow`` = run without approval
    - ``ask`` = prompt user in interactive mode, auto-allow in autonomous mode
    - ``deny`` = block the action
    """

    def __init__(self, rules: dict[str, Any] | str | None = None) -> None:
        if rules is None or (isinstance(rules, dict) and not rules):
            rules = dict(_DEFAULTS)
        elif isinstance(rules, str):
            # "allow" / "ask" / "deny" — set everything to one level
            rules = {"*": rules}

        self._rules: dict[str, Any] = rules
        self._global_default = PermissionLevel(self._rules.get("*", "allow"))

    def get_level(self, tool_name: str, input_value: str = "") -> PermissionLevel:
        """Resolve the permission level for a tool call.

        Args:
            tool_name: The canonical tool name (e.g. ``bash``, ``read``, ``edit``).
            input_value: The tool's input for granular matching
                         (e.g. the shell command, file path, URL).

        Returns:
            The resolved PermissionLevel.
        """
        tool_name = self._normalize(tool_name)
        rule = self._rules.get(tool_name)

        if rule is None:
            return self._global_default

        # Simple string rule: "allow" / "ask" / "deny"
        if isinstance(rule, str):
            return PermissionLevel(rule)

        # Granular object rule with wildcard patterns
        if isinstance(rule, dict):
            return self._match_patterns(rule, input_value)

        return self._global_default

    def allows(self, tool_name: str, input_value: str = "") -> bool:
        """Check if a tool call is allowed (allow or ask)."""
        return self.get_level(tool_name, input_value) != PermissionLevel.DENY

    def is_denied(self, tool_name: str, input_value: str = "") -> bool:
        """Check if a tool call is denied."""
        return self.get_level(tool_name, input_value) == PermissionLevel.DENY

    def needs_approval(self, tool_name: str, input_value: str = "") -> bool:
        """Check if a tool call needs user approval."""
        return self.get_level(tool_name, input_value) == PermissionLevel.ASK

    def allowed_tool_names(self) -> list[str]:
        """Return canonical tool names that are allowed (no input context)."""
        all_tools = [
            "file_read",
            "edit",
            "file_write",
            "file_delete",
            "shell",
            "glob",
            "grep",
            "list",
            "webfetch",
            "submit_result",
        ]
        return [name for name in all_tools if self.allows(name)]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (for API, YAML, JSON)."""
        return dict(self._rules)

    def _match_patterns(self, rules: dict[str, str], input_value: str) -> PermissionLevel:
        """Match input against wildcard patterns. Last match wins (OpenCode convention)."""
        result = PermissionLevel(rules.get("*", self._global_default.value))
        for pattern, level in rules.items():
            if pattern == "*":
                continue
            if fnmatch.fnmatch(input_value, pattern):
                result = PermissionLevel(level)
        return result

    @staticmethod
    def _normalize(tool_name: str) -> str:
        """Map tool names to canonical permission keys."""
        mapping = {
            "file_read": "read",
            "file_write": "edit",
            "file_delete": "edit",
            "shell": "bash",
            "list_dir": "list",
            "web_fetch": "webfetch",
        }
        return mapping.get(tool_name, tool_name)

    def __repr__(self) -> str:
        return f"Permissions({self._rules})"


def load_permissions(value: str | dict | Permissions) -> Permissions:
    """Load Permissions from a dict, a YAML/JSON file path, or pass through."""
    if isinstance(value, Permissions):
        return value
    if isinstance(value, dict):
        return Permissions(value)
    if isinstance(value, str):
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
                return Permissions(raw)
            if isinstance(raw, str):
                return Permissions(raw)
        # Maybe it's "allow" / "ask" / "deny" as a bare string
        if value in ("allow", "ask", "deny"):
            return Permissions(value)
    return Permissions()


def load_text_or_file(value: str) -> str:
    """Load text from a string or from a file path (.md, .txt, .prompt)."""
    if not value:
        return value
    path = Path(value)
    if path.exists() and path.suffix in (".md", ".txt", ".prompt"):
        return path.read_text().strip()
    return value


class TaskDefinition(BaseModel):
    """An autonomous agent task within a pipeline.

    Each task is an agent with its own model, tools, goal, and loop.

    **Configuration from files** — ``goal``, ``system_prompt``, and
    ``permissions`` can be inline values or file paths.

    **Permissions** follow OpenCode's format exactly::

        # Set all at once
        permissions: allow

        # Per-tool with global default
        permissions:
          "*": ask
          read: allow
          edit: deny
          bash:
            "*": deny
            "git *": allow
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str

    goal: str
    system_prompt: str | None = None

    models: list[str] = Field(default_factory=list)
    primary_model: str | None = None
    fallback_models: list[str] = Field(default_factory=list)

    permissions: Any = Field(default_factory=Permissions)

    tools: list[str] = Field(default_factory=list)
    depends_on: list[str] | str = Field(default_factory=list)

    max_iterations: int = 20
    max_tool_calls: int | None = None
    max_tokens: int | None = None  # Total token budget; loop stops if exceeded
    context_window: int | None = None  # Max tokens in conversation; older messages trimmed

    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None

    constraints: list[Constraint] = Field(default_factory=list)

    is_reusable: bool = False
    sub_pipeline: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    prompt_template: str | None = None

    model_config = {"arbitrary_types_allowed": True}

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
            return load_text_or_file(v)
        pt = info.data.get("prompt_template")
        if pt and pt.strip():
            return pt
        if info.data.get("sub_pipeline") is not None:
            return "Execute sub-pipeline"
        raise ValueError("Task must have a goal")

    @field_validator("system_prompt", mode="before")
    @classmethod
    def validate_system_prompt(cls, v: str | None) -> str | None:
        if v and v.strip():
            return load_text_or_file(v)
        return v

    @field_validator("permissions", mode="before")
    @classmethod
    def validate_permissions(cls, v: Any) -> Permissions:
        if isinstance(v, Permissions):
            return v
        return load_permissions(v)

    @field_validator("depends_on", mode="before")
    @classmethod
    def normalize_depends_on(cls, v: list[str] | str) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v

    @model_validator(mode="after")
    def merge_model_fields(self) -> TaskDefinition:
        if self.models:
            if not self.primary_model:
                self.primary_model = self.models[0]
            if not self.fallback_models and len(self.models) > 1:
                self.fallback_models = self.models[1:]
        elif self.primary_model:
            self.models = [self.primary_model, *self.fallback_models]
        if not self.primary_model and not self.models and self.sub_pipeline is None:
            raise ValueError("Task must have at least one model (via 'models' or 'primary_model')")
        return self

    def effective_tools(self) -> list[str]:
        if self.tools:
            return self.tools
        return self.permissions.allowed_tool_names()
