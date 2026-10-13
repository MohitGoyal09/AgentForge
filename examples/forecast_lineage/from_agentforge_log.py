"""Convert a REAL AgentForge event log into forecast-lineage rows (stdlib only).

Usage: python from_agentforge_log.py <events.jsonl> <out_dir>
Writes versions.csv (same columns as the synthetic example) and gaps.md (every
field the log could not fill, and why). The label rule and Brier code come from
build_example.py; this file only maps real events onto its inputs.
"""
from __future__ import annotations

import csv
import fnmatch
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_example as be  # noqa: E402

FAILED_TOOL = "tool_call_complete (success=false)"


def _utc(stamp: str) -> str:
    """Older logs wrote naive timestamps; read them as UTC so comparisons work."""
    dt = datetime.fromisoformat(stamp)
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def convert(raw: list[dict]) -> tuple[list[dict], list[str]]:
    """Return (version rows, gap lines). Builds a normalized event view for be.classify."""
    starts = {e["payload"]["call_id"]: e["payload"] for e in raw if e["type"] == "tool_call_start"}
    gaps: list[str] = []
    norm: list[dict] = []          # events shaped for be.classify
    sources: list[dict] = []       # {seq, url, time}
    submissions: list[dict] = []   # {event, body, path}
    recovery_counts: Counter = Counter()
    web_fetch_seqs: list[int] = []
    truncated: list[dict] = []

    for e in raw:
        t, p, seq, when = e["type"], e["payload"], e["sequence"], _utc(e["timestamp"])
        if t in be.RECOVERY_TYPES:
            recovery_counts[t] += 1
            norm.append({"sequence": seq, "type": t, "timestamp": when, "payload": {}})
        if t != "tool_call_complete":
            continue
        args = starts.get(p["call_id"], {}).get("arguments", {})
        if not p["success"]:
            recovery_counts[FAILED_TOOL] += 1
            norm.append({"sequence": seq, "type": "agent_error", "timestamp": when, "payload": {}})
        if p["name"] == "web_fetch":
            web_fetch_seqs.append(seq)
        if p["name"] == "web_fetch" and p["success"]:
            src = {"seq": seq, "url": args.get("url", ""), "time": when}
            cut = p.get("metadata", {}).get("output_hygiene", {}).get("truncated_fields")
            if p.get("truncated") or cut:
                truncated.append(src)
            sources.append(src)
            # publish_time is unknown; the retrieval time stands in for it (the proxy rule).
            norm.append({"sequence": seq, "type": "source_retrieved", "timestamp": when, "payload": {
                "publish_time": when, "sha256": hashlib.sha256(p["output"].encode()).hexdigest()}})
        elif p["name"] == "write_file" and p["success"] and fnmatch.fnmatch(
                PurePosixPath(args.get("path", "")).name, "forecast_v*.json"):
            try:
                body = json.loads(args["content"])
                submissions.append({"event": e, "body": body, "path": args["path"]})
            except (KeyError, ValueError):
                gaps.append(f"- `{args.get('path')}` (seq {seq}): content is not valid JSON, no version row written.")

    rows: list[dict] = []
    prev_of: dict[str, dict] = {}
    for s in submissions:
        e, b = s["event"], s["body"]
        seq, when = e["sequence"], _utc(e["timestamp"])
        try:
            cid, probs = b["challenge_id"], {k: float(b["probabilities"][k]) for k in be.CATEGORIES}
            version, urls = int(b["version"]), list(b.get("cited_urls", []))
        except (KeyError, TypeError, ValueError) as err:
            gaps.append(f"- `{s['path']}` (seq {seq}): missing or bad field ({err!r}), no version row written.")
            continue
        if abs(sum(probs.values()) - 1) > 1e-6:
            gaps.append(f"- `{s['path']}`: probabilities sum to {sum(probs.values()):.4f}, not 1. Row kept as written.")
        cited, ghosts = [], []
        for url in urls:
            hits = [x["seq"] for x in sources if x["url"] == url and x["seq"] < seq]
            if hits:
                if hits[-1] not in cited:
                    cited.append(hits[-1])
            else:
                ghosts.append(url)
        if ghosts:
            gaps.append(f"- `{s['path']}` (challenge {cid} v{version}) cites URLs that were never fetched "
                        f"(uncited or hallucinated source): {', '.join(ghosts)}")
        uncited = [x["url"] for x in sources if x["seq"] < seq and x["seq"] not in cited]
        if uncited:
            gaps.append(f"- `{s['path']}` fetched but did not cite: {', '.join(sorted(set(uncited)))}")
        sub = {"sequence": seq, "type": "forecast_submitted", "timestamp": when,
               "payload": {"cited_event_seqs": cited}}
        norm.append(sub)
        norm.sort(key=lambda x: x["sequence"])
        if cid in prev_of:
            label, _, recovery = be.classify(norm, prev_of[cid], sub)
        else:
            label, recovery = "initial", []
        prev_of[cid] = sub
        rows.append({
            "challenge_id": cid, "forecast_id": "", "revision_id": "", "version": version,
            "submitted_at": when, "p_bearish": probs["bearish"], "p_neutral": probs["neutral"],
            "p_bullish": probs["bullish"], "vector_provenance": "submitted", "receipt_id": "",
            "evidence_budget_tool_calls": "", "tool_calls_used": sum(1 for q in web_fetch_seqs if q <= seq),
            "cited_event_seqs": be.join(cited), "recovery_event_seqs": be.join(recovery),
            "label": label, "brier_unadjusted": "", "adjustment": "",
        })

    rows_note = f"{len(rows)} version row(s) from {len(sources)} successful web_fetch source(s)."
    header = [
        "# Gaps: what the real AgentForge log could not fill", "", rows_note, "",
        "## Fields left blank for every row", "",
        "- `publish_time` (source): web_fetch output and URL carry no publish time. Not stored in the CSV; "
        "sources: " + (", ".join(f"seq {x['seq']} {x['url']}" for x in sources) or "none") + ".",
        "- `label`: because publish_time is unknown, a cited source counts as new by a proxy: it was first "
        "retrieved after the previous submission AND its sha256 was unseen before then. This overstates "
        "novelty (a re-fetched page with a trivial change counts) and cannot tell a late-published source "
        "from an early-published one fetched late.",
        "- `forecast_id`, `revision_id`, `receipt_id`: the log has no forecast_submitted event and no submission receipt.",
        "- `submitted_at`: time the write_file call completed, not a platform acceptance time.",
        "- `vector_provenance`: always `submitted`; the log cannot say whether the agent reconstructed a vector.",
        "- `evidence_budget_tool_calls`: the budget exists only as prose in the prompt (agent_start message), not as an event.",
        "- `tool_calls_used`: all web_fetch completions (success or fail) up to the submission, cumulative "
        "for the whole session; the log has no challenge boundary and no count of other tools.",
        "- `brier_unadjusted`: outcome not known yet (no challenge_resolved event), so blank. `adjustment` stays blank.",
        "- sha256: taken over the logged tool output text, which is what the model saw.",
        "- truncated fetch output: " + (
            "; ".join(f"seq {x['seq']} {x['url']}" for x in truncated)
            + ". The model saw only a cut-down body, and the hash covers that body."
            if truncated else "none."), "",
        "## Recovery events seen in the log", "",
        ", ".join(f"{k}: {v}" for k, v in sorted(recovery_counts.items())) or "none",
        "", "## Per-forecast findings", "",
    ]
    return rows, header + (gaps or ["- none"])


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit("usage: from_agentforge_log.py <events.jsonl> <out_dir>")
    rows, gap_lines = convert(_read(Path(argv[0])))
    out = Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    (out / "versions.csv").write_text(be.to_csv(be.VERSION_COLUMNS, rows), encoding="utf-8", newline="")
    (out / "gaps.md").write_text("\n".join(gap_lines) + "\n", encoding="utf-8")
    print(f"{len(rows)} versions -> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
