"""Message and conversation models for multi-turn agent interactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """A tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """The result of executing a tool call."""

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class Message:
    """A single message in a conversation.

    Roles:
        system  - system instructions / agent persona
        user    - user input or tool results
        assistant - model responses (may include tool_calls)
        tool    - tool execution results
    """

    role: str  # system, user, assistant, tool
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None  # For tool-result messages

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for model APIs."""
        d: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in self.tool_calls
            ]
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass
class Conversation:
    """An ordered list of messages forming a multi-turn conversation."""

    messages: list[Message] = field(default_factory=list)

    def add_system(self, content: str) -> None:
        self.messages.append(Message(role="system", content=content))

    def add_user(self, content: str) -> None:
        self.messages.append(Message(role="user", content=content))

    def add_assistant(
        self, content: str | None = None, tool_calls: list[ToolCall] | None = None
    ) -> None:
        self.messages.append(Message(role="assistant", content=content, tool_calls=tool_calls))

    def add_tool_result(self, tool_call_id: str, content: str, is_error: bool = False) -> None:
        self.messages.append(Message(role="tool", content=content, tool_call_id=tool_call_id))

    def to_list(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self.messages]

    def token_estimate(self) -> int:
        """Rough token estimate (4 chars per token heuristic)."""
        total_chars = sum(len(m.content or "") for m in self.messages)
        return total_chars // 4
