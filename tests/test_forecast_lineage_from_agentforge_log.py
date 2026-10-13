"""Tests for examples/forecast_lineage/from_agentforge_log.py (hand-written fixture log)."""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "forecast_lineage"

A, B, C = "https://x.test/a.csv", "https://x.test/b.csv", "https://x.test/c.csv"
GHOST = "https://x.test/never-fetched.csv"


def _load():
    spec = importlib.util.spec_from_file_location("from_agentforge_log", EXAMPLE_DIR / "from_agentforge_log.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture() -> list[dict]:
    events: list[dict] = []

    def emit(type_: str, minute: int, payload: dict) -> None:
        # One naive timestamp (older logs wrote them) to check it is read as UTC.
        stamp = f"2026-10-14T10:{minute:02d}:00" + ("" if minute == 4 else "+00:00")
        events.append({"schema_version": 1, "session_id": "s", "turn": 1,
                       "sequence": len(events) + 1, "type": type_, "timestamp": stamp, "payload": payload})

    def fetch(cid: str, url: str, minute: int, output: str, ok: bool = True) -> None:
        emit("tool_call_start", minute, {"call_id": cid, "name": "web_fetch", "arguments": {"url": url}})
        emit("tool_call_complete", minute, {"call_id": cid, "name": "web_fetch", "success": ok,
                                            "output": output, "error": None if ok else "boom",
                                            "truncated": False,
                                            "metadata": {"output_hygiene": {"truncated_fields": (
                                                {"output": 5} if url == C else {})}}})

    def write(cid: str, version: int, urls: list[str], minute: int, probs: dict) -> None:
        body = {"challenge_id": "GC-T", "version": version, "probabilities": probs,
                "cited_urls": urls, "rationale": "r"}
        emit("tool_call_start", minute, {"call_id": cid, "name": "write_file",
                                         "arguments": {"path": f"forecast_v{version}.json", "content": json.dumps(body)}})
        emit("tool_call_complete", minute, {"call_id": cid, "name": "write_file", "success": True,
                                            "output": "ok", "error": None})

    fetch("1", A, 1, "alpha")
    fetch("2", B, 2, "beta")
    write("3", 1, [A, B, GHOST], 3, {"bearish": 0.3, "neutral": 0.3, "bullish": 0.4})
    fetch("4", C, 4, "gamma")
    fetch("5", "https://x.test/d.csv", 5, "", ok=False)
    emit("retry", 6, {"model": "m", "attempt": 1, "error": "e", "delay": 1.0})
    write("6", 2, [A, C], 7, {"bearish": 0.2, "neutral": 0.2, "bullish": 0.6})
    write("7", 3, [A], 8, {"bearish": 0.2, "neutral": 0.2, "bullish": 0.6})
    return events


def _run(tmp_path: Path) -> tuple[list[dict], str]:
    log = tmp_path / "events.jsonl"
    log.write_text("".join(json.dumps(e) + "\n" for e in _fixture()))
    out = tmp_path / "out"
    _load().main([str(log), str(out)])
    with open(out / "versions.csv", newline="") as f:
        return list(csv.DictReader(f)), (out / "gaps.md").read_text()


def test_columns_match_synthetic_example(tmp_path):
    rows, _ = _run(tmp_path)
    mod = _load()
    assert list(rows[0]) == mod.be.VERSION_COLUMNS


def test_versions_labels_and_citations(tmp_path):
    rows, _ = _run(tmp_path)
    assert [r["version"] for r in rows] == ["1", "2", "3"]
    assert [r["label"] for r in rows] == ["initial", "mixed", "previously_seen"]
    # tool_call_complete seqs: A=2, B=4, C=8; failed fetch d=10; retry=11
    assert rows[0]["cited_event_seqs"] == "2;4"
    assert rows[1]["cited_event_seqs"] == "2;8"
    assert rows[1]["recovery_event_seqs"] == "10;11"
    assert rows[2]["recovery_event_seqs"] == ""
    assert rows[0]["p_bullish"] == "0.4"
    assert all(r["brier_unadjusted"] == "" and r["adjustment"] == "" for r in rows)
    assert rows[1]["submitted_at"].startswith("2026-10-14T10:07")


def test_gaps_lists_hallucinated_url_and_unfilled_fields(tmp_path):
    _, gaps = _run(tmp_path)
    assert GHOST in gaps
    assert "publish_time" in gaps
    assert "brier" in gaps
    assert "proxy" in gaps


def test_gaps_flags_truncated_fetch_output(tmp_path):
    _, gaps = _run(tmp_path)
    assert f"seq 8 {C}" in gaps.split("truncated", 1)[1]
