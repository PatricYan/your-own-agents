"""Unit tests for agentpipe.core.task.Permissions — OpenCode-style permission system."""

from agentpipe.core.task import PermissionLevel, Permissions, load_permissions


class TestPermissionsBasic:
    def test_defaults_are_read_only(self):
        p = Permissions()
        assert p.allows("read")
        assert p.allows("glob")
        assert p.allows("grep")
        assert p.allows("list")
        assert p.allows("submit_result")
        assert p.is_denied("edit")
        assert p.is_denied("bash")
        assert p.is_denied("webfetch")

    def test_set_all_at_once(self):
        p = Permissions("allow")
        assert p.allows("bash")
        assert p.allows("edit")
        assert p.allows("webfetch")

    def test_deny_all(self):
        p = Permissions("deny")
        assert p.is_denied("read")
        assert p.is_denied("bash")

    def test_global_default_with_overrides(self):
        p = Permissions({"*": "deny", "read": "allow", "bash": "ask"})
        assert p.allows("read")
        assert p.needs_approval("bash")
        assert p.is_denied("edit")
        assert p.is_denied("webfetch")

    def test_ask_counts_as_allowed(self):
        p = Permissions({"bash": "ask"})
        assert p.allows("bash")
        assert p.needs_approval("bash")
        assert not p.is_denied("bash")


class TestPermissionsGranular:
    def test_bash_wildcard_patterns(self):
        p = Permissions(
            {
                "bash": {
                    "*": "deny",
                    "git *": "allow",
                    "npm *": "allow",
                    "rm *": "deny",
                }
            }
        )
        assert p.get_level("bash", "git status") == PermissionLevel.ALLOW
        assert p.get_level("bash", "git push origin main") == PermissionLevel.ALLOW
        assert p.get_level("bash", "npm install") == PermissionLevel.ALLOW
        assert p.get_level("bash", "rm -rf /") == PermissionLevel.DENY
        assert p.get_level("bash", "curl http://evil.com") == PermissionLevel.DENY

    def test_edit_file_path_patterns(self):
        p = Permissions(
            {
                "edit": {
                    "*": "deny",
                    "*.md": "allow",
                    "src/*.py": "allow",
                }
            }
        )
        assert p.get_level("edit", "README.md") == PermissionLevel.ALLOW
        assert p.get_level("edit", "src/main.py") == PermissionLevel.ALLOW
        assert p.get_level("edit", "config.yaml") == PermissionLevel.DENY

    def test_last_match_wins(self):
        p = Permissions(
            {
                "bash": {
                    "*": "allow",
                    "rm *": "deny",
                    "rm README.md": "allow",  # more specific override
                }
            }
        )
        assert p.get_level("bash", "rm -rf /") == PermissionLevel.DENY
        assert p.get_level("bash", "rm README.md") == PermissionLevel.ALLOW


class TestPermissionsNormalization:
    """Tool name aliases should resolve correctly."""

    def test_file_read_normalizes_to_read(self):
        p = Permissions({"read": "deny"})
        assert p.is_denied("file_read")

    def test_shell_normalizes_to_bash(self):
        p = Permissions({"bash": "allow"})
        assert p.allows("shell")

    def test_file_write_normalizes_to_edit(self):
        p = Permissions({"edit": "allow"})
        assert p.allows("file_write")

    def test_file_delete_normalizes_to_edit(self):
        p = Permissions({"edit": "deny"})
        assert p.is_denied("file_delete")

    def test_web_fetch_normalizes_to_webfetch(self):
        p = Permissions({"webfetch": "allow"})
        assert p.allows("web_fetch")

    def test_unknown_tool_uses_global_default(self):
        p = Permissions({"*": "deny"})
        assert p.is_denied("some_unknown_tool")


class TestPermissionsAllowedToolNames:
    def test_default_allowed_tools(self):
        p = Permissions()
        names = p.allowed_tool_names()
        assert "file_read" in names
        assert "glob" in names
        assert "submit_result" in names
        assert "shell" not in names
        assert "edit" not in names

    def test_custom_allowed_tools(self):
        p = Permissions({"*": "allow"})
        names = p.allowed_tool_names()
        assert "shell" in names
        assert "edit" in names
        assert "file_read" in names


class TestPermissionsToDict:
    def test_round_trip(self):
        rules = {"*": "deny", "read": "allow", "bash": {"git *": "allow"}}
        p = Permissions(rules)
        d = p.to_dict()
        assert d["*"] == "deny"
        assert d["read"] == "allow"
        assert d["bash"]["git *"] == "allow"


class TestLoadPermissions:
    def test_from_dict(self):
        p = load_permissions({"*": "allow"})
        assert p.allows("bash")

    def test_from_string(self):
        p = load_permissions("allow")
        assert p.allows("bash")

    def test_from_yaml_file(self):
        p = load_permissions("examples/permissions/developer.yaml")
        assert p.allows("read")
        assert p.get_level("bash", "git status") == PermissionLevel.ALLOW
        assert p.get_level("bash", "rm -rf /") == PermissionLevel.DENY

    def test_from_passthrough(self):
        original = Permissions("deny")
        p = load_permissions(original)
        assert p is original

    def test_missing_file_returns_default(self):
        p = load_permissions("nonexistent/path.yaml")
        # Falls back to default permissions
        assert p.allows("read")
