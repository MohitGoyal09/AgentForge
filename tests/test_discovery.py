"""Tests for ToolDiscoveryManager — covers BUG E.

BUG E regression tests:
  1. A syntactically broken .py file logs a warning and does NOT crash discovery.
  2. Two files with the same stem in different root directories both load without
     one clobbering the other in sys.modules.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from agentforge_harness.config.config import Config
from agentforge_harness.tools.discovery import ToolDiscoveryManager
from agentforge_harness.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_TOOL_SOURCE = """\
from agentforge_harness.tools.base import Tool, ToolInvocation, ToolResult
from agentforge_harness.config.config import Config


class SampleTool(Tool):
    name = "sample_tool"
    description = "A sample tool for testing"

    @property
    def schema(self):
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        return ToolResult.success_result("ok")
"""

BROKEN_PYTHON = "this is not : valid python !!!! <<"


def _make_tool_dir(base: Path, stem: str, source: str) -> Path:
    """Create <base>/.agentforge/tools/<stem>.py with *source* content."""
    tool_dir = base / ".agentforge" / "tools"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / f"{stem}.py").write_text(source)
    return base


def _manager(tmp_path: Path) -> tuple[ToolDiscoveryManager, ToolRegistry]:
    config = Config(cwd=tmp_path)
    registry = ToolRegistry(config)
    mgr = ToolDiscoveryManager(config, registry)
    return mgr, registry


# ---------------------------------------------------------------------------
# BUG E — syntactically broken .py logs warning and does not crash
# ---------------------------------------------------------------------------


def test_broken_module_logs_warning_and_does_not_crash(tmp_path: Path, caplog):
    """A broken .py file must emit a warning and allow discovery to continue."""
    _make_tool_dir(tmp_path, "broken_tool", BROKEN_PYTHON)

    mgr, registry = _manager(tmp_path)

    with caplog.at_level(logging.WARNING, logger="agentforge_harness.tools.discovery"):
        # Must not raise
        mgr.discover_from_directory(tmp_path)

    # A warning must have been logged
    assert any("broken_tool" in r.message or "Failed" in r.message for r in caplog.records)
    # No tools from the broken file should be registered
    assert registry.get("sample_tool") is None


def test_valid_module_loads_after_broken_sibling(tmp_path: Path, caplog):
    """The broken file must not prevent the valid sibling from loading."""
    _make_tool_dir(tmp_path, "broken_tool", BROKEN_PYTHON)

    tool_dir = tmp_path / ".agentforge" / "tools"
    (tool_dir / "valid_tool.py").write_text(VALID_TOOL_SOURCE)

    mgr, registry = _manager(tmp_path)

    with caplog.at_level(logging.WARNING, logger="agentforge_harness.tools.discovery"):
        mgr.discover_from_directory(tmp_path)

    # The valid tool must still be registered
    assert registry.get("sample_tool") is not None


# ---------------------------------------------------------------------------
# BUG E — two files with the same stem in different root directories
# ---------------------------------------------------------------------------


def test_same_stem_in_different_roots_both_load(tmp_path: Path):
    """Two roots containing a file named 'my_tool.py' must both register without
    the second clobbering the first in sys.modules."""
    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"

    # Both directories have a file called my_tool.py, but define *different* tools.
    source_a = VALID_TOOL_SOURCE.replace("SampleTool", "ToolA").replace(
        'name = "sample_tool"', 'name = "tool_a"'
    )
    source_b = VALID_TOOL_SOURCE.replace("SampleTool", "ToolB").replace(
        'name = "sample_tool"', 'name = "tool_b"'
    )

    _make_tool_dir(root_a, "my_tool", source_a)
    _make_tool_dir(root_b, "my_tool", source_b)

    config_a = Config(cwd=root_a)
    registry = ToolRegistry(config_a)
    mgr = ToolDiscoveryManager(config_a, registry)

    mgr.discover_from_directory(root_a)
    mgr.discover_from_directory(root_b)

    assert registry.get("tool_a") is not None, "tool_a from root_a should be registered"
    assert registry.get("tool_b") is not None, "tool_b from root_b should be registered"
