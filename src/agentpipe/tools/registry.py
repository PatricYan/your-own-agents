"""Tool registry: register, discover, and instantiate tools by name."""

from __future__ import annotations

from typing import Any

from agentpipe.schema import ToolDefinition
from agentpipe.tools.base import Tool


class ToolRegistry:
    """Registry of available tools that agents can use."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        self._tools[tool.definition.name] = tool

    def get(self, name: str) -> Tool:
        """Get a tool by name."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not registered")
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def get_definitions(self, names: list[str] | None = None) -> list[ToolDefinition]:
        """Get tool definitions, optionally filtered by name."""
        if names is None:
            return [t.definition for t in self._tools.values()]
        return [self._tools[n].definition for n in names if n in self._tools]

    def get_openai_schemas(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        return [d.to_openai_schema() for d in self.get_definitions(names)]

    def get_anthropic_schemas(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        return [d.to_anthropic_schema() for d in self.get_definitions(names)]


def create_default_registry(workspace: str | None = None) -> ToolRegistry:
    """Create a registry with all built-in tools.

    Tools modeled after OpenCode and Codex CLI:
      file_read, edit, file_write, file_delete, shell, glob, grep, list, web_fetch, submit_result
    """
    from agentpipe.tools.builtin.edit import EditTool
    from agentpipe.tools.builtin.file_delete import FileDeleteTool
    from agentpipe.tools.builtin.file_read import FileReadTool
    from agentpipe.tools.builtin.file_write import FileWriteTool
    from agentpipe.tools.builtin.glob import GlobTool
    from agentpipe.tools.builtin.grep import GrepTool
    from agentpipe.tools.builtin.list_dir import ListDirTool
    from agentpipe.tools.builtin.shell import ShellTool
    from agentpipe.tools.builtin.submit_result import SubmitResultTool
    from agentpipe.tools.builtin.web_fetch import WebFetchTool

    registry = ToolRegistry()
    # Read tools (default: allowed)
    registry.register(FileReadTool(base_dir=workspace))
    registry.register(GlobTool(base_dir=workspace))
    registry.register(GrepTool(base_dir=workspace))
    registry.register(ListDirTool(base_dir=workspace))
    # Write tools (default: denied, must be explicitly allowed)
    registry.register(EditTool(base_dir=workspace))
    registry.register(FileWriteTool(base_dir=workspace))
    registry.register(FileDeleteTool(base_dir=workspace))
    # Shell (default: denied)
    registry.register(ShellTool(cwd=workspace))
    # Network (default: denied)
    registry.register(WebFetchTool())
    # Completion (always allowed)
    registry.register(SubmitResultTool())
    return registry
