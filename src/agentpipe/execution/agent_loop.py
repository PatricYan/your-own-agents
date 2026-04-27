"""Agent loop: the core think-act-observe cycle for autonomous task execution.

Each task in the pipeline runs as an autonomous agent. The agent loop:
1. Initializes a conversation with the system prompt + goal + input data
2. Sends the conversation to the model (with tool definitions)
3. If the model returns tool calls -> executes each tool, appends results
4. If the model returns content with no tool calls -> checks if done
5. If the agent calls submit_result -> extracts the final output, loop ends
6. Repeats until goal is met, submit_result is called, or limits are hit

**Human-in-the-loop**: The ``on_before_iteration`` callback fires before each
iteration. It receives the current task definition and can return a modified
copy — allowing a user to update permissions, system_prompt, goal, or tools
while the agent is running.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from agentpipe.common import Conversation, ToolCall
from agentpipe.core.task import PermissionLevel, TaskDefinition
from agentpipe.models.provider import ModelProvider, StopReason
from agentpipe.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ---- callback protocols ----


class IterationCallback(Protocol):
    """Notifies the caller after each iteration completes."""

    def __call__(self, iteration: int, phase: str, details: list[dict]) -> None: ...


class BeforeIterationHook(Protocol):
    """Called before each iteration. Return a modified task to change behaviour mid-run.

    Return ``None`` to keep the current task unchanged.
    """

    def __call__(self, iteration: int, task: TaskDefinition) -> TaskDefinition | None: ...


# ---- data classes ----


@dataclass
class IterationRecord:
    """Record of a single think-act-observe iteration."""

    iteration: int
    model_content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""


@dataclass
class AgentLoopResult:
    """Result of running the agent loop."""

    output: dict[str, Any]
    iterations: int
    total_tool_calls: int
    conversation: Conversation
    iteration_log: list[IterationRecord] = field(default_factory=list)
    completed: bool = True
    error: str | None = None
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


# ---- agent loop ----


class AgentLoop:
    """Runs an autonomous agent loop for a single task.

    The agent uses a model as its brain and tools to accomplish its goal.
    Permissions are enforced at execution time — the model only sees tools it
    is allowed to use, and any tool call outside the permitted set is blocked.

    Human-in-the-loop: supply ``on_before_iteration`` to inspect or modify the
    task (permissions, prompt, goal, tools) before every iteration.
    """

    def __init__(
        self,
        provider: ModelProvider,
        tool_registry: ToolRegistry,
        on_iteration: IterationCallback | None = None,
        on_before_iteration: BeforeIterationHook | None = None,
        on_content: Any | None = None,
        on_tool_call: Any | None = None,
        on_permission_ask: Any | None = None,
        log_writer: Any | None = None,
    ) -> None:
        self._provider = provider
        self._tool_registry = tool_registry
        self._on_iteration = on_iteration
        self._on_before_iteration = on_before_iteration
        self._on_content = on_content
        self._on_tool_call = on_tool_call
        self._on_permission_ask = on_permission_ask
        self._log_writer = log_writer

    async def run(
        self,
        task: TaskDefinition,
        input_data: dict[str, Any],
    ) -> AgentLoopResult:
        """Run the agent loop for a task until completion or limits."""
        conversation = Conversation()
        iteration_log: list[IterationRecord] = []
        total_tool_calls = 0
        total_tokens = 0
        prompt_tokens = 0
        completion_tokens = 0

        # Build system prompt
        system = self._build_system_prompt(task, input_data)
        conversation.add_system(system)
        if self._log_writer:
            self._log_writer.log_system_prompt(system)

        # Build initial user message
        initial_msg = self._build_initial_message(task, input_data)
        conversation.add_user(initial_msg)
        if self._log_writer:
            self._log_writer.log_user_message(initial_msg)

        # Get the submit_result tool for detecting completion
        submit_tool = self._get_submit_tool()

        for iteration in range(task.max_iterations):
            # ---- human-in-the-loop: allow mid-run changes (supports sync and async) ----
            if self._on_before_iteration is not None:
                import inspect

                result = self._on_before_iteration(iteration, task)
                if inspect.isawaitable(result):
                    updated = await result
                else:
                    updated = result
                if updated is not None:
                    # Apply changes — rebuild system prompt if goal/prompt changed
                    old_goal, old_prompt = task.goal, task.system_prompt
                    task = updated
                    if task.goal != old_goal or task.system_prompt != old_prompt:
                        update_msg = (
                            f"[System update] Your instructions have been updated.\n\n"
                            f"**New goal**: {task.goal}"
                            + (
                                f"\n\n**New instructions**: {task.system_prompt}"
                                if task.system_prompt
                                else ""
                            )
                        )
                        conversation.add_user(update_msg)
                        if self._log_writer:
                            self._log_writer.log_user_message(update_msg)
                        logger.info(
                            "Agent '%s': task updated at iteration %d",
                            task.name,
                            iteration,
                        )

            # Resolve per-task permissions → allowed tools
            allowed_tools = self._resolve_allowed_tools(task)
            tool_defs = self._tool_registry.get_definitions(list(allowed_tools))

            # --- Token budget check: stop if total tokens exceed budget ---
            if task.max_tokens and total_tokens >= task.max_tokens:
                logger.warning(
                    "Agent '%s' hit token budget (%d/%d) at iteration %d",
                    task.name,
                    total_tokens,
                    task.max_tokens,
                    iteration,
                )
                break

            # --- Context window management: trim conversation if too large ---
            if task.context_window:
                trimmed = conversation.trim_to_budget(task.context_window)
                if trimmed > 0:
                    logger.info(
                        "Agent '%s': trimmed %d messages to fit context window (%d tokens)",
                        task.name,
                        trimmed,
                        task.context_window,
                    )

            record = IterationRecord(iteration=iteration)

            # Think: send conversation to model
            try:
                response = await self._provider.chat(
                    conversation.messages, tools=tool_defs, on_content=self._on_content
                )
            except Exception as e:
                logger.error(
                    "Agent '%s' model call failed at iteration %d: %s", task.name, iteration, e
                )
                return AgentLoopResult(
                    output={"error": str(e)},
                    iterations=iteration + 1,
                    total_tool_calls=total_tool_calls,
                    conversation=conversation,
                    iteration_log=iteration_log,
                    completed=False,
                    error=str(e),
                )

            record.model_content = response.content
            record.stop_reason = response.stop_reason.value

            # Log the model's full response
            if self._log_writer:
                tc_dicts = (
                    [{"name": tc.name, "arguments": tc.arguments} for tc in response.tool_calls]
                    if response.tool_calls
                    else []
                )
                self._log_writer.log_model_response(
                    response.content, tc_dicts, response.stop_reason.value
                )

            # Track token usage
            if response.usage:
                total_tokens += response.usage.get("total_tokens", 0)
                prompt_tokens += response.usage.get("prompt_tokens", 0)
                completion_tokens += response.usage.get("completion_tokens", 0)

            # If model returned content without tool calls → re-prompt to use tools
            # The agent must call submit_result to complete. Plain text is not enough.
            if response.stop_reason == StopReason.END_TURN and not response.tool_calls:
                conversation.add_assistant(content=response.content)
                reprompt = (
                    "You must use tools to accomplish your goal. "
                    "When you are done, call the submit_result tool with your final output as JSON. "
                    "Do not just respond with text — use the available tools."
                )
                conversation.add_user(reprompt)
                if self._log_writer:
                    self._log_writer.log_user_message(reprompt)
                iteration_log.append(record)
                if self._on_iteration:
                    self._on_iteration(iteration, "re-prompting", [])
                continue

            # Act: execute tool calls
            if response.tool_calls:
                conversation.add_assistant(content=response.content, tool_calls=response.tool_calls)

                for tc in response.tool_calls:
                    # Pause check before each tool execution (not just between iterations)
                    # so that pause takes effect mid-iteration instead of waiting for the
                    # entire iteration to finish.
                    if self._on_before_iteration is not None:
                        import inspect

                        mid_result = self._on_before_iteration(iteration, task)
                        if inspect.isawaitable(mid_result):
                            mid_updated = await mid_result
                        else:
                            mid_updated = mid_result
                        if mid_updated is not None:
                            task = mid_updated

                    total_tool_calls += 1
                    if task.max_tool_calls and total_tool_calls > task.max_tool_calls:
                        conversation.add_tool_result(
                            tc.id, "Error: Maximum tool call limit reached.", is_error=True
                        )
                        continue

                    if self._on_tool_call:
                        self._on_tool_call(tc.name, tc.arguments)
                    result_text = await self._execute_tool(tc, allowed_tools, task.permissions)
                    conversation.add_tool_result(tc.id, result_text)

                    # Log tool call + result
                    if self._log_writer:
                        self._log_writer.log_tool_call(tc.name, tc.arguments, result_text)
                        self._log_writer.log_tool_result(tc.id, result_text)

                    # Show permission denials to the user
                    if result_text.startswith("Error:") and self._on_content:
                        self._on_content(f"\n  ✗ {result_text}\n")

                    record.tool_calls.append({"name": tc.name, "arguments": tc.arguments})
                    record.tool_results.append(
                        {"tool_call_id": tc.id, "content": result_text[:500]}
                    )

                    # Check if submit_result was called
                    if tc.name == "submit_result" and submit_tool is not None:
                        from agentpipe.tools.builtin.submit_result import SubmitResultTool

                        if (
                            isinstance(submit_tool, SubmitResultTool)
                            and submit_tool.last_result is not None
                        ):
                            iteration_log.append(record)
                            if self._log_writer:
                                self._log_writer.log_iteration(
                                    iteration,
                                    record.model_content,
                                    record.tool_calls,
                                    record.tool_results,
                                )
                            return AgentLoopResult(
                                output=self._parse_final_output(submit_tool.last_result),
                                iterations=iteration + 1,
                                total_tool_calls=total_tool_calls,
                                conversation=conversation,
                                iteration_log=iteration_log,
                                completed=True,
                                total_tokens=total_tokens,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                            )

                iteration_log.append(record)
                if self._log_writer:
                    self._log_writer.log_iteration(
                        iteration, record.model_content, record.tool_calls, record.tool_results
                    )
                if self._on_iteration:
                    self._on_iteration(
                        iteration, "acting", [{"name": tc.name} for tc in response.tool_calls]
                    )
            else:
                conversation.add_assistant(content=response.content)
                iteration_log.append(record)

        # Loop ended — either max_iterations or token budget
        reason = (
            "Max iterations"
            if not (task.max_tokens and total_tokens >= task.max_tokens)
            else "Token budget"
        )
        logger.warning("Agent '%s': %s reached", task.name, reason)
        last_content = ""
        for msg in reversed(conversation.messages):
            if msg.role == "assistant" and msg.content:
                last_content = msg.content
                break

        return AgentLoopResult(
            output=self._parse_final_output(last_content),
            iterations=len(iteration_log),
            total_tool_calls=total_tool_calls,
            conversation=conversation,
            iteration_log=iteration_log,
            completed=False,
            error=f"{reason} reached",
            total_tokens=total_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    # ---- private helpers ----

    def _resolve_allowed_tools(self, task: TaskDefinition) -> set[str]:
        """Derive the set of tools this task may use.

        Priority: explicit ``tools`` list > ``permissions``-derived list.
        ``submit_result`` is always included.
        """
        effective = task.effective_tools()
        # Filter against what the registry actually has
        available = set(self._tool_registry.list_tools())
        allowed = {t for t in effective if t in available}
        # submit_result always allowed
        if self._tool_registry.has("submit_result"):
            allowed.add("submit_result")
        return allowed

    def _get_submit_tool(self):
        """Return the submit_result tool instance (if registered)."""
        if not self._tool_registry.has("submit_result"):
            return None
        tool = self._tool_registry.get("submit_result")
        from agentpipe.tools.builtin.submit_result import SubmitResultTool

        if isinstance(tool, SubmitResultTool):
            tool.reset()
        return tool

    def _build_system_prompt(self, task: TaskDefinition, input_data: dict[str, Any]) -> str:
        parts = []

        # Agent rules — loaded from AGENTPIPE_RULES env var
        from agentpipe import config

        if config.RULES_FILE:
            rules_path = Path(config.RULES_FILE)
            if rules_path.exists():
                parts.append(rules_path.read_text().strip())

        # User-defined prompts (skills, principles, role instructions)
        combined = task.effective_system_prompt()
        if combined:
            parts.append(combined)

        # Inform the agent of its permissions (OpenCode format)
        perms = task.permissions
        tool_descriptions = {
            "read": "read files",
            "edit": "edit/write/create files",
            "bash": "execute shell commands",
            "glob": "search files by pattern",
            "grep": "search file contents",
            "list": "list directories",
            "webfetch": "fetch URLs from the web",
        }
        perm_lines = []
        for tool_key, desc in tool_descriptions.items():
            level = perms.get_level(tool_key)
            if level == PermissionLevel.ALLOW:
                perm_lines.append(f"- You CAN {desc}")
            elif level == PermissionLevel.DENY:
                perm_lines.append(f"- You CANNOT {desc}")
        if perm_lines:
            parts.append("## Your Permissions\n" + "\n".join(perm_lines))

        if task.output_schema:
            parts.append(f"\nExpected output format: {json.dumps(task.output_schema)}")

        return "\n\n".join(parts)

    def _build_initial_message(self, task: TaskDefinition, input_data: dict[str, Any]) -> str:
        parts = [f"## Goal\n\n{task.goal}"]
        if input_data:
            if len(input_data) == 1 and "text" in input_data:
                parts.append(f"## Input\n\n{input_data['text']}")
            elif len(input_data) == 1 and "input" in input_data:
                parts.append(f"## Input\n\n{input_data['input']}")
            else:
                formatted = json.dumps(input_data, indent=2, default=str)
                parts.append(f"## Input Data\n\n```json\n{formatted}\n```")
        return "\n\n".join(parts)

    async def _execute_tool(
        self, tool_call: ToolCall, allowed_tools: set[str], permissions: Any
    ) -> str:
        """Execute a tool call, enforcing permissions strictly.

        Permission levels:
        - allow: execute immediately
        - ask: prompt user via on_permission_ask callback; deny if no callback
        - deny: block with error message
        """
        if tool_call.name not in allowed_tools:
            return f"Error: Tool '{tool_call.name}' is not permitted for this task"

        # submit_result always bypasses permission checks
        if tool_call.name == "submit_result":
            pass
        else:
            input_value = self._get_tool_input_value(tool_call)

            # Check deny
            if permissions.is_denied(tool_call.name, input_value):
                return (
                    f"Error: '{tool_call.name}' with input '{input_value}' is denied by permissions"
                )

            # Check ask — requires user approval
            if permissions.needs_approval(tool_call.name, input_value):
                if self._on_permission_ask:
                    approved = self._on_permission_ask(tool_call.name, input_value)
                    if not approved:
                        return (
                            f"Error: '{tool_call.name}' with input '{input_value}' "
                            f"was denied by user (permission level: ask)"
                        )
                else:
                    # No callback = non-interactive mode → deny ask-level tools
                    return (
                        f"Error: '{tool_call.name}' requires approval (permission level: ask). "
                        f"Run with --interactive (-i) to approve at runtime."
                    )

        try:
            tool = self._tool_registry.get(tool_call.name)
            return await tool.execute(**tool_call.arguments)
        except KeyError:
            return f"Error: Tool '{tool_call.name}' not found"
        except Exception as e:
            return f"Error executing tool '{tool_call.name}': {e}"

    def _get_tool_input_value(self, tool_call: ToolCall) -> str:
        """Extract the primary input value from a tool call for permission matching.

        Maps tool names to their primary argument (like OpenCode):
        - bash/shell: the command string
        - read/edit/write/glob: the file path or pattern
        - grep: the regex pattern
        - webfetch: the URL
        """
        args = tool_call.arguments
        name = tool_call.name
        if name in ("shell", "bash"):
            return args.get("command", "")
        if name in ("file_read", "read"):
            return args.get("path", "")
        if name in ("edit",):
            return args.get("file_path", "")
        if name in ("file_write", "write"):
            return args.get("path", "")
        if name in ("file_delete",):
            return args.get("path", "")
        if name in ("glob",):
            return args.get("pattern", "")
        if name in ("grep",):
            return args.get("pattern", "")
        if name in ("web_fetch", "webfetch"):
            return args.get("url", "")
        return ""

    def _parse_final_output(self, content: str | None) -> dict[str, Any]:
        if not content:
            return {}
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return {"text": content}
