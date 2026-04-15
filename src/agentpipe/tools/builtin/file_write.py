"""Built-in tool: write/create files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentpipe.tools.base import Tool, ToolDefinition, ToolParameter


class FileWriteTool(Tool):
    """Write content to a file, creating directories as needed."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir else None

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="file_write",
            description="Write content to a file. Creates the file and parent directories if they don't exist.",
            parameters=[
                ToolParameter(name="path", type="string", description="File path to write to"),
                ToolParameter(
                    name="content", type="string", description="Content to write to the file"
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> str:
        path = Path(kwargs["path"])
        if self._base_dir and not path.is_absolute():
            path = self._base_dir / path

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(kwargs["content"])
            return f"Successfully wrote {len(kwargs['content'])} characters to {path}"
        except Exception as e:
            return f"Error writing file: {e}"
