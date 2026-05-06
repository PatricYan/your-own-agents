"""Common data types shared across all modules.

Pure data classes with no business logic — any module can import
from here without creating circular dependencies.
"""

from agentpipe.common.conversation import Conversation, Message, ToolCall, ToolResult
from agentpipe.common.tool_schema import ToolDefinition, ToolParameter

__all__ = [
    "Conversation",
    "Message",
    "ToolCall",
    "ToolDefinition",
    "ToolParameter",
    "ToolResult",
]
