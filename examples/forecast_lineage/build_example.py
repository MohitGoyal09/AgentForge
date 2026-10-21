"""Build the synthetic forecast-lineage example (stdlib only, deterministic).

Writes events.jsonl, versions.csv and challenges.csv next to this file.
Run `python build_example.py` to build, `python build_example.py --check` to
build and run the self-check. Everything is synthetic: no network, no LLM
calls, no Headline Arena API calls, no real GC prices, no clock.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Mirrors agentforge_harness.agent.persistence.SCHEMA_VERSION. Hardcoded so the
# script stays stdlib-only and standalone; tests/test_forecast_lineage_example.py
# asserts the two stay equal.
SCHEMA_VERSION = 1
SESSION_ID = "forecast-lineage-demo"
CATEGORIES = ("bearish", "neutral", "bullish")
RECOVERY_TYPES = {"agent_error", "retry", "compaction", "checkpoint_restored"}
EVIDENCE_BUDGET = {"max_tool_calls": 15, "token_cap": 40000}
TOOL_CALL_TYPES = {"source_retrieved", "agent_error", "retry"}

CHALLENGES = {
    "GC-A": {"deadline": "2026-03-02T21:00:00+00:00", "outcome": "bullish"},
    "GC-B": {"deadline": "2026-03-03T21:00:00+00:00", "outcome": "neutral"},
}

VERSION_COLUMNS = [
    "challenge_id", "forecast_id", "revision_id", "version", "submitted_at",
    "p_bearish", "p_neutral", "p_bullish", "vector_provenance", "submission_status", "receipt_id",
    "evidence_budget_tool_calls", "tool_calls_used", "cited_event_seqs",
    "recovery_event_seqs", "label", "label_basis", "hash_basis", "source_truncated",
    "brier_unadjusted", "adjustment",
]
CHALLENGE_COLUMNS = [
    "challenge_id", "asset", "deadline", "outcome", "outcome_is_synthetic",
    "final_forecast_id", "final_revision_id", "final_brier_unadjusted",
]


def ts(day: str, hms: str) -> str:
    """Fixed UTC ISO 8601 timestamp, same format as PersistenceManager.append_event."""
    return datetime.fromisoformat(f"{day}T{hms}").replace(tzinfo=timezone.utc).isoformat()


def reconstruct(direction: str, confidence: float) -> dict[str, float]:
    """Chosen direction gets `confidence`; the remainder is split evenly."""
    rest = round((1 - confidence) / 2, 6)
    return {k: (confidence if k == direction else rest) for k in CATEGORIES}


def brier(probs: dict[str, float], outcome: str) -> float:
    """Sum over 3 categories of (p_k - o_k)^2, o one-hot on outcome. Range 0..2."""
    assert abs(sum(probs.values()) - 1) < 1e-9, probs
    return sum((probs[k] - (1.0 if k == outcome else 0.0)) ** 2 for k in CATEGORIES)


def classify(events: list[dict], prev: dict, cur: dict) -> tuple[str, list[int], list[int], str]:
    """Label `cur` against the previous submission `prev` of the same challenge.

    A cited source whose hash is unseen before `prev` is `new` only when its
    publish_time proves it appeared after `prev`. Otherwise it was only newly
    retrieved. Returns (label, fresh_cited_seqs, recovery_seqs, label_basis), where
    label_basis is `publish_time`, `retrieval_time_proxy` (a fresh source has no
    publish_time) or "" (no fresh source).
    """
    by_seq = {e["sequence"]: e for e in events}
    prev_time = datetime.fromisoformat(prev["timestamp"])
    seen = {
        e["payload"]["sha256"]
        for e in events
        if e["sequence"] < prev["sequence"] and "sha256" in e["payload"]
    }
    cited = cur["payload"]["cited_event_seqs"]
    new, retrieved, proxy = [], [], False
    for seq in cited:
        src = by_seq[seq]
        assert src["type"] == "source_retrieved" and seq < cur["sequence"], seq
        p = src["payload"]
        if p["sha256"] in seen:
            continue
        published = p.get("publish_time")
        if published is None:
            proxy = True
            retrieved.append(seq)
        elif datetime.fromisoformat(published) > prev_time:
            new.append(seq)
        else:
            retrieved.append(seq)
    fresh = sorted(new + retrieved)
    basis = ("retrieval_time_proxy" if proxy else "publish_time") if fresh else ""
    recovery = [
        e["sequence"] for e in events
        if prev["sequence"] < e["sequence"] < cur["sequence"] and e["type"] in RECOVERY_TYPES
    ]
    if fresh and recovery:
        label = "mixed"
    elif new:
        label = "new"
    elif retrieved:
        label = "newly_retrieved"
    elif recovery:
        label = "recovery_only"
    elif cited:
        label = "previously_seen"
    else:
        label = "unknown"
    return label, fresh, recovery, basis


def cited_truncated(events: list[dict], cited: list[int]) -> str:
    """"true" if any cited source's stored text was cut short, else "false"."""
    by_seq = {e["sequence"]: e for e in events}
    return "true" if any(by_seq[s]["payload"].get("truncated") for s in cited) else "false"


class Session:
    """Tiny event recorder using the AgentForge event envelope."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, type_: str, timestamp: str, payload: dict, turn: int) -> int:
        seq = len(self.events) + 1
        self.events.append({
            "schema_version": SCHEMA_VERSION,
            "session_id": SESSION_ID,
            "turn": turn,
            "sequence": seq,
            "type": type_,
            "timestamp": timestamp,
            "payload": payload,
        })
        return seq

    def source(self, series: str, vintage: str, published: str, retrieved: str, turn: int) -> int:
        content = f"SYNTHETIC CONTENT {series} vintage {vintage}"
        return self.emit("source_retrieved", retrieved, {
            "source_id": f"{series}@{vintage}",
            "url": f"https://alfred.stlouisfed.org/series?seid={series}",
            "publisher": "FRED/ALFRED, Federal Reserve Bank of St. Louis (synthetic stand-in)",
            "publish_time": published,
            "retrieval_time": retrieved,
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "vintage_date": vintage,
        }, turn)

    def forecast(self, challenge: str, version: int, when: str, cited: list[int], turn: int,
                 probs: dict[str, float] | None = None,
                 direction: str | None = None, confidence: float | None = None) -> int:
        payload = {
            "challenge_id": challenge,
            "forecast_id": f"fc-{challenge}",
            "revision_id": None if version == 1 else f"rev-{challenge}-{version - 1}",
            "version": version,
            "is_revision": version > 1,
        }
        if probs is None:
            probs = reconstruct(direction, confidence)
            payload.update(probabilities=probs, vector_provenance="reconstructed",
                           direction=direction, confidence=confidence)
        else:
            payload.update(probabilities=probs, vector_provenance="submitted")
        accepted = (datetime.fromisoformat(when) + timedelta(seconds=2)).isoformat()
        payload.update(cited_event_seqs=cited, receipt={
            "receipt_id": f"rcpt-{challenge}-v{version}", "accepted_at": accepted, "synthetic": True,
        })
        return self.emit("forecast_submitted", when, payload, turn)


def build_events() -> list[dict]:
    s = Session()
    s.emit("run_config", ts("2026-03-02", "13:00:00"), {"evidence_budget": EVIDENCE_BUDGET}, 0)
    # GC-A
    dgs10_old = s.source("DGS10", "2026-02-27", ts("2026-02-27", "21:00:00"), ts("2026-03-02", "13:01:00"), 1)
    usd = s.source("DTWEXBGS", "2026-02-27", ts("2026-02-27", "21:00:00"), ts("2026-03-02", "13:02:00"), 1)
    s.forecast("GC-A", 1, ts("2026-03-02", "13:05:00"), [dgs10_old, usd], 1,
               probs={"bearish": 0.30, "neutral": 0.30, "bullish": 0.40})
    dgs10_new = s.source("DGS10", "2026-03-02", ts("2026-03-02", "15:30:00"), ts("2026-03-02", "15:31:00"), 2)
    s.forecast("GC-A", 2, ts("2026-03-02", "15:40:00"), [dgs10_old, dgs10_new], 2,
               probs={"bearish": 0.15, "neutral": 0.25, "bullish": 0.60})
    s.emit("agent_error", ts("2026-03-02", "17:00:00"),
           {"error": "tool call timed out (synthetic)", "details": {"tool": "fetch_series"}}, 3)
    s.emit("retry", ts("2026-03-02", "17:00:05"),
           {"model": "synthetic-model", "attempt": 1, "error": "timeout (synthetic)", "delay": 5.0}, 3)
    s.emit("compaction", ts("2026-03-02", "17:10:00"), {"message": "context compacted (synthetic)", "summary_tokens": 900}, 3)
    s.emit("checkpoint_restored", ts("2026-03-02", "17:12:00"),
           {"checkpoint_id": "cp-synthetic-1", "restored_event_sequence": 6}, 3)
    s.forecast("GC-A", 3, ts("2026-03-02", "17:20:00"), [dgs10_old, dgs10_new], 3,
               probs={"bearish": 0.20, "neutral": 0.20, "bullish": 0.60})
    s.emit("challenge_resolved", ts("2026-03-02", "22:00:00"),
           {"challenge_id": "GC-A", "outcome": CHALLENGES["GC-A"]["outcome"], "synthetic": True}, 4)
    # GC-B
    dgs10_b = s.source("DGS10", "2026-03-03", ts("2026-03-03", "08:00:00"), ts("2026-03-03", "13:01:00"), 5)
    s.forecast("GC-B", 1, ts("2026-03-03", "13:05:00"), [dgs10_b], 5, direction="bullish", confidence=0.6)
    s.forecast("GC-B", 2, ts("2026-03-03", "14:30:00"), [dgs10_b], 6,
               probs={"bearish": 0.10, "neutral": 0.50, "bullish": 0.40})
    s.emit("challenge_resolved", ts("2026-03-03", "22:00:00"),
           {"challenge_id": "GC-B", "outcome": CHALLENGES["GC-B"]["outcome"], "synthetic": True}, 7)
    return s.events


def f4(x: float) -> str:
    return f"{x:.4f}"


def join(seqs: list[int]) -> str:
    return ";".join(map(str, seqs))


def build_rows(events: list[dict]) -> tuple[list[dict], list[dict]]:
    budget = next(e for e in events if e["type"] == "run_config")["payload"]["evidence_budget"]
    outcomes = {e["payload"]["challenge_id"]: e["payload"]["outcome"]
                for e in events if e["type"] == "challenge_resolved"}
    subs = [e for e in events if e["type"] == "forecast_submitted"]
    versions, prev_of = [], {}
    for e in subs:
        p, cid = e["payload"], e["payload"]["challenge_id"]
        assert datetime.fromisoformat(e["timestamp"]) <= datetime.fromisoformat(CHALLENGES[cid]["deadline"])
        if p["version"] == 1:
            label, recovery, basis = "initial", [], ""
        else:
            label, _, recovery, basis = classify(events, prev_of[cid], e)
        prev_of[cid] = e
        # Per-challenge count: tool calls after the previous challenge_resolved (or session
        # start) up to and including this submission.
        start = max((x["sequence"] for x in events
                     if x["type"] == "challenge_resolved" and x["sequence"] < e["sequence"]), default=0)
        used = sum(1 for x in events
                   if start < x["sequence"] <= e["sequence"] and x["type"] in TOOL_CALL_TYPES)
        assert used <= budget["max_tool_calls"]
        pr = p["probabilities"]
        versions.append({
            "challenge_id": cid, "forecast_id": p["forecast_id"], "revision_id": p["revision_id"] or "",
            "version": p["version"], "submitted_at": e["timestamp"],
            "p_bearish": pr["bearish"], "p_neutral": pr["neutral"], "p_bullish": pr["bullish"],
            "vector_provenance": p["vector_provenance"],
            "submission_status": "synthetic_receipt" if p["receipt"]["synthetic"] else "submitted",
            "receipt_id": p["receipt"]["receipt_id"],
            "evidence_budget_tool_calls": budget["max_tool_calls"], "tool_calls_used": used,
            "cited_event_seqs": join(p["cited_event_seqs"]), "recovery_event_seqs": join(recovery),
            "label": label, "label_basis": basis, "hash_basis": "full_body",
            "source_truncated": cited_truncated(events, p["cited_event_seqs"]),
            "brier_unadjusted": f4(brier(pr, outcomes[cid])), "adjustment": "",
        })
    challenges = []
    for cid, meta in CHALLENGES.items():
        final = [v for v in versions if v["challenge_id"] == cid][-1]
        challenges.append({
            "challenge_id": cid, "asset": "GC", "deadline": meta["deadline"], "outcome": outcomes[cid],
            "outcome_is_synthetic": "true", "final_forecast_id": final["forecast_id"],
            "final_revision_id": final["revision_id"], "final_brier_unadjusted": final["brier_unadjusted"],
        })
    return versions, challenges


def to_csv(columns: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def build() -> dict[str, str]:
    """Return {filename: text} for all generated files."""
    events = build_events()
    versions, challenges = build_rows(events)
    return {
        "events.jsonl": "".join(json.dumps(e) + "\n" for e in events),
        "versions.csv": to_csv(VERSION_COLUMNS, versions),
        "challenges.csv": to_csv(CHALLENGE_COLUMNS, challenges),
    }


def self_check() -> None:
    # Brier math
    assert brier({"bearish": 0, "neutral": 0, "bullish": 1}, "bullish") == 0
    assert brier({"bearish": 1, "neutral": 0, "bullish": 0}, "bullish") == 2
    third = {k: 1 / 3 for k in CATEGORIES}
    assert f4(brier(third, "neutral")) == "0.6667"
    assert f4(brier({"bearish": 0.2, "neutral": 0.2, "bullish": 0.6}, "bullish")) == "0.2400"
    assert reconstruct("bullish", 0.6) == {"bearish": 0.2, "neutral": 0.2, "bullish": 0.6}

    # In-memory fixtures for all five labels (mixed and unknown are not in the story).
    def sub(seq: int, when: str, cited: list[int]) -> dict:
        return {"sequence": seq, "type": "forecast_submitted", "timestamp": ts("2026-01-01", when),
                "payload": {"cited_event_seqs": cited}}

    def src(seq: int, published: str | None, sha: str) -> dict:
        return {"sequence": seq, "type": "source_retrieved", "timestamp": ts("2026-01-01", "09:00:00"),
                "payload": {"publish_time": published and ts("2026-01-01", published), "sha256": sha}}

    def err(seq: int) -> dict:
        return {"sequence": seq, "type": "retry", "timestamp": ts("2026-01-01", "11:00:00"), "payload": {}}

    old, new_src = src(1, "08:00:00", "a"), src(3, "10:30:00", "b")
    first = sub(2, "10:00:00", [1])
    fixtures = {
        "mixed": [old, first, new_src, err(4), sub(5, "12:00:00", [3])],
        "new": [old, first, new_src, sub(4, "12:00:00", [3])],
        "recovery_only": [old, first, err(3), sub(4, "12:00:00", [1])],
        "previously_seen": [old, first, sub(3, "12:00:00", [1])],
        "unknown": [old, first, sub(3, "12:00:00", [])],
        # Published before the previous forecast but first fetched after it.
        "newly_retrieved": [old, first, src(3, "08:30:00", "c"), sub(4, "12:00:00", [3])],
    }
    for expected, evs in fixtures.items():
        subs = [e for e in evs if e["type"] == "forecast_submitted"]
        assert classify(evs, subs[0], subs[1])[0] == expected, expected
    assert classify(fixtures["new"], first, fixtures["new"][3])[3] == "publish_time"
    assert classify(fixtures["newly_retrieved"], first, fixtures["newly_retrieved"][3])[3] == "publish_time"
    # No publish time: never `new`, and the basis says it is a proxy.
    nopub = [old, first, src(3, None, "d"), sub(4, "12:00:00", [3])]
    assert classify(nopub, first, nopub[3])[0::3] == ("newly_retrieved", "retrieval_time_proxy")
    # Same sha as an earlier event is not "new" even if published later.
    dup = [old, first, src(3, "10:30:00", "a"), sub(4, "12:00:00", [3])]
    assert classify(dup, dup[1], dup[3])[0] == "previously_seen"

    # The built example.
    events = build_events()
    seqs = [e["sequence"] for e in events]
    assert all(b > a for a, b in zip(seqs, seqs[1:])), "sequence must rise strictly"
    assert all(e["timestamp"].endswith("+00:00") for e in events)
    for e in events:
        if e["type"] == "forecast_submitted":
            assert abs(sum(e["payload"]["probabilities"].values()) - 1) < 1e-9
    versions, challenges = build_rows(events)
    assert [v["label"] for v in versions] == ["initial", "new", "recovery_only", "initial", "previously_seen"]
    assert [v["brier_unadjusted"] for v in versions] == ["0.5400", "0.2450", "0.2400", "1.0400", "0.4200"]
    assert sum(1 for e in events if e["type"] == "forecast_submitted") == len(versions)
    ids = [c["challenge_id"] for c in challenges]
    assert ids == sorted(set(ids)) == sorted(CHALLENGES), "one row per challenge"
    assert [c["final_brier_unadjusted"] for c in challenges] == ["0.2400", "0.4200"]
    assert all(v["adjustment"] == "" for v in versions)
    assert all(v["tool_calls_used"] <= v["evidence_budget_tool_calls"] for v in versions)
    assert [v["tool_calls_used"] for v in versions] == [2, 3, 5, 1, 1]
    assert [v["label_basis"] for v in versions] == ["", "publish_time", "", "", ""]
    assert all(v["submission_status"] == "synthetic_receipt" for v in versions)
    assert all(v["hash_basis"] == "full_body" and v["source_truncated"] == "false" for v in versions)
    print("self_check ok")


def main(argv: list[str]) -> None:
    for name, text in build().items():
        (HERE / name).write_text(text, encoding="utf-8", newline="")
    events = build_events()
    versions, challenges = build_rows(events)
    print(f"{len(events)} events, {len(versions)} versions, {len(challenges)} challenges")
    for v in versions:
        print(f"  {v['challenge_id']} v{v['version']} {v['label']} brier={v['brier_unadjusted']}")
    if "--check" in argv:
        self_check()


if __name__ == "__main__":
    main(sys.argv[1:])
