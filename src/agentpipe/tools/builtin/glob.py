"""Built-in tool: find files by glob pattern (like OpenCode's glob)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentpipe.tools.base import Tool, ToolDefinition, ToolParameter


class GlobTool(Tool):
    """Find files matching a glob pattern."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir else Path.cwd()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="glob",
            description="Find files matching a glob pattern (e.g. '**/*.py', 'src/**/*.ts'). Returns matching file paths.",
            parameters=[
                ToolParameter(
                    name="pattern",
                    type="string",
                    description="The glob pattern to match files against",
                ),
                ToolParameter(
                    name="path",
                    type="string",
                    description="Directory to search in (default: workspace root)",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> str:
        pattern = kwargs["pattern"]
        search_dir = Path(kwargs.get("path", "")) if kwargs.get("path") else self._base_dir

        if not search_dir.is_absolute() and self._base_dir:
            search_dir = self._base_dir / search_dir

        try:
            matches = sorted(str(p) for p in search_dir.glob(pattern) if p.is_file())
            if not matches:
                return f"No files matched pattern '{pattern}' in {search_dir}"
            result = "\n".join(matches[:200])
            if len(matches) > 200:
                result += f"\n... and {len(matches) - 200} more files"
            return result
        except Exception as e:
            return f"Error: {e}"
