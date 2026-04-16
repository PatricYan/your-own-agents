"""Unit tests for agentpipe.tools — each tool independently testable."""

import pytest

from agentpipe.tools.registry import ToolRegistry, create_default_registry


class TestToolRegistry:
    def test_create_default_has_10_tools(self):
        reg = create_default_registry()
        assert len(reg.list_tools()) == 10

    def test_expected_tool_names(self):
        reg = create_default_registry()
        names = sorted(reg.list_tools())
        assert names == [
            "edit",
            "file_delete",
            "file_read",
            "file_write",
            "glob",
            "grep",
            "list",
            "shell",
            "submit_result",
            "web_fetch",
        ]

    def test_get_existing_tool(self):
        reg = create_default_registry()
        tool = reg.get("file_read")
        assert tool.definition.name == "file_read"

    def test_get_missing_tool(self):
        reg = create_default_registry()
        with pytest.raises(KeyError):
            reg.get("nonexistent")

    def test_has(self):
        reg = create_default_registry()
        assert reg.has("shell")
        assert not reg.has("nonexistent")

    def test_get_definitions(self):
        reg = create_default_registry()
        defs = reg.get_definitions(["file_read", "shell"])
        assert len(defs) == 2
        assert {d.name for d in defs} == {"file_read", "shell"}

    def test_openai_schemas(self):
        reg = create_default_registry()
        schemas = reg.get_openai_schemas(["file_read"])
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"

    def test_register_custom_tool(self):
        from agentpipe.tools.base import Tool, ToolDefinition

        class CustomTool(Tool):
            @property
            def definition(self):
                return ToolDefinition(name="custom", description="custom tool")

            async def execute(self, **kwargs):
                return "custom result"

        reg = ToolRegistry()
        reg.register(CustomTool())
        assert reg.has("custom")


class TestFileReadTool:
    @pytest.mark.asyncio
    async def test_read_file(self, tmp_path):
        from agentpipe.tools.builtin.file_read import FileReadTool

        (tmp_path / "test.txt").write_text("hello\nworld\n")
        tool = FileReadTool(base_dir=str(tmp_path))
        result = await tool.execute(path="test.txt")
        assert "hello" in result
        assert "world" in result

    @pytest.mark.asyncio
    async def test_read_missing_file(self, tmp_path):
        from agentpipe.tools.builtin.file_read import FileReadTool

        tool = FileReadTool(base_dir=str(tmp_path))
        result = await tool.execute(path="missing.txt")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_read_with_offset_limit(self, tmp_path):
        from agentpipe.tools.builtin.file_read import FileReadTool

        (tmp_path / "data.txt").write_text("a\nb\nc\nd\ne\n")
        tool = FileReadTool(base_dir=str(tmp_path))
        result = await tool.execute(path="data.txt", offset=2, limit=2)
        assert "b" in result
        assert "c" in result
        assert "a" not in result


class TestEditTool:
    @pytest.mark.asyncio
    async def test_edit_file(self, tmp_path):
        from agentpipe.tools.builtin.edit import EditTool

        f = tmp_path / "code.py"
        f.write_text("return 1\n")
        tool = EditTool(base_dir=str(tmp_path))
        result = await tool.execute(
            file_path="code.py", old_string="return 1", new_string="return 42"
        )
        assert "Successfully" in result
        assert "return 42" in f.read_text()

    @pytest.mark.asyncio
    async def test_edit_not_found(self, tmp_path):
        from agentpipe.tools.builtin.edit import EditTool

        (tmp_path / "f.py").write_text("hello")
        tool = EditTool(base_dir=str(tmp_path))
        result = await tool.execute(file_path="f.py", old_string="xyz", new_string="abc")
        assert "not found" in result


class TestFileWriteTool:
    @pytest.mark.asyncio
    async def test_write_file(self, tmp_path):
        from agentpipe.tools.builtin.file_write import FileWriteTool

        tool = FileWriteTool(base_dir=str(tmp_path))
        result = await tool.execute(path="out.txt", content="hello")
        assert "Successfully" in result
        assert (tmp_path / "out.txt").read_text() == "hello"


class TestFileDeleteTool:
    @pytest.mark.asyncio
    async def test_delete_file(self, tmp_path):
        from agentpipe.tools.builtin.file_delete import FileDeleteTool

        f = tmp_path / "del.txt"
        f.write_text("bye")
        tool = FileDeleteTool(base_dir=str(tmp_path))
        result = await tool.execute(path="del.txt")
        assert "Successfully" in result
        assert not f.exists()


class TestShellTool:
    @pytest.mark.asyncio
    async def test_echo(self):
        from agentpipe.tools.builtin.shell import ShellTool

        tool = ShellTool()
        result = await tool.execute(command="echo hello_shell")
        assert "hello_shell" in result


class TestGlobTool:
    @pytest.mark.asyncio
    async def test_glob(self, tmp_path):
        from agentpipe.tools.builtin.glob import GlobTool

        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.txt").write_text("")
        tool = GlobTool(base_dir=str(tmp_path))
        result = await tool.execute(pattern="*.py")
        assert "a.py" in result
        assert "c.txt" not in result


class TestGrepTool:
    @pytest.mark.asyncio
    async def test_grep(self, tmp_path):
        from agentpipe.tools.builtin.grep import GrepTool

        (tmp_path / "test.py").write_text("def hello():\n    pass\ndef world():\n    pass\n")
        tool = GrepTool(base_dir=str(tmp_path))
        result = await tool.execute(pattern="def .*world")
        assert "world" in result


class TestListDirTool:
    @pytest.mark.asyncio
    async def test_list(self, tmp_path):
        from agentpipe.tools.builtin.list_dir import ListDirTool

        (tmp_path / "file.txt").write_text("")
        (tmp_path / "subdir").mkdir()
        tool = ListDirTool(base_dir=str(tmp_path))
        result = await tool.execute()
        assert "subdir/" in result
        assert "file.txt" in result


class TestSubmitResultTool:
    @pytest.mark.asyncio
    async def test_submit(self):
        from agentpipe.tools.builtin.submit_result import SubmitResultTool

        tool = SubmitResultTool()
        tool.reset()
        assert tool.last_result is None
        await tool.execute(result='{"answer": 42}')
        assert tool.last_result == '{"answer": 42}'
