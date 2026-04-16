"""Unit tests for agentpipe.schema — shared data types (no dependencies)."""

from agentpipe.schema import (
    Conversation,
    Message,
    ToolCall,
    ToolDefinition,
    ToolParameter,
    ToolResult,
)


class TestMessage:
    def test_basic_message(self):
        m = Message(role="user", content="hello")
        assert m.role == "user"
        assert m.content == "hello"
        assert m.tool_calls is None

    def test_to_dict_simple(self):
        m = Message(role="assistant", content="hi")
        d = m.to_dict()
        assert d == {"role": "assistant", "content": "hi"}

    def test_to_dict_with_tool_calls(self):
        m = Message(
            role="assistant",
            content="I'll read the file",
            tool_calls=[ToolCall(id="c1", name="file_read", arguments={"path": "a.txt"})],
        )
        d = m.to_dict()
        assert len(d["tool_calls"]) == 1
        assert d["tool_calls"][0]["name"] == "file_read"

    def test_to_dict_tool_result(self):
        m = Message(role="tool", content="file contents", tool_call_id="c1")
        d = m.to_dict()
        assert d["role"] == "tool"
        assert d["tool_call_id"] == "c1"


class TestConversation:
    def test_empty(self):
        c = Conversation()
        assert c.messages == []
        assert c.to_list() == []

    def test_add_messages(self):
        c = Conversation()
        c.add_system("you are an agent")
        c.add_user("do something")
        c.add_assistant(content="I'll use a tool")
        c.add_tool_result("c1", "tool output")
        assert len(c.messages) == 4
        assert c.messages[0].role == "system"
        assert c.messages[3].role == "tool"

    def test_to_list(self):
        c = Conversation()
        c.add_user("hi")
        lst = c.to_list()
        assert lst == [{"role": "user", "content": "hi"}]

    def test_token_estimate(self):
        c = Conversation()
        c.add_user("a" * 400)
        assert c.token_estimate() == 100


class TestToolCall:
    def test_fields(self):
        tc = ToolCall(id="c1", name="shell", arguments={"command": "ls"})
        assert tc.id == "c1"
        assert tc.name == "shell"
        assert tc.arguments == {"command": "ls"}


class TestToolResult:
    def test_fields(self):
        tr = ToolResult(tool_call_id="c1", content="output", is_error=False)
        assert tr.tool_call_id == "c1"
        assert not tr.is_error


class TestToolDefinition:
    def test_basic(self):
        td = ToolDefinition(name="my_tool", description="does stuff")
        assert td.name == "my_tool"
        assert td.parameters == []

    def test_openai_schema(self):
        td = ToolDefinition(
            name="file_read",
            description="Read a file",
            parameters=[ToolParameter(name="path", type="string", description="file path")],
        )
        schema = td.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "file_read"
        assert "path" in schema["function"]["parameters"]["properties"]
        assert "path" in schema["function"]["parameters"]["required"]

    def test_anthropic_schema(self):
        td = ToolDefinition(
            name="shell",
            description="Run command",
            parameters=[ToolParameter(name="command", type="string", description="cmd")],
        )
        schema = td.to_anthropic_schema()
        assert schema["name"] == "shell"
        assert "command" in schema["input_schema"]["properties"]

    def test_optional_parameter(self):
        td = ToolDefinition(
            name="test",
            description="test",
            parameters=[
                ToolParameter(name="req", type="string", description="required"),
                ToolParameter(name="opt", type="string", description="optional", required=False),
            ],
        )
        schema = td.to_openai_schema()
        assert "req" in schema["function"]["parameters"]["required"]
        assert "opt" not in schema["function"]["parameters"]["required"]


class TestBackwardCompatibility:
    """Verify old import paths still work."""

    def test_import_from_execution_conversation(self):
        from agentpipe.execution.conversation import Conversation, Message

        assert Message is not None
        assert Conversation is not None

    def test_import_from_tools_base(self):
        from agentpipe.tools.base import ToolDefinition, ToolParameter

        assert ToolDefinition is not None
        assert ToolParameter is not None

    def test_identity_equality(self):
        """Schema types and backward-compat re-exports are the same objects."""
        from agentpipe.execution.conversation import Message as MsgOld
        from agentpipe.schema import Message as MsgNew

        assert MsgOld is MsgNew
