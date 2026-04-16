"""Generic HTTP model adapter for multi-turn conversations."""

from __future__ import annotations

import json
from typing import Any

from agentpipe.models.http_session import HttpSession
from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason
from agentpipe.schema import Message, ToolDefinition


class HttpModelProvider(ModelProvider):
    """Adapter for generic HTTP model endpoints.

    Sends a POST request with the conversation as JSON payload.
    """

    def __init__(
        self,
        base_url: str,
        model: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._headers = headers or {"Content-Type": "application/json"}
        self._session = HttpSession(timeout=timeout)

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> ModelResponse:
        payload: dict[str, Any] = {
            "messages": [m.to_dict() for m in messages],
        }
        if self._model:
            payload["model"] = self._model
        if tools:
            payload["tools"] = [t.to_openai_schema() for t in tools]
        if parameters:
            payload.update(parameters)

        data = await self._session.post_json(self._base_url, payload, self._headers)

        # Extract content from common response formats
        content = ""
        if isinstance(data, dict):
            content = (
                data.get("content", "")
                or data.get("text", "")
                or data.get("response", "")
                or data.get("output", "")
                or json.dumps(data)
            )
        elif isinstance(data, str):
            content = data
        else:
            content = str(data)

        return ModelResponse(
            content=content,
            stop_reason=StopReason.END_TURN,
            raw=data if isinstance(data, dict) else {"raw": data},
        )
