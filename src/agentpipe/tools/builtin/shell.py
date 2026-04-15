"""Built-in tool: execute shell commands."""

from __future__ import annotations

import asyncio
from typing import Any

from agentpipe.tools.base import Tool, ToolDefinition, ToolParameter


class ShellTool(Tool):
    """Execute a shell command and return its output."""

    def __init__(self, cwd: str | None = None, timeout: float = 120.0) -> None:
        self._cwd = cwd
        self._timeout = timeout

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="shell",
            description="Execute a shell command and return stdout/stderr. Use for running programs, installing packages, running tests, etc.",
            parameters=[
                ToolParameter(
                    name="command", type="string", description="The shell command to execute"
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> str:
        command = kwargs["command"]
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self._timeout)
            output_parts = []
            if stdout:
                output_parts.append(stdout.decode(errors="replace"))
            if stderr:
                output_parts.append(f"STDERR:\n{stderr.decode(errors='replace')}")
            output_parts.append(f"\nExit code: {process.returncode}")
            result = "\n".join(output_parts)
            # Truncate very long output
            if len(result) > 50000:
                result = result[:50000] + "\n... (truncated)"
            return result
        except TimeoutError:
            return f"Error: Command timed out after {self._timeout}s"
        except Exception as e:
            return f"Error executing command: {e}"
