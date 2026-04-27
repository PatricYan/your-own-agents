"""OpenAI-compatible model adapter with streaming and tool calling."""

from __future__ import annotations

import json
from typing import Any

from agentpipe.common import Message, ToolCall, ToolDefinition
from agentpipe.models.http_session import HttpSession
from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason


class OpenAIModelProvider(ModelProvider):
    """Adapter for OpenAI chat completions API with streaming."""

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
        api_key = self._get_api_key()
        params = {**self._default_params, **(parameters or {})}

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

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": api_messages,
            "stream": True,
            **{
                k: v for k, v in params.items() if k not in ("model", "messages", "tools", "stream")
            },
        }
        if tools:
            payload["tools"] = [t.to_openai_schema() for t in tools]

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # Stream the response
        content_text = ""
        tool_calls_by_idx: dict[int, dict[str, str]] = {}
        stop_reason = StopReason.END_TURN
        usage: dict[str, int] = {}

        async for line in self._session.post_stream(
            f"{self._base_url}/chat/completions", payload, headers
        ):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            for choice in event.get("choices", []):
                delta = choice.get("delta", {})
                finish = choice.get("finish_reason")

                # Content
                if "content" in delta and delta["content"]:
                    text = delta["content"]
                    content_text += text
                    if on_content and text:
                        on_content(text)

                # Tool calls
                for tc_delta in delta.get("tool_calls", []):
                    idx = tc_delta.get("index", 0)
                    if idx not in tool_calls_by_idx:
                        tool_calls_by_idx[idx] = {"id": "", "name": "", "arguments": ""}
                    tc = tool_calls_by_idx[idx]
                    if "id" in tc_delta:
                        tc["id"] = tc_delta["id"]
                    func = tc_delta.get("function", {})
                    if "name" in func:
                        tc["name"] = func["name"]
                    if "arguments" in func:
                        tc["arguments"] += func["arguments"]

                # Stop reason
                if finish == "tool_calls":
                    stop_reason = StopReason.TOOL_USE
                elif finish == "length":
                    stop_reason = StopReason.MAX_TOKENS

            # Usage (sometimes in the last chunk)
            if "usage" in event:
                usage = event["usage"]

        # Build tool calls
        tool_calls = []
        for _idx, tc in sorted(tool_calls_by_idx.items()):
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {"raw": tc["arguments"]}
            tool_calls.append(ToolCall(id=tc["id"], name=tc["name"], arguments=args))

        if tool_calls:
            stop_reason = StopReason.TOOL_USE

        return ModelResponse(
            content=content_text or None,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            raw={},
            usage=usage or None,
        )
