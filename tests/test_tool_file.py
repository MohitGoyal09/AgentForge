from __future__ import annotations

from tools.base import ToolInvocation


class TestWriteFileTool:
    async def test_write_new_file(self, write_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        inv = ToolInvocation(params={"path": str(path), "content": "hello"}, cwd=tmp_cwd)
        result = await write_file_tool.execute(inv)
        assert result.success
        assert path.read_text() == "hello"

    async def test_write_summary(self, write_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        inv = ToolInvocation(params={"path": str(path), "content": "hello"}, cwd=tmp_cwd)
        result = await write_file_tool.execute(inv)
        assert result.summary
        assert str(path) in result.summary

    async def test_write_artifacts(self, write_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        inv = ToolInvocation(params={"path": str(path), "content": "hello"}, cwd=tmp_cwd)
        result = await write_file_tool.execute(inv)
        assert len(result.artifacts) == 1
        assert result.artifacts[0] == str(path)

    async def test_write_next_actions(self, write_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        inv = ToolInvocation(params={"path": str(path), "content": "hello"}, cwd=tmp_cwd)
        result = await write_file_tool.execute(inv)
        assert result.next_actions

    async def test_write_to_nonexistent_parent_default_creates_dirs(self, write_file_tool, tmp_cwd):
        path = tmp_cwd / "noexist" / "file.txt"
        inv = ToolInvocation(params={"path": str(path), "content": "hello"}, cwd=tmp_cwd)
        result = await write_file_tool.execute(inv)
        assert result.success
        assert path.exists()
        assert path.read_text() == "hello"

    async def test_overwrite_existing(self, write_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        path.write_text("old")
        inv = ToolInvocation(params={"path": str(path), "content": "new"}, cwd=tmp_cwd)
        result = await write_file_tool.execute(inv)
        assert result.success
        assert path.read_text() == "new"

    async def test_write_metadata_new_file(self, write_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        inv = ToolInvocation(params={"path": str(path), "content": "hello"}, cwd=tmp_cwd)
        result = await write_file_tool.execute(inv)
        assert result.metadata.get("is_new_file") is True
        assert result.metadata.get("lines") == 1

    async def test_write_without_create_dirs_returns_error(self, write_file_tool, tmp_cwd):
        path = tmp_cwd / "a" / "b" / "test.txt"
        inv = ToolInvocation(
            params={"path": str(path), "content": "hello", "create_directories": False},
            cwd=tmp_cwd,
        )
        result = await write_file_tool.execute(inv)
        assert not result.success
        assert "Parent directory" in result.error

    async def test_write_recovery_hint_on_error(self, write_file_tool, tmp_cwd):
        path = tmp_cwd / "noexist" / "f.txt"
        inv = ToolInvocation(
            params={"path": str(path), "content": "hello", "create_directories": False},
            cwd=tmp_cwd,
        )
        result = await write_file_tool.execute(inv)
        assert result.recovery_hint


class TestReadFileTool:
    async def test_read_existing_file(self, read_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        path.write_text("hello\nworld")
        inv = ToolInvocation(params={"path": str(path)}, cwd=tmp_cwd)
        result = await read_file_tool.execute(inv)
        assert result.success
        assert "hello" in result.output
        assert "world" in result.output

    async def test_read_nonexistent_file_returns_error(self, read_file_tool, tmp_cwd):
        path = tmp_cwd / "noexist.txt"
        inv = ToolInvocation(params={"path": str(path)}, cwd=tmp_cwd)
        result = await read_file_tool.execute(inv)
        assert not result.success
        assert result.recovery_hint

    async def test_read_summary(self, read_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        path.write_text("hello")
        inv = ToolInvocation(params={"path": str(path)}, cwd=tmp_cwd)
        result = await read_file_tool.execute(inv)
        assert result.summary

    async def test_read_artifacts(self, read_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        path.write_text("hello")
        inv = ToolInvocation(params={"path": str(path)}, cwd=tmp_cwd)
        result = await read_file_tool.execute(inv)
        assert len(result.artifacts) == 1
        assert result.artifacts[0] == str(path)

    async def test_read_with_offset(self, read_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        path.write_text("\n".join(f"line {i}" for i in range(1, 11)))
        inv = ToolInvocation(params={"path": str(path), "offset": 5, "limit": 3}, cwd=tmp_cwd)
        result = await read_file_tool.execute(inv)
        assert result.success
        assert "line 5" in result.output
        assert "line 7" in result.output

    async def test_read_binary_file_returns_error(self, read_file_tool, tmp_cwd):
        path = tmp_cwd / "test.bin"
        path.write_bytes(bytes(range(256)))
        inv = ToolInvocation(params={"path": str(path)}, cwd=tmp_cwd)
        result = await read_file_tool.execute(inv)
        assert not result.success

    async def test_read_empty_file(self, read_file_tool, tmp_cwd):
        path = tmp_cwd / "empty.txt"
        path.write_text("")
        inv = ToolInvocation(params={"path": str(path)}, cwd=tmp_cwd)
        result = await read_file_tool.execute(inv)
        assert result.success
        assert "empty" in result.output.lower()

    async def test_read_with_limit(self, read_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        path.write_text("\n".join(f"line {i}" for i in range(1, 101)))
        inv = ToolInvocation(params={"path": str(path), "limit": 5}, cwd=tmp_cwd)
        result = await read_file_tool.execute(inv)
        assert result.success
        assert "line 1" in result.output
        assert "line 5" in result.output
        assert "line 6" not in result.output

    async def test_read_next_actions(self, read_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        path.write_text("content")
        inv = ToolInvocation(params={"path": str(path)}, cwd=tmp_cwd)
        result = await read_file_tool.execute(inv)
        assert isinstance(result.next_actions, list)

    async def test_read_recovery_hint_on_not_found(self, read_file_tool, tmp_cwd):
        inv = ToolInvocation(params={"path": str(tmp_cwd / "noexist.txt")}, cwd=tmp_cwd)
        result = await read_file_tool.execute(inv)
        assert result.recovery_hint


class TestAppendFileTool:
    async def test_append_to_existing(self, append_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        path.write_text("line1\n")
        inv = ToolInvocation(params={"path": str(path), "content": "line2"}, cwd=tmp_cwd)
        result = await append_file_tool.execute(inv)
        assert result.success
        assert path.read_text() == "line1\nline2\n"

    async def test_append_to_nonexistent_creates_by_default(self, append_file_tool, tmp_cwd):
        path = tmp_cwd / "noexist.txt"
        inv = ToolInvocation(params={"path": str(path), "content": "hello"}, cwd=tmp_cwd)
        result = await append_file_tool.execute(inv)
        assert result.success

    async def test_append_with_create_if_missing(self, append_file_tool, tmp_cwd):
        path = tmp_cwd / "new.txt"
        inv = ToolInvocation(
            params={"path": str(path), "content": "hello", "create_if_missing": True},
            cwd=tmp_cwd,
        )
        result = await append_file_tool.execute(inv)
        assert result.success
        assert path.read_text() == "hello\n"

    async def test_append_summary(self, append_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        path.write_text("a\n")
        inv = ToolInvocation(params={"path": str(path), "content": "b"}, cwd=tmp_cwd)
        result = await append_file_tool.execute(inv)
        assert result.summary

    async def test_append_artifacts(self, append_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        path.write_text("a\n")
        inv = ToolInvocation(params={"path": str(path), "content": "b"}, cwd=tmp_cwd)
        result = await append_file_tool.execute(inv)
        assert len(result.artifacts) == 1

    async def test_append_next_actions(self, append_file_tool, tmp_cwd):
        path = tmp_cwd / "test.txt"
        inv = ToolInvocation(params={"path": str(path), "content": "hello"}, cwd=tmp_cwd)
        result = await append_file_tool.execute(inv)
        assert result.next_actions

    async def test_append_without_create_if_missing_returns_error(self, append_file_tool, tmp_cwd):
        path = tmp_cwd / "noexist.txt"
        inv = ToolInvocation(
            params={"path": str(path), "content": "hello", "create_if_missing": False},
            cwd=tmp_cwd,
        )
        result = await append_file_tool.execute(inv)
        assert not result.success
        assert "does not exist" in result.error.lower() or "not exist" in result.error.lower()

    async def test_append_recovery_hint_on_missing_file(self, append_file_tool, tmp_cwd):
        path = tmp_cwd / "noexist.txt"
        inv = ToolInvocation(
            params={"path": str(path), "content": "hello", "create_if_missing": False},
            cwd=tmp_cwd,
        )
        result = await append_file_tool.execute(inv)
        assert result.recovery_hint


class TestEditFileTool:
    async def test_edit_existing_file(self, edit_file_tool, tmp_cwd):
        path = tmp_cwd / "test.py"
        path.write_text("def old():\n    pass\n")
        inv = ToolInvocation(
            params={"path": str(path), "old_string": "old", "new_string": "new"},
            cwd=tmp_cwd,
        )
        result = await edit_file_tool.execute(inv)
        assert result.success
        content = path.read_text()
        assert "new" in content
        assert "old" not in content

    async def test_edit_nonexistent_file_returns_error(self, edit_file_tool, tmp_cwd):
        inv = ToolInvocation(
            params={"path": str(tmp_cwd / "noexist.py"), "old_string": "x", "new_string": "y"},
            cwd=tmp_cwd,
        )
        result = await edit_file_tool.execute(inv)
        assert not result.success

    async def test_edit_non_matching_old_string(self, edit_file_tool, tmp_cwd):
        path = tmp_cwd / "test.py"
        path.write_text("hello")
        inv = ToolInvocation(
            params={"path": str(path), "old_string": "nonexistent", "new_string": "x"},
            cwd=tmp_cwd,
        )
        result = await edit_file_tool.execute(inv)
        assert not result.success

    async def test_edit_identical_old_new_returns_error(self, edit_file_tool, tmp_cwd):
        path = tmp_cwd / "test.py"
        path.write_text("hello")
        inv = ToolInvocation(
            params={"path": str(path), "old_string": "hello", "new_string": "hello"},
            cwd=tmp_cwd,
        )
        result = await edit_file_tool.execute(inv)
        assert not result.success

    async def test_edit_creates_file_when_old_string_empty(self, edit_file_tool, tmp_cwd):
        path = tmp_cwd / "new.txt"
        inv = ToolInvocation(
            params={"path": str(path), "old_string": "", "new_string": "new content"},
            cwd=tmp_cwd,
        )
        result = await edit_file_tool.execute(inv)
        assert result.success
        assert path.read_text() == "new content"

    async def test_edit_summary(self, edit_file_tool, tmp_cwd):
        path = tmp_cwd / "test.py"
        path.write_text("old")
        inv = ToolInvocation(
            params={"path": str(path), "old_string": "old", "new_string": "new"},
            cwd=tmp_cwd,
        )
        result = await edit_file_tool.execute(inv)
        assert result.summary

    async def test_edit_artifacts(self, edit_file_tool, tmp_cwd):
        path = tmp_cwd / "test.py"
        path.write_text("old")
        inv = ToolInvocation(
            params={"path": str(path), "old_string": "old", "new_string": "new"},
            cwd=tmp_cwd,
        )
        result = await edit_file_tool.execute(inv)
        assert len(result.artifacts) == 1

    async def test_edit_next_actions(self, edit_file_tool, tmp_cwd):
        path = tmp_cwd / "test.py"
        path.write_text("old")
        inv = ToolInvocation(
            params={"path": str(path), "old_string": "old", "new_string": "new"},
            cwd=tmp_cwd,
        )
        result = await edit_file_tool.execute(inv)
        assert result.next_actions

    async def test_edit_recovery_hint_on_not_found(self, edit_file_tool, tmp_cwd):
        inv = ToolInvocation(
            params={"path": str(tmp_cwd / "noexist.py"), "old_string": "x", "new_string": "y"},
            cwd=tmp_cwd,
        )
        result = await edit_file_tool.execute(inv)
        assert result.recovery_hint

    async def test_edit_recovery_hint_on_no_match(self, edit_file_tool, tmp_cwd):
        path = tmp_cwd / "test.py"
        path.write_text("hello")
        inv = ToolInvocation(
            params={"path": str(path), "old_string": "nonexistent", "new_string": "x"},
            cwd=tmp_cwd,
        )
        result = await edit_file_tool.execute(inv)
        assert result.recovery_hint

    async def test_edit_replaces_all_occurrences(self, edit_file_tool, tmp_cwd):
        path = tmp_cwd / "test.py"
        path.write_text("foo bar foo baz")
        inv = ToolInvocation(
            params={"path": str(path), "old_string": "foo", "new_string": "qux", "replace_all": True},
            cwd=tmp_cwd,
        )
        result = await edit_file_tool.execute(inv)
        assert result.success
        content = path.read_text()
        assert content == "qux bar qux baz"


class TestListDirTool:
    async def test_list_empty_dir(self, list_dir_tool, tmp_cwd):
        inv = ToolInvocation(params={}, cwd=tmp_cwd)
        result = await list_dir_tool.execute(inv)
        assert result.success
        assert "empty" in result.output.lower()

    async def test_list_files(self, list_dir_tool, tmp_cwd):
        (tmp_cwd / "a.txt").write_text("a")
        (tmp_cwd / "b.txt").write_text("b")
        inv = ToolInvocation(params={}, cwd=tmp_cwd)
        result = await list_dir_tool.execute(inv)
        assert result.success
        assert "a.txt" in result.output
        assert "b.txt" in result.output

    async def test_list_dir_hidden(self, list_dir_tool, tmp_cwd):
        (tmp_cwd / ".hidden").write_text("secret")
        (tmp_cwd / "visible.txt").write_text("ok")
        inv = ToolInvocation(params={}, cwd=tmp_cwd)
        result = await list_dir_tool.execute(inv)
        assert ".hidden" not in result.output

        inv_hidden = ToolInvocation(params={"include_hidden": True}, cwd=tmp_cwd)
        result_hidden = await list_dir_tool.execute(inv_hidden)
        assert ".hidden" in result_hidden.output

    async def test_list_nonexistent_dir_returns_error(self, list_dir_tool, tmp_cwd):
        inv = ToolInvocation(params={"path": "/nonexistent"}, cwd=tmp_cwd)
        result = await list_dir_tool.execute(inv)
        assert not result.success

    async def test_list_summary(self, list_dir_tool, tmp_cwd):
        (tmp_cwd / "a.txt").write_text("a")
        inv = ToolInvocation(params={}, cwd=tmp_cwd)
        result = await list_dir_tool.execute(inv)
        assert result.summary
        assert "1 entries" in result.summary

    async def test_list_next_actions(self, list_dir_tool, tmp_cwd):
        (tmp_cwd / "a.txt").write_text("a")
        inv = ToolInvocation(params={}, cwd=tmp_cwd)
        result = await list_dir_tool.execute(inv)
        assert result.next_actions

    async def test_list_recovery_hint_on_bad_path(self, list_dir_tool, tmp_cwd):
        inv = ToolInvocation(params={"path": "/nonexistent"}, cwd=tmp_cwd)
        result = await list_dir_tool.execute(inv)
        assert result.recovery_hint


class TestGrepTool:
    async def test_grep_finds_match(self, grep_tool, tmp_cwd):
        (tmp_cwd / "test.py").write_text("def hello():\n    pass\n")
        inv = ToolInvocation(params={"pattern": "hello"}, cwd=tmp_cwd)
        result = await grep_tool.execute(inv)
        assert result.success
        assert "hello" in result.output

    async def test_grep_no_match(self, grep_tool, tmp_cwd):
        (tmp_cwd / "test.py").write_text("abc")
        inv = ToolInvocation(params={"pattern": "xyz"}, cwd=tmp_cwd)
        result = await grep_tool.execute(inv)
        assert result.success
        assert "no matches" in result.output.lower()

    async def test_grep_case_insensitive(self, grep_tool, tmp_cwd):
        (tmp_cwd / "test.py").write_text("Hello World")
        inv = ToolInvocation(params={"pattern": "hello", "case_insensitive": True}, cwd=tmp_cwd)
        result = await grep_tool.execute(inv)
        assert result.success
        assert "Hello" in result.output

    async def test_grep_nonexistent_path_returns_error(self, grep_tool, tmp_cwd):
        inv = ToolInvocation(params={"pattern": "x", "path": "/nonexistent"}, cwd=tmp_cwd)
        result = await grep_tool.execute(inv)
        assert not result.success

    async def test_grep_invalid_regex_returns_error(self, grep_tool, tmp_cwd):
        inv = ToolInvocation(params={"pattern": "[invalid"}, cwd=tmp_cwd)
        result = await grep_tool.execute(inv)
        assert not result.success

    async def test_grep_summary(self, grep_tool, tmp_cwd):
        (tmp_cwd / "test.py").write_text("match this")
        inv = ToolInvocation(params={"pattern": "match"}, cwd=tmp_cwd)
        result = await grep_tool.execute(inv)
        assert result.summary
        assert "match" in result.summary.lower()

    async def test_grep_next_actions(self, grep_tool, tmp_cwd):
        (tmp_cwd / "test.py").write_text("match this")
        inv = ToolInvocation(params={"pattern": "match"}, cwd=tmp_cwd)
        result = await grep_tool.execute(inv)
        assert result.next_actions

    async def test_grep_artifacts(self, grep_tool, tmp_cwd):
        (tmp_cwd / "test.py").write_text("match this")
        inv = ToolInvocation(params={"pattern": "match"}, cwd=tmp_cwd)
        result = await grep_tool.execute(inv)
        assert len(result.artifacts) > 0

    async def test_grep_recovery_hint_on_bad_path(self, grep_tool, tmp_cwd):
        inv = ToolInvocation(params={"pattern": "x", "path": "/nonexistent"}, cwd=tmp_cwd)
        result = await grep_tool.execute(inv)
        assert result.recovery_hint

    async def test_grep_recovery_hint_on_invalid_regex(self, grep_tool, tmp_cwd):
        inv = ToolInvocation(params={"pattern": "["}, cwd=tmp_cwd)
        result = await grep_tool.execute(inv)
        assert result.recovery_hint

    async def test_grep_metadata_contains_match_count(self, grep_tool, tmp_cwd):
        (tmp_cwd / "test.py").write_text("match\nmatch\nnomatch\n")
        inv = ToolInvocation(params={"pattern": "match"}, cwd=tmp_cwd)
        result = await grep_tool.execute(inv)
        assert result.metadata.get("matches") == 3


class TestGlobTool:
    async def test_glob_finds_files(self, glob_tool, tmp_cwd):
        (tmp_cwd / "a.py").write_text("a")
        (tmp_cwd / "b.py").write_text("b")
        (tmp_cwd / "c.txt").write_text("c")
        inv = ToolInvocation(params={"pattern": "*.py"}, cwd=tmp_cwd)
        result = await glob_tool.execute(inv)
        assert result.success
        assert "a.py" in result.output
        assert "b.py" in result.output
        assert "c.txt" not in result.output

    async def test_glob_nonexistent_dir_returns_error(self, glob_tool, tmp_cwd):
        inv = ToolInvocation(params={"pattern": "*.py", "path": "/nonexistent"}, cwd=tmp_cwd)
        result = await glob_tool.execute(inv)
        assert not result.success

    async def test_glob_summary(self, glob_tool, tmp_cwd):
        (tmp_cwd / "a.py").write_text("a")
        inv = ToolInvocation(params={"pattern": "*.py"}, cwd=tmp_cwd)
        result = await glob_tool.execute(inv)
        assert result.summary
        assert "1 file" in result.summary.lower()

    async def test_glob_next_actions(self, glob_tool, tmp_cwd):
        (tmp_cwd / "a.py").write_text("a")
        inv = ToolInvocation(params={"pattern": "*.py"}, cwd=tmp_cwd)
        result = await glob_tool.execute(inv)
        assert result.next_actions

    async def test_glob_artifacts(self, glob_tool, tmp_cwd):
        (tmp_cwd / "a.py").write_text("a")
        inv = ToolInvocation(params={"pattern": "*.py"}, cwd=tmp_cwd)
        result = await glob_tool.execute(inv)
        assert len(result.artifacts) > 0

    async def test_glob_no_match(self, glob_tool, tmp_cwd):
        inv = ToolInvocation(params={"pattern": "*.zzz"}, cwd=tmp_cwd)
        result = await glob_tool.execute(inv)
        assert result.success
        assert "0 files" in result.summary.lower() or "0" in result.summary

    async def test_glob_recovery_hint_on_bad_path(self, glob_tool, tmp_cwd):
        inv = ToolInvocation(params={"pattern": "*.py", "path": "/nonexistent"}, cwd=tmp_cwd)
        result = await glob_tool.execute(inv)
        assert result.recovery_hint

    async def test_glob_metadata(self, glob_tool, tmp_cwd):
        (tmp_cwd / "a.py").write_text("a")
        (tmp_cwd / "b.py").write_text("b")
        inv = ToolInvocation(params={"pattern": "*.py"}, cwd=tmp_cwd)
        result = await glob_tool.execute(inv)
        assert result.metadata.get("matches") == 2
