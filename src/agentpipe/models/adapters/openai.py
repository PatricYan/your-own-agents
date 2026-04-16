"""OpenAI-compatible model adapter with tool/function calling support."""

from __future__ import annotations

import json
import os
from typing import Any

from agentpipe.models.http_session import HttpSession
from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason
from agentpipe.schema import Message, ToolCall, ToolDefinition


class OpenAIModelProvider(ModelProvider):
    """Adapter for OpenAI chat completions API and compatible endpoints."""

    def __init__(
        self,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
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

        api_messages = _build_messages(messages)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": api_messages,
            **{k: v for k, v in params.items() if k not in ("model", "messages", "tools")},
        }
        if tools:
            payload["tools"] = [t.to_openai_schema() for t in tools]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        data = await self._session.post_json(f"{self._base_url}/chat/completions", payload, headers)
        return _parse_response(data)


def _build_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert Message objects to OpenAI API format."""
    api_messages = []
    for msg in messages:
        m: dict[str, Any] = {"role": msg.role}
        if msg.content is not None:
            m["content"] = msg.content
        if msg.tool_calls:
            m["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in msg.tool_calls
            ]
        if msg.tool_call_id:
            m["tool_call_id"] = msg.tool_call_id
        api_messages.append(m)
    return api_messages


def _parse_response(data: dict[str, Any]) -> ModelResponse:
    """Parse OpenAI API response into ModelResponse."""
    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    finish_reason = choice.get("finish_reason", "stop")

    tool_calls = []
    for tc in message.get("tool_calls", []):
        func = tc.get("function", {})
        try:
            args = json.loads(func.get("arguments", "{}"))
        except json.JSONDecodeError:
            args = {"raw": func.get("arguments", "")}
        tool_calls.append(ToolCall(id=tc["id"], name=func["name"], arguments=args))

    stop_reason = StopReason.TOOL_USE if tool_calls else StopReason.END_TURN
    if finish_reason == "length":
        stop_reason = StopReason.MAX_TOKENS

    return ModelResponse(
        content=message.get("content"),
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        raw=data,
        usage=data.get("usage"),
    )
