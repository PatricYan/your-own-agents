"""Base model provider interface for multi-turn conversations with tool support."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from agentpipe.schema import Message, ToolCall, ToolDefinition


class StopReason(StrEnum):
    """Reason the model stopped generating."""

    END_TURN = "end_turn"
    TOOL_USE = "tool_use"
    MAX_TOKENS = "max_tokens"
    STOP_SEQUENCE = "stop_sequence"


@dataclass
class ModelResponse:
    """Response from a model provider."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: StopReason = StopReason.END_TURN
    raw: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, int] | None = None


class ModelProvider(ABC):
    """Abstract base class for model provider adapters.

    Supports multi-turn conversations and tool/function calling.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> ModelResponse:
        """Send a conversation to the model and return the response.

        Args:
            messages: The conversation history (system, user, assistant, tool messages).
            tools: Optional list of tool definitions the model can invoke.
            parameters: Optional model parameters (temperature, max_tokens, etc.).

        Returns:
            ModelResponse with content and/or tool_calls.

        Raises:
            RuntimeError: If the model call fails.
        """

    async def send(self, prompt: str, parameters: dict[str, Any] | None = None) -> ModelResponse:
        """Convenience: single-prompt call (wraps chat with a single user message).

        Kept for backward compatibility with simple use cases.
        """
        msg = Message(role="user", content=prompt)
        return await self.chat([msg], parameters=parameters)
