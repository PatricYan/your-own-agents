"""Message and conversation models for multi-turn agent interactions.

Includes conversation window management — when conversations grow too large
for a model's context window, older messages are trimmed while preserving
the system prompt and recent context.
"""

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
    """A single message in a conversation."""

    role: str  # system, user, assistant, tool
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
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

    def token_estimate(self) -> int:
        """Rough token estimate for this message (4 chars ≈ 1 token)."""
        chars = len(self.content or "")
        if self.tool_calls:
            for tc in self.tool_calls:
                chars += len(tc.name) + len(str(tc.arguments))
        return max(chars // 4, 1)


@dataclass
class Conversation:
    """An ordered list of messages with context window management.

    When conversations grow long, use ``trim_to_budget()`` to truncate
    older messages while preserving the system prompt and recent context.
    """

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
        """Total token estimate for the entire conversation."""
        return sum(m.token_estimate() for m in self.messages)

    def trim_to_budget(self, max_tokens: int) -> int:
        """Trim conversation to fit within a token budget.

        Strategy:
        1. Always keep the system prompt (first message if role=system)
        2. Always keep the last N messages (recent context)
        3. Remove the oldest non-system messages first
        4. If a single message is too large, truncate its content

        Returns the number of messages removed.
        """
        if self.token_estimate() <= max_tokens:
            return 0

        # Separate system message from the rest
        system_msgs = [m for m in self.messages if m.role == "system"]
        other_msgs = [m for m in self.messages if m.role != "system"]

        system_tokens = sum(m.token_estimate() for m in system_msgs)
        budget_for_others = max_tokens - system_tokens

        if budget_for_others <= 0:
            # System prompt alone exceeds budget — truncate it
            if system_msgs:
                max_chars = max_tokens * 4
                system_msgs[0].content = (system_msgs[0].content or "")[:max_chars]
            self.messages = system_msgs + other_msgs[-2:]  # keep last 2
            return len(other_msgs) - 2

        # Remove oldest messages until we fit
        removed = 0
        while other_msgs and sum(m.token_estimate() for m in other_msgs) > budget_for_others:
            other_msgs.pop(0)
            removed += 1

        # Truncate the oldest remaining message if still over budget
        if other_msgs and sum(m.token_estimate() for m in other_msgs) > budget_for_others:
            excess = sum(m.token_estimate() for m in other_msgs) - budget_for_others
            excess_chars = excess * 4
            first = other_msgs[0]
            if first.content and len(first.content) > excess_chars:
                first.content = first.content[excess_chars:]

        self.messages = system_msgs + other_msgs
        return removed
