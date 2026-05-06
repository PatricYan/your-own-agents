"""Built-in tool: search file contents using regex (like OpenCode's grep)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agentpipe.tools.base import Tool, ToolDefinition, ToolParameter


class GrepTool(Tool):
    """Search file contents using a regular expression."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir else Path.cwd()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="grep",
            description="Search file contents using a regular expression. Returns file paths and matching lines.",
            parameters=[
                ToolParameter(
                    name="pattern", type="string", description="The regex pattern to search for"
                ),
                ToolParameter(
                    name="path",
                    type="string",
                    description="Directory to search in (default: workspace root)",
                    required=False,
                ),
                ToolParameter(
                    name="include",
                    type="string",
                    description="File glob to filter (e.g. '*.py', '*.ts')",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> str:
        pattern_str = kwargs["pattern"]
        search_dir = Path(kwargs.get("path", "")) if kwargs.get("path") else self._base_dir
        include = kwargs.get("include", "**/*")

        if not search_dir.is_absolute() and self._base_dir:
            search_dir = self._base_dir / search_dir

        try:
            regex = re.compile(pattern_str)
        except re.error as e:
            return f"Error: Invalid regex pattern: {e}"

        results: list[str] = []
        try:
            for file_path in search_dir.glob(include):
                if not file_path.is_file():
                    continue
                try:
                    text = file_path.read_text(errors="replace")
                    for i, line in enumerate(text.splitlines(), 1):
                        if regex.search(line):
                            results.append(f"{file_path}:{i}: {line.rstrip()}")
                            if len(results) >= 500:
                                results.append("... (truncated at 500 matches)")
                                return "\n".join(results)
                except (OSError, UnicodeDecodeError):
                    continue
        except Exception as e:
            return f"Error searching: {e}"

        if not results:
            return f"No matches for pattern '{pattern_str}'"
        return "\n".join(results)
