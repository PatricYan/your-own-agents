"""Built-in tool: edit files using exact string replacement (like OpenCode's edit)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentpipe.tools.base import Tool, ToolDefinition, ToolParameter


class EditTool(Tool):
    """Edit an existing file by replacing an exact string match.

    Modeled after OpenCode's edit tool — performs precise replacements
    rather than rewriting entire files.
    """

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir else None

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="edit",
            description=(
                "Edit a file by replacing an exact string with a new string. "
                "Provide the old text to find and the new text to replace it with. "
                "The old text must match exactly (including whitespace)."
            ),
            parameters=[
                ToolParameter(
                    name="file_path", type="string", description="Path to the file to edit"
                ),
                ToolParameter(
                    name="old_string",
                    type="string",
                    description="The exact text to find and replace",
                ),
                ToolParameter(name="new_string", type="string", description="The replacement text"),
            ],
        )

    async def execute(self, **kwargs: Any) -> str:
        path = Path(kwargs["file_path"])
        if self._base_dir and not path.is_absolute():
            path = self._base_dir / path

        if not path.exists():
            return f"Error: File not found: {path}"

        old_string = kwargs["old_string"]
        new_string = kwargs["new_string"]

        try:
            content = path.read_text()
            count = content.count(old_string)
            if count == 0:
                return f"Error: old_string not found in {path}"
            if count > 1:
                return f"Error: Found {count} matches for old_string in {path}. Provide more context to make the match unique."
            new_content = content.replace(old_string, new_string, 1)
            path.write_text(new_content)
            return f"Successfully edited {path}"
        except Exception as e:
            return f"Error editing file: {e}"
