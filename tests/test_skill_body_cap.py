"""Tests for the skill body size cap in SkillManager.load_skill()."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import pytest

from agentforge_harness.skills.manager import SkillManager, _MAX_SKILL_BODY_CHARS

_TRUNCATION_NOTICE = "[... skill content truncated for compaction; use Read on the skill path if you need the full text]"


def _make_skill_file(root: Path, name: str, body: str) -> Path:
    """Write a minimal SKILL.md (no frontmatter) with the given body."""
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(body, encoding="utf-8")
    return skill_file


def test_body_under_cap_returned_as_is():
    """Skill body shorter than the cap is returned unchanged."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        body = "A" * (_MAX_SKILL_BODY_CHARS - 1)
        _make_skill_file(root, "small-skill", body)

        manager = SkillManager(skill_roots=[root])
        manager.discover()
        result = manager.load_skill("small-skill")

    assert result == body
    assert _TRUNCATION_NOTICE not in result


def test_body_exactly_at_cap_returned_as_is():
    """Body exactly at the limit is not truncated."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        body = "B" * _MAX_SKILL_BODY_CHARS
        _make_skill_file(root, "exact-skill", body)

        manager = SkillManager(skill_roots=[root])
        manager.discover()
        result = manager.load_skill("exact-skill")

    # strip_frontmatter adds no content here, so result should equal body
    assert result.startswith("B" * _MAX_SKILL_BODY_CHARS)
    assert _TRUNCATION_NOTICE not in result


def test_body_over_cap_is_truncated_with_notice():
    """Body longer than the cap is truncated and the notice is appended."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        body = "C" * (_MAX_SKILL_BODY_CHARS + 5000)
        _make_skill_file(root, "large-skill", body)

        manager = SkillManager(skill_roots=[root])
        manager.discover()
        result = manager.load_skill("large-skill")

    # Exactly _MAX_SKILL_BODY_CHARS chars of original content, then the notice
    assert result[: _MAX_SKILL_BODY_CHARS] == "C" * _MAX_SKILL_BODY_CHARS
    assert result.endswith(_TRUNCATION_NOTICE)


def test_warning_logged_when_truncated(caplog):
    """A WARNING is emitted when the skill body is truncated."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        body = "D" * (_MAX_SKILL_BODY_CHARS + 1)
        _make_skill_file(root, "warn-skill", body)

        manager = SkillManager(skill_roots=[root])
        manager.discover()

        with caplog.at_level(logging.WARNING, logger="agentforge_harness.skills.manager"):
            manager.load_skill("warn-skill")

    assert any("truncated" in record.message.lower() for record in caplog.records)
    assert any("warn-skill" in record.message for record in caplog.records)


def test_no_warning_logged_when_not_truncated(caplog):
    """No WARNING is emitted when the skill body is within the cap."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        body = "E" * 100
        _make_skill_file(root, "tiny-skill", body)

        manager = SkillManager(skill_roots=[root])
        manager.discover()

        with caplog.at_level(logging.WARNING, logger="agentforge_harness.skills.manager"):
            manager.load_skill("tiny-skill")

    assert not any("truncated" in record.message.lower() for record in caplog.records)
