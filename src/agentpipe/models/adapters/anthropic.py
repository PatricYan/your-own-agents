"""Anthropic model adapter with tool calling support."""

from __future__ import annotations

import os
from typing import Any

from agentpipe.models.http_session import HttpSession
from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason
from agentpipe.schema import Message, ToolCall, ToolDefinition


class AnthropicModelProvider(ModelProvider):
    """Adapter for Anthropic Messages API with tool use."""

    def __init__(
        self,
        api_key_env: str = "ANTHROPIC_API_KEY",
        base_url: str = "https://api.anthropic.com",
        model: str = "claude-sonnet-4-20250514",
        default_params: dict[str, Any] | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._api_key_env = api_key_env
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._default_params = default_params or {}
        self._session = HttpSession(timeout=timeout)

    def _get_api_key(self) -> str:
        key = os.environ.get(self._api_key_env, "")
        if not key:
            raise RuntimeError(f"API key not found in env var '{self._api_key_env}'")
        return key

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> ModelResponse:
        api_key = self._get_api_key()
        params = {**self._default_params, **(parameters or {})}

        # Separate system message from conversation
        system_content = None
        api_messages = []
        for msg in messages:
            if msg.role == "system":
                system_content = msg.content
                continue

            if msg.role == "tool":
                # Anthropic uses tool_result content blocks
                api_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.content or "",
                            }
                        ],
                    }
                )
            elif msg.role == "assistant" and msg.tool_calls:
                # Build content blocks with text + tool_use
                content_blocks: list[dict[str, Any]] = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    )
                api_messages.append({"role": "assistant", "content": content_blocks})
            else:
                api_messages.append({"role": msg.role, "content": msg.content or ""})

        max_tokens = params.pop("max_tokens", 4096)
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": api_messages,
            **{
                k: v
                for k, v in params.items()
                if k not in ("model", "max_tokens", "messages", "tools", "system")
            },
        }
        if system_content:
            payload["system"] = system_content
        if tools:
            payload["tools"] = [t.to_anthropic_schema() for t in tools]

        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        data = await self._session.post_json(f"{self._base_url}/v1/messages", payload, headers)

        # Parse response content blocks
        content_text = ""
        tool_calls = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                content_text += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(id=block["id"], name=block["name"], arguments=block.get("input", {}))
                )

        stop_reason_str = data.get("stop_reason", "end_turn")
        stop_reason = StopReason.TOOL_USE if stop_reason_str == "tool_use" else StopReason.END_TURN
        if stop_reason_str == "max_tokens":
            stop_reason = StopReason.MAX_TOKENS

        return ModelResponse(
            content=content_text or None,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            raw=data,
            usage=data.get("usage"),
        )
