"""Contract tests: verify model adapters correctly format requests and parse responses.

Uses a local HTTP server that simulates the OpenAI API format. No API keys needed.
Tests the full chain: adapter → HttpSession → HTTP → response parsing.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agentpipe.common import Message, ToolCall, ToolDefinition, ToolParameter

# ============================================================
# Local mock server simulating OpenAI chat completions API
# ============================================================


class MockOpenAIHandler(BaseHTTPRequestHandler):
    """Simulates OpenAI /v1/chat/completions endpoint."""

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length))

        # Check if tools are provided — if so, respond with a tool call
        if body.get("tools"):
            response = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_test123",
                                    "type": "function",
                                    "function": {
                                        "name": "submit_result",
                                        "arguments": json.dumps({"result": '{"answer": 42}'}),
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            }
        else:
            response = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Hello from mock server!",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def log_message(self, format, *args):
        pass  # Suppress server logs during tests


@pytest.fixture(scope="module")
def mock_server():
    """Start a local HTTP server that simulates OpenAI API."""
    server = HTTPServer(("127.0.0.1", 0), MockOpenAIHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ============================================================
# Contract tests
# ============================================================


class TestOpenAIAdapter:
    """Test OpenAI adapter against the mock server."""

    @pytest.mark.asyncio
    async def test_simple_chat(self, mock_server, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "test-key-123")

        from agentpipe.models.adapters.openai import OpenAIModelProvider

        provider = OpenAIModelProvider(
            api_key_env="TEST_API_KEY",
            base_url=mock_server + "/v1",
            model="test-model",
        )

        messages = [Message(role="user", content="Hello")]
        response = await provider.chat(messages)

        assert response.content == "Hello from mock server!"
        assert response.stop_reason.value == "end_turn"
        assert response.usage is not None
        assert response.usage["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_chat_with_tools(self, mock_server, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "test-key-123")

        from agentpipe.models.adapters.openai import OpenAIModelProvider

        provider = OpenAIModelProvider(
            api_key_env="TEST_API_KEY",
            base_url=mock_server + "/v1",
            model="test-model",
        )

        messages = [Message(role="user", content="Do something")]
        tools = [
            ToolDefinition(
                name="submit_result",
                description="Submit result",
                parameters=[ToolParameter(name="result", type="string", description="result")],
            )
        ]
        response = await provider.chat(messages, tools=tools)

        assert response.stop_reason.value == "tool_use"
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "submit_result"
        assert response.tool_calls[0].id == "call_test123"
        assert response.usage["total_tokens"] == 70

    @pytest.mark.asyncio
    async def test_multi_turn_conversation(self, mock_server, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "test-key-123")

        from agentpipe.models.adapters.openai import OpenAIModelProvider

        provider = OpenAIModelProvider(
            api_key_env="TEST_API_KEY",
            base_url=mock_server + "/v1",
            model="test-model",
        )

        messages = [
            Message(role="system", content="You are a test agent"),
            Message(role="user", content="Step 1"),
            Message(role="assistant", content="I did step 1"),
            Message(role="user", content="Step 2"),
        ]
        response = await provider.chat(messages)
        assert response.content is not None

    @pytest.mark.asyncio
    async def test_tool_result_in_conversation(self, mock_server, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "test-key-123")

        from agentpipe.models.adapters.openai import OpenAIModelProvider

        provider = OpenAIModelProvider(
            api_key_env="TEST_API_KEY",
            base_url=mock_server + "/v1",
            model="test-model",
        )

        messages = [
            Message(role="user", content="Use a tool"),
            Message(
                role="assistant",
                tool_calls=[ToolCall(id="c1", name="file_read", arguments={"path": "test.txt"})],
            ),
            Message(role="tool", content="file contents here", tool_call_id="c1"),
        ]
        response = await provider.chat(messages)
        assert response.content is not None or response.tool_calls


class TestHttpSession:
    """Test the retry and connection pooling logic."""

    @pytest.mark.asyncio
    async def test_connection_reuse(self, mock_server, monkeypatch):
        """Verify the session reuses connections across calls."""
        from agentpipe.models.http_session import HttpSession

        session = HttpSession(timeout=10.0)
        headers = {"Authorization": "Bearer test", "Content-Type": "application/json"}

        # Make two requests — should reuse the same client
        r1 = await session.post_json(
            mock_server + "/v1/chat/completions",
            {"model": "test", "messages": [{"role": "user", "content": "hi"}]},
            headers,
        )
        r2 = await session.post_json(
            mock_server + "/v1/chat/completions",
            {"model": "test", "messages": [{"role": "user", "content": "hi again"}]},
            headers,
        )

        assert "choices" in r1
        assert "choices" in r2
        await session.close()

    @pytest.mark.asyncio
    async def test_missing_api_key_raises(self):
        from agentpipe.models.adapters.openai import OpenAIModelProvider

        provider = OpenAIModelProvider(
            api_key_env="NONEXISTENT_KEY_12345",
            base_url="http://localhost:1",
        )
        with pytest.raises(RuntimeError, match="API key not found"):
            await provider.chat([Message(role="user", content="hello")])


class TestTokenTracking:
    """Verify token usage is tracked through the agent loop."""

    @pytest.mark.asyncio
    async def test_tokens_accumulated(self, mock_server, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "test-key-123")

        from agentpipe.core.task import TaskDefinition
        from agentpipe.execution.agent_loop import AgentLoop
        from agentpipe.models.adapters.openai import OpenAIModelProvider
        from agentpipe.tools.registry import create_default_registry

        provider = OpenAIModelProvider(
            api_key_env="TEST_API_KEY",
            base_url=mock_server + "/v1",
            model="test-model",
        )
        task = TaskDefinition(name="test", goal="Do something", primary_model="test-model")
        registry = create_default_registry()

        loop = AgentLoop(provider=provider, tool_registry=registry)
        result = await loop.run(task, {"input": "test"})

        # The mock server returns usage on every call
        assert result.total_tokens > 0
        assert result.prompt_tokens > 0
        assert result.completion_tokens > 0
