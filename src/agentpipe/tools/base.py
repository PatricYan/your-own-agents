"""Base tool interface for agent tool execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agentpipe.schema.tool_schema import ToolDefinition, ToolParameter

__all__ = ["Tool", "ToolDefinition", "ToolParameter"]


class Tool(ABC):
    """Abstract base class for tools that agents can use.

    A tool receives structured input, performs an action (read a file,
    run a command, search the web, etc.), and returns a text result.
    """

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return the tool's schema definition for model APIs."""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool with the given arguments.

        Returns:
            A string result to be sent back to the model.

        Raises:
            Exception: If tool execution fails.
        """
