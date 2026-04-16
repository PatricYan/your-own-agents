"""Shared data schemas used across all modules.

This package contains pure data classes with no business logic,
so that any module (models, tools, execution, core) can import
them without creating circular dependencies.
"""

from agentpipe.schema.conversation import Conversation, Message, ToolCall, ToolResult
from agentpipe.schema.tool_schema import ToolDefinition, ToolParameter

__all__ = [
    "Conversation",
    "Message",
    "ToolCall",
    "ToolDefinition",
    "ToolParameter",
    "ToolResult",
]
