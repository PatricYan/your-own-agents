"""Base tool interface for agent tool execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolParameter:
    """A parameter in a tool's input schema."""

    name: str
    type: str  # string, integer, number, boolean, array, object
    description: str
    required: bool = True
    enum: list[str] | None = None


@dataclass
class ToolDefinition:
    """Schema definition for a tool, used to inform the model what tools are available.

    This maps directly to the function/tool definition format used by
    OpenAI, Anthropic, and other model APIs.
    """

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function-calling tool schema."""
        properties = {}
        required = []
        for p in self.parameters:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def to_anthropic_schema(self) -> dict[str, Any]:
        """Convert to Anthropic tool schema."""
        properties = {}
        required = []
        for p in self.parameters:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


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
