"""Backward-compat shim: types now live in agentpipe.common."""

from agentpipe.common import (  # noqa: F401
    Conversation,
    Message,
    ToolCall,
    ToolDefinition,
    ToolParameter,
    ToolResult,
)

__all__ = [
    "Conversation",
    "Message",
    "ToolCall",
    "ToolDefinition",
    "ToolParameter",
    "ToolResult",
]
