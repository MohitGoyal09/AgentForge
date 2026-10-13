"""Tests for examples/forecast_lineage/build_example.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from agentforge_harness.agent.persistence import SCHEMA_VERSION

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "forecast_lineage"


def _load():
    spec = importlib.util.spec_from_file_location("build_example", EXAMPLE_DIR / "build_example.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_self_check_passes():
    _load().self_check()


def test_build_is_byte_identical_across_runs():
    mod = _load()
    first, second = mod.build(), mod.build()
    assert first == second
    assert {k: v.encode() for k, v in first.items()} == {k: v.encode() for k, v in second.items()}


def test_committed_outputs_match_build():
    for name, text in _load().build().items():
        assert (EXAMPLE_DIR / name).read_bytes() == text.encode(), f"{name} is stale; rerun build_example.py"


def test_schema_version_mirrors_package():
    assert _load().SCHEMA_VERSION == SCHEMA_VERSION
