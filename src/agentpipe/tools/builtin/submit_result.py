"""Built-in tool: agent signals task completion with final output."""

from __future__ import annotations

from typing import Any

from agentpipe.tools.base import Tool, ToolDefinition, ToolParameter


class SubmitResultTool(Tool):
    """Signal that the agent has completed its task and submit the final result.

    When the agent calls this tool, the agentic loop ends and the provided
    result becomes the task's output.
    """

    def __init__(self) -> None:
        self._last_result: str | None = None

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="submit_result",
            description="Call this tool when you have completed the task. Provide the final result as a JSON string.",
            parameters=[
                ToolParameter(
                    name="result",
                    type="string",
                    description="The final result of the task as a JSON string or plain text",
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> str:
        self._last_result = kwargs.get("result", "")
        return "Result submitted successfully. Task complete."

    @property
    def last_result(self) -> str | None:
        return self._last_result

    def reset(self) -> None:
        self._last_result = None
