from __future__ import annotations

from pathlib import Path

from agentforge_harness.utils.paths import display_path_rel_to_cwd, ensure_parent_directory, find_source_files, resolve_path


class TestResolvePath:
    def test_resolve_path_with_absolute_path(self, tmp_cwd: Path):
        abs_path = Path("/tmp")
        result = resolve_path(str(tmp_cwd), str(abs_path))
        assert result == abs_path.resolve()

    def test_resolve_path_with_relative_path(self, tmp_cwd: Path):
        result = resolve_path(tmp_cwd, "a/b.txt")
        assert result == tmp_cwd.resolve() / "a" / "b.txt"


class TestDisplayPathRelToCwd:
    def test_display_path_rel_to_cwd(self, tmp_cwd: Path):
        target = tmp_cwd / "nested" / "file.txt"
        assert display_path_rel_to_cwd(str(target), tmp_cwd) == "nested/file.txt"

    def test_display_path_rel_to_cwd_falls_back_when_path_not_under_cwd(self, tmp_cwd: Path):
        target = Path("/tmp/outside.txt")
        assert display_path_rel_to_cwd(str(target), tmp_cwd) == str(target)

    def test_display_path_rel_to_cwd_without_cwd(self):
        assert display_path_rel_to_cwd("/tmp/example.txt", None) == "/tmp/example.txt"


class TestEnsureParentDirectory:
    def test_ensure_parent_directory_creates_parent(self, tmp_cwd: Path):
        target = tmp_cwd / "a" / "b" / "c.txt"
        ensure_parent_directory(target)
        assert target.parent.exists()
        assert target.parent.is_dir()


class TestFindSourceFiles:
    def test_find_source_files_skips_hidden_and_binary_files(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()

        (src / "visible.py").write_text("print('ok')")
        (src / ".hidden.py").write_text("print('hidden')")

        nested = src / "nested"
        nested.mkdir()
        (nested / "inner.txt").write_text("text")

        excluded = src / "__pycache__"
        excluded.mkdir()
        (excluded / "skip.py").write_text("print('nope')")

        binary = src / "binary.bin"
        binary.write_bytes(b"abc\x00def")

        result = find_source_files(src)
        result_strs = {str(p) for p in result}
        assert str(src / "visible.py") in result_strs
        assert str(src / "nested" / "inner.txt") in result_strs
        assert str(src / ".hidden.py") not in result_strs
        assert str(src / "binary.bin") not in result_strs
        assert not any(str(excluded) in p for p in result_strs)
