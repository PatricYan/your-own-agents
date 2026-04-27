"""Anthropic model adapter with streaming and tool calling."""

from __future__ import annotations

import json
from typing import Any

from agentpipe.common import Message, ToolCall, ToolDefinition
from agentpipe.models.http_session import HttpSession
from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason


class AnthropicModelProvider(ModelProvider):
    """Adapter for Anthropic Messages API with streaming."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "",
        default_params: dict[str, Any] | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._default_params = default_params or {}
        self._session = HttpSession(timeout=timeout)

    def _get_api_key(self) -> str:
        return self._api_key

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        parameters: dict[str, Any] | None = None,
        on_content: Any | None = None,
    ) -> ModelResponse:
        """Send a conversation. Streams by default for faster first-token.

        Args:
            on_content: Optional callback(text: str) called as content arrives.
        """
        api_key = self._get_api_key()
        params = {**self._default_params, **(parameters or {})}

        system_content = None
        api_messages = []
        for msg in messages:
            if msg.role == "system":
                system_content = msg.content
                continue
            if msg.role == "tool":
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
                content_blocks: list[dict[str, Any]] = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content_blocks.append(
                        {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
                    )
                api_messages.append({"role": "assistant", "content": content_blocks})
            else:
                api_messages.append({"role": msg.role, "content": msg.content or ""})

        max_tokens = params.pop("max_tokens", 4096)
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": api_messages,
            "stream": True,
            **{
                k: v
                for k, v in params.items()
                if k not in ("model", "max_tokens", "messages", "tools", "system", "stream")
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

        # Stream the response
        content_text = ""
        tool_calls: list[ToolCall] = []
        stop_reason = StopReason.END_TURN
        usage: dict[str, int] = {}
        current_tool_id = ""
        current_tool_name = ""
        current_tool_input = ""

        async for line in self._session.post_stream(f"{self._base_url}/messages", payload, headers):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")

            if event_type == "content_block_start":
                block = event.get("content_block", {})
                if block.get("type") == "tool_use":
                    current_tool_id = block.get("id", "")
                    current_tool_name = block.get("name", "")
                    current_tool_input = ""

            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    content_text += text
                    if on_content and text:
                        on_content(text)
                elif delta.get("type") == "input_json_delta":
                    current_tool_input += delta.get("partial_json", "")

            elif event_type == "content_block_stop":
                if current_tool_name:
                    try:
                        args = json.loads(current_tool_input) if current_tool_input else {}
                    except json.JSONDecodeError:
                        args = {"raw": current_tool_input}
                    tool_calls.append(
                        ToolCall(id=current_tool_id, name=current_tool_name, arguments=args)
                    )
                    current_tool_id = ""
                    current_tool_name = ""
                    current_tool_input = ""

            elif event_type == "message_delta":
                sr = event.get("delta", {}).get("stop_reason", "")
                if sr == "tool_use":
                    stop_reason = StopReason.TOOL_USE
                elif sr == "max_tokens":
                    stop_reason = StopReason.MAX_TOKENS
                msg_usage = event.get("usage", {})
                if msg_usage:
                    usage["completion_tokens"] = msg_usage.get("output_tokens", 0)

            elif event_type == "message_start":
                msg_usage = event.get("message", {}).get("usage", {})
                if msg_usage:
                    usage["prompt_tokens"] = msg_usage.get("input_tokens", 0)

        if tool_calls:
            stop_reason = StopReason.TOOL_USE

        usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)

        return ModelResponse(
            content=content_text or None,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            raw={},
            usage=usage if usage.get("total_tokens") else None,
        )
