"""Ollama model adapter for locally-hosted models."""

from __future__ import annotations

from typing import Any

from agentpipe.common import Message, ToolCall, ToolDefinition
from agentpipe.models.http_session import HttpSession
from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason


class OllamaModelProvider(ModelProvider):
    """Adapter for Ollama chat API (local models)."""

    def __init__(
        self,
        base_url: str,
        model: str = "",
        default_params: dict[str, Any] | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._default_params = default_params or {}
        self._session = HttpSession(timeout=timeout)

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> ModelResponse:
        params = {**self._default_params, **(parameters or {})}

        api_messages = []
        for msg in messages:
            m: dict[str, Any] = {"role": msg.role, "content": msg.content or ""}
            api_messages.append(m)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": api_messages,
            "stream": False,
        }

        # Map parameters to Ollama options
        options: dict[str, Any] = {}
        if "temperature" in params:
            options["temperature"] = params.pop("temperature")
        if "max_tokens" in params:
            options["num_predict"] = params.pop("max_tokens")
        for k, v in params.items():
            if k not in ("model", "messages", "stream", "tools"):
                options[k] = v
        if options:
            payload["options"] = options

        # Ollama tool support (if tools provided and model supports it)
        if tools:
            payload["tools"] = [t.to_openai_schema() for t in tools]

        data = await self._session.post_json(
            self._base_url, payload, {"Content-Type": "application/json"}
        )

        msg_data = data.get("message", {})
        content = msg_data.get("content", "")

        # Parse tool calls from Ollama response
        tool_calls = []
        for tc in msg_data.get("tool_calls", []):
            func = tc.get("function", {})
            tool_calls.append(
                ToolCall(
                    id=f"call_{len(tool_calls)}",
                    name=func.get("name", ""),
                    arguments=func.get("arguments", {}),
                )
            )

        stop_reason = StopReason.TOOL_USE if tool_calls else StopReason.END_TURN

        return ModelResponse(
            content=content or None,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            raw=data,
        )
