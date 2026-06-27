"""Tests for SkillManager.get_active_allowed_tools()."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agentforge_harness.skills.manager import SkillManager, SkillMetadata


def _make_manager(*skills: SkillMetadata) -> SkillManager:
    manager = SkillManager(skill_roots=[])
    for skill in skills:
        manager._available[skill.name] = skill
    return manager


def _skill(name: str, allowed_tools: list[str] | None) -> SkillMetadata:
    return SkillMetadata(
        name=name,
        description="",
        path=Path(f"/fake/{name}/SKILL.md"),
        allowed_tools=allowed_tools,
    )


def test_no_active_skills_with_allowed_tools_returns_none():
    """No active skill specifies allowed_tools → returns None (no restriction)."""
    manager = _make_manager(
        _skill("alpha", None),
        _skill("beta", None),
    )
    result = manager.get_active_allowed_tools(["alpha", "beta"])
    assert result is None


def test_one_skill_with_allowed_tools():
    """Single active skill with allowed_tools returns those tools."""
    manager = _make_manager(
        _skill("alpha", ["read", "write"]),
    )
    result = manager.get_active_allowed_tools(["alpha"])
    assert set(result) == {"read", "write"}


def test_two_skills_returns_union():
    """Two active skills each with different tools → union is returned."""
    manager = _make_manager(
        _skill("alpha", ["read"]),
        _skill("beta", ["write"]),
    )
    result = manager.get_active_allowed_tools(["alpha", "beta"])
    assert result is not None
    assert set(result) == {"read", "write"}


def test_union_deduplicates():
    """Overlapping tools across skills are deduplicated."""
    manager = _make_manager(
        _skill("alpha", ["read", "glob"]),
        _skill("beta", ["read", "write"]),
    )
    result = manager.get_active_allowed_tools(["alpha", "beta"])
    assert result is not None
    assert sorted(result) == sorted({"read", "glob", "write"})
    # No duplicates
    assert len(result) == len(set(result))


def test_one_skill_with_empty_allowed_tools_returns_empty_list():
    """Skill explicitly specifies allowed_tools=[] → returns [] (block everything)."""
    manager = _make_manager(
        _skill("alpha", []),
    )
    result = manager.get_active_allowed_tools(["alpha"])
    assert result == []


def test_unknown_active_skills_are_ignored():
    """Active skill names not in _available are silently skipped."""
    manager = _make_manager(_skill("known", ["read"]))
    result = manager.get_active_allowed_tools(["known", "unknown-skill"])
    assert set(result) == {"read"}


def test_mix_of_none_and_set_allowed_tools():
    """One skill with None and one with tools → union of the non-None ones."""
    manager = _make_manager(
        _skill("alpha", None),
        _skill("beta", ["shell"]),
    )
    result = manager.get_active_allowed_tools(["alpha", "beta"])
    assert result == ["shell"]
