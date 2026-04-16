"""Backward-compatibility shim: classes now live in agentpipe.schema.conversation."""

from agentpipe.schema.conversation import (  # noqa: F401
    Conversation,
    Message,
    ToolCall,
    ToolResult,
)

__all__ = ["Conversation", "Message", "ToolCall", "ToolResult"]
