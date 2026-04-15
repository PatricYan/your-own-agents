"""Built-in tool: read file contents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentpipe.tools.base import Tool, ToolDefinition, ToolParameter


class FileReadTool(Tool):
    """Read the contents of a file."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir else None

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="file_read",
            description="Read the contents of a file at the given path.",
            parameters=[
                ToolParameter(name="path", type="string", description="File path to read"),
                ToolParameter(
                    name="offset",
                    type="integer",
                    description="Line number to start from (1-indexed)",
                    required=False,
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of lines to read",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> str:
        path = Path(kwargs["path"])
        if self._base_dir and not path.is_absolute():
            path = self._base_dir / path

        if not path.exists():
            return f"Error: File not found: {path}"

        try:
            content = path.read_text()
            lines = content.splitlines(keepends=True)

            offset = int(kwargs.get("offset", 1)) - 1
            limit = kwargs.get("limit")
            if limit is not None:
                lines = lines[offset : offset + int(limit)]
            elif offset > 0:
                lines = lines[offset:]

            return "".join(lines)
        except Exception as e:
            return f"Error reading file: {e}"
