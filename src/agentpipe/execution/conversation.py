"""Backward-compatibility shim: classes now live in agentpipe.common.conversation."""

from agentpipe.common.conversation import (  # noqa: F401
    Conversation,
    Message,
    ToolCall,
    ToolResult,
)

__all__ = ["Conversation", "Message", "ToolCall", "ToolResult"]
