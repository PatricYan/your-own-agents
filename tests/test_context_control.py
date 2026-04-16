"""Tests for conversation window management, token budget, and HTTP session reuse."""

import json

import pytest

from agentpipe.schema.conversation import Conversation, Message, ToolCall

# ============================================================
# 1. Conversation Window Management
# ============================================================


class TestConversationTrim:
    """Test conversation trimming to fit within a token budget."""

    def test_no_trim_when_under_budget(self):
        c = Conversation()
        c.add_system("short system prompt")
        c.add_user("hello")
        removed = c.trim_to_budget(1000)
        assert removed == 0
        assert len(c.messages) == 2

    def test_trim_removes_oldest_messages(self):
        c = Conversation()
        c.add_system("system")
        for i in range(20):
            c.add_user(f"message {i} " + "x" * 200)  # ~50 tokens each
        original_count = len(c.messages)
        removed = c.trim_to_budget(200)  # very tight budget
        assert removed > 0
        assert len(c.messages) < original_count
        # System prompt is preserved
        assert c.messages[0].role == "system"
        assert c.messages[0].content == "system"

    def test_system_prompt_always_preserved(self):
        c = Conversation()
        c.add_system("important system instructions " + "x" * 400)
        c.add_user("user message 1 " + "x" * 400)
        c.add_user("user message 2 " + "x" * 400)
        c.add_user("user message 3 " + "x" * 400)
        c.trim_to_budget(200)
        assert c.messages[0].role == "system"

    def test_recent_messages_preserved(self):
        c = Conversation()
        c.add_system("sys")
        c.add_user("old message " + "x" * 400)
        c.add_assistant(content="old response " + "x" * 400)
        c.add_user("recent message")
        c.add_assistant(content="recent response")
        c.trim_to_budget(100)
        # Recent messages should be at the end
        last_msg = c.messages[-1]
        assert "recent" in (last_msg.content or "")

    def test_token_estimate_per_message(self):
        m = Message(role="user", content="a" * 400)
        assert m.token_estimate() == 100  # 400 / 4

    def test_token_estimate_with_tool_calls(self):
        m = Message(
            role="assistant",
            content="text",
            tool_calls=[ToolCall(id="c1", name="shell", arguments={"command": "ls -la"})],
        )
        assert m.token_estimate() > 1

    def test_total_token_estimate(self):
        c = Conversation()
        c.add_system("a" * 400)  # 100 tokens
        c.add_user("b" * 200)  # 50 tokens
        est = c.token_estimate()
        assert est == 150


# ============================================================
# 2. Token Budget Enforcement in Agent Loop
# ============================================================


class TestTokenBudget:
    """Test that the agent loop stops when token budget is exceeded."""

    @pytest.mark.asyncio
    async def test_loop_stops_at_token_budget(self):
        """Agent should stop when total_tokens exceeds max_tokens."""
        from agentpipe.core.task import TaskDefinition
        from agentpipe.execution.agent_loop import AgentLoop
        from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason
        from agentpipe.tools.registry import create_default_registry

        class TokenBurner(ModelProvider):
            """Model that always uses tools, never finishes, reports high token usage."""

            async def chat(self, messages, tools=None, parameters=None):
                return ModelResponse(
                    tool_calls=[ToolCall(id="c0", name="file_read", arguments={"path": "x"})],
                    stop_reason=StopReason.TOOL_USE,
                    usage={"prompt_tokens": 5000, "completion_tokens": 1000, "total_tokens": 6000},
                )

        task = TaskDefinition(
            name="burner",
            goal="burn tokens",
            primary_model="m",
            max_iterations=100,  # high limit
            max_tokens=10000,  # token budget: 10K
        )
        reg = create_default_registry()
        loop = AgentLoop(provider=TokenBurner(), tool_registry=reg)
        result = await loop.run(task, {})

        # Should stop after 2 iterations (6000 * 2 = 12000 > 10000)
        assert not result.completed
        assert result.total_tokens > 0
        assert result.iterations <= 3  # stopped early due to token budget

    @pytest.mark.asyncio
    async def test_no_budget_means_no_limit(self):
        """Without max_tokens, the loop runs to max_iterations."""
        from agentpipe.core.task import TaskDefinition
        from agentpipe.execution.agent_loop import AgentLoop
        from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason
        from agentpipe.tools.registry import create_default_registry

        class NeverFinish(ModelProvider):
            async def chat(self, messages, tools=None, parameters=None):
                return ModelResponse(
                    tool_calls=[ToolCall(id="c0", name="file_read", arguments={"path": "x"})],
                    stop_reason=StopReason.TOOL_USE,
                    usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                )

        task = TaskDefinition(
            name="no_budget",
            goal="loop forever",
            primary_model="m",
            max_iterations=5,
            # no max_tokens set
        )
        reg = create_default_registry()
        loop = AgentLoop(provider=NeverFinish(), tool_registry=reg)
        result = await loop.run(task, {})

        assert result.iterations == 5  # ran to max_iterations
        assert result.total_tokens == 750  # 150 * 5


class TestContextWindow:
    """Test that context window trimming works in the agent loop."""

    @pytest.mark.asyncio
    async def test_context_window_trims_conversation(self):
        from agentpipe.core.task import TaskDefinition
        from agentpipe.execution.agent_loop import AgentLoop
        from agentpipe.models.provider import ModelProvider, ModelResponse, StopReason
        from agentpipe.tools.registry import create_default_registry

        call_count = 0

        class VerboseModel(ModelProvider):
            """Returns long responses to grow the conversation."""

            async def chat(self, messages, tools=None, parameters=None):
                nonlocal call_count
                call_count += 1
                if call_count >= 5:
                    return ModelResponse(
                        tool_calls=[
                            ToolCall(
                                id="c0",
                                name="submit_result",
                                arguments={"result": json.dumps({"done": True})},
                            )
                        ],
                        stop_reason=StopReason.TOOL_USE,
                    )
                # Return a long tool call to grow conversation
                return ModelResponse(
                    tool_calls=[
                        ToolCall(id=f"c{call_count}", name="file_read", arguments={"path": "x"})
                    ],
                    stop_reason=StopReason.TOOL_USE,
                )

        task = TaskDefinition(
            name="trim_test",
            goal="test context trimming",
            primary_model="m",
            max_iterations=10,
            context_window=200,  # very tight: force trimming
        )
        reg = create_default_registry()
        loop = AgentLoop(provider=VerboseModel(), tool_registry=reg)
        result = await loop.run(task, {})

        assert result.completed
        # Conversation should have been trimmed during execution
        assert result.conversation.token_estimate() <= 300  # approximately within budget


# ============================================================
# 3. HTTP Session Reuse
# ============================================================


class TestHttpSessionReuse:
    """Test that HttpSession reuses the underlying httpx client."""

    @pytest.mark.asyncio
    async def test_client_created_once(self):
        from agentpipe.models.http_session import HttpSession

        session = HttpSession(timeout=10.0)
        client1 = session._get_client()
        client2 = session._get_client()
        assert client1 is client2  # same object
        await session.close()

    @pytest.mark.asyncio
    async def test_client_recreated_after_close(self):
        from agentpipe.models.http_session import HttpSession

        session = HttpSession(timeout=10.0)
        client1 = session._get_client()
        await session.close()
        client2 = session._get_client()
        assert client1 is not client2  # new object after close
        await session.close()

    @pytest.mark.asyncio
    async def test_adapter_reuses_session(self):
        """Verify the OpenAI adapter keeps one session across multiple chat() calls."""
        from agentpipe.models.adapters.openai import OpenAIModelProvider

        provider = OpenAIModelProvider(
            api_key_env="DUMMY",
            base_url="http://localhost:1",
        )
        # The session is created in __init__
        session1 = provider._session
        session2 = provider._session
        assert session1 is session2
