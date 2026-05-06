"""Built-in tool: fetch URL content."""

from __future__ import annotations

from typing import Any

import httpx

from agentpipe.tools.base import Tool, ToolDefinition, ToolParameter


class WebFetchTool(Tool):
    """Fetch content from a URL."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_fetch",
            description="Fetch the content of a URL and return it as text.",
            parameters=[
                ToolParameter(name="url", type="string", description="The URL to fetch"),
            ],
        )

    async def execute(self, **kwargs: Any) -> str:
        url = kwargs["url"]
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.text
                if len(content) > 50000:
                    content = content[:50000] + "\n... (truncated)"
                return content
        except Exception as e:
            return f"Error fetching URL: {e}"
