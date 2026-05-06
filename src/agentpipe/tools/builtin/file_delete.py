"""Built-in tool: delete files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentpipe.tools.base import Tool, ToolDefinition, ToolParameter


class FileDeleteTool(Tool):
    """Delete a file at the given path."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir else None

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="file_delete",
            description="Delete a file at the given path.",
            parameters=[
                ToolParameter(name="path", type="string", description="File path to delete"),
            ],
        )

    async def execute(self, **kwargs: Any) -> str:
        path = Path(kwargs["path"])
        if self._base_dir and not path.is_absolute():
            path = self._base_dir / path

        if not path.exists():
            return f"Error: File not found: {path}"

        try:
            path.unlink()
            return f"Successfully deleted {path}"
        except Exception as e:
            return f"Error deleting file: {e}"
