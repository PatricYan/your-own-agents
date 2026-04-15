"""Built-in tool: list files and directories (like OpenCode's list)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentpipe.tools.base import Tool, ToolDefinition, ToolParameter


class ListDirTool(Tool):
    """List files and directories at a given path."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir else Path.cwd()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list",
            description="List files and directories at the given path. Directories are shown with a trailing /.",
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Directory path to list (default: workspace root)",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> str:
        target = Path(kwargs.get("path", "")) if kwargs.get("path") else self._base_dir

        if not target.is_absolute() and self._base_dir:
            target = self._base_dir / target

        if not target.exists():
            return f"Error: Path not found: {target}"
        if not target.is_dir():
            return f"Error: Not a directory: {target}"

        try:
            entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            lines = []
            for entry in entries[:500]:
                suffix = "/" if entry.is_dir() else ""
                lines.append(f"{entry.name}{suffix}")
            if len(entries) > 500:
                lines.append(f"... and {len(entries) - 500} more entries")
            return "\n".join(lines) if lines else "(empty directory)"
        except Exception as e:
            return f"Error listing directory: {e}"
