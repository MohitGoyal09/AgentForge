from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from agentforge_harness.agent.persistence import SessionSnapshot


def build_session_report(snapshot: SessionSnapshot) -> dict[str, Any]:
    model_config = snapshot.config.get("model", {}) if isinstance(snapshot.config, dict) else {}
    todos = snapshot.todos or {}

    return {
        "schema_version": snapshot.schema_version,
        "session_id": snapshot.session_id,
        "name": snapshot.name or "",
        "mode": snapshot.mode,
        "cwd": snapshot.cwd,
        "created_at": snapshot.created_at.isoformat(),
        "updated_at": snapshot.updated_at.isoformat(),
        "turn_count": snapshot.turn_count,
        "message_count": len(snapshot.messages or []),
        "model": {
            "provider": model_config.get("provider"),
            "name": model_config.get("name"),
        },
        "usage": {
            "prompt_tokens": snapshot.total_usage.prompt_tokens,
            "completion_tokens": snapshot.total_usage.completion_tokens,
            "total_tokens": snapshot.total_usage.total_tokens,
            "cached_tokens": snapshot.total_usage.cached_tokens,
        },
        "tools": {
            "count": len(snapshot.active_tools),
            "names": snapshot.active_tools,
        },
        "mcp_servers": snapshot.mcp_servers,
        "skills": snapshot.active_skills,
        "todos": {
            "count": len(todos),
            "items": todos,
        },
    }


def format_session_report(report: dict[str, Any]) -> str:
    model = report.get("model", {})
    usage = report.get("usage", {})
    todos = report.get("todos", {})
    tools = report.get("tools", {})

    lines = [
        f"  Session: {report.get('name') or str(report.get('session_id', ''))[:8]}",
        f"  Model: {model.get('name') or 'unknown'}",
        f"  Provider: {model.get('provider') or 'unknown'}",
        f"  Mode: {report.get('mode')}",
        f"  Turns: {report.get('turn_count')}",
        f"  Messages: {report.get('message_count')}",
        f"  Created: {report.get('created_at')}",
        f"  Updated: {report.get('updated_at')}",
        f"  Active skills: {', '.join(report.get('skills') or []) or 'none'}",
        f"  Tools: {tools.get('count', 0)} registered",
        f"  Active todos: {todos.get('count', 0)}",
        f"  Prompt tokens: {usage.get('prompt_tokens', 0)}",
        f"  Completion tokens: {usage.get('completion_tokens', 0)}",
        f"  Total tokens: {usage.get('total_tokens', 0)}",
    ]
    cached_tokens = usage.get("cached_tokens", 0)
    if cached_tokens:
        lines.append(f"  Cached tokens: {cached_tokens}")
    return "\n".join(lines)


def render_session_markdown(snapshot: SessionSnapshot) -> str:
    report = build_session_report(snapshot)
    lines = [
        f"# Session: {snapshot.name or snapshot.session_id}",
        "",
        "## Summary",
        "",
        format_session_report(report).strip(),
        "",
        "## Transcript",
    ]

    for msg in snapshot.messages or []:
        role = msg.get("role", "")
        content = msg.get("content", "") or ""
        tool_calls = msg.get("tool_calls")
        if role == "user":
            lines.append(f"\n**User:** {content}")
        elif role == "assistant":
            if content:
                lines.append(f"\n**Assistant:** {content}")
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "tool")
                    lines.append(f"\n*Tool call:* `{name}(...)`")
        elif role == "tool":
            tool_id = msg.get("tool_call_id", "")[:8]
            preview = content[:1000].replace("\n", "\\n") if content else "(empty)"
            lines.append(f"\n*Tool result [{tool_id}]:* `{preview}`")

    return "\n".join(lines) + "\n"


def render_session_html(snapshot: SessionSnapshot) -> str:
    report = build_session_report(snapshot)
    summary_cards = "\n".join(
        f'<div class="metric"><span>{html.escape(key)}</span><strong>{html.escape(str(value))}</strong></div>'
        for key, value in _flatten_report_summary(report).items()
    )
    usage = report.get("usage", {})
    usage_rows = "\n".join(
        f"<tr><th>{html.escape(key)}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in {
            "Prompt tokens": usage.get("prompt_tokens", 0),
            "Completion tokens": usage.get("completion_tokens", 0),
            "Total tokens": usage.get("total_tokens", 0),
            "Cached tokens": usage.get("cached_tokens", 0),
        }.items()
    )
    transcript = "\n".join(_render_message_html(msg) for msg in snapshot.messages or [])

    title = html.escape(snapshot.name or snapshot.session_id)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentForge Session - {title}</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; line-height: 1.5; color: #17202a; background: #f6f8fa; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 2rem; }}
    header {{ margin-bottom: 1.5rem; }}
    h1 {{ margin: 0 0 0.25rem; }}
    h2 {{ margin-top: 2rem; }}
    .subtle {{ color: #57606a; margin: 0; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.75rem; margin: 1rem 0 1.5rem; }}
    .metric {{ background: #fff; border: 1px solid #d8dee4; border-radius: 6px; padding: 0.75rem; }}
    .metric span {{ display: block; color: #57606a; font-size: 0.78rem; text-transform: uppercase; }}
    .metric strong {{ display: block; font-size: 1rem; overflow-wrap: anywhere; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; }}
    th, td {{ border: 1px solid #d8dee4; padding: 0.45rem 0.6rem; text-align: left; vertical-align: top; }}
    th {{ width: 13rem; background: #f6f8fa; }}
    details.msg {{ background: #fff; border: 1px solid #d8dee4; border-radius: 6px; padding: 0.8rem 1rem; margin: 0.8rem 0; }}
    details.msg summary {{ cursor: pointer; font-weight: 700; }}
    .role-user summary {{ color: #0969da; }}
    .role-assistant summary {{ color: #1a7f37; }}
    .role-tool summary {{ color: #8250df; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; margin: 0; }}
    .content {{ margin-top: 0.75rem; }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #0d1117; color: #e6edf3; }}
      .metric, details.msg {{ background: #161b22; border-color: #30363d; }}
      table th, table td {{ border-color: #30363d; }}
      th {{ background: #161b22; }}
      .subtle, .metric span {{ color: #8b949e; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>AgentForge Session</h1>
    <p class="subtle">{title}</p>
  </header>
  <h2>Summary</h2>
  <section class="metrics">
    {summary_cards}
  </section>
  <h2>Usage</h2>
  <table>
    {usage_rows}
  </table>
  <h2>Transcript</h2>
  {transcript}
</main>
</body>
</html>
"""


def write_session_export(snapshot: SessionSnapshot, output_dir: Path, fmt: str) -> Path:
    normalized = fmt.lower()
    if normalized in {"markdown", "md"}:
        path = output_dir / f"session-{snapshot.session_id[:8]}.md"
        path.write_text(render_session_markdown(snapshot), encoding="utf-8")
        return path
    if normalized == "html":
        path = output_dir / f"session-{snapshot.session_id[:8]}.html"
        path.write_text(render_session_html(snapshot), encoding="utf-8")
        return path
    raise ValueError(f"Unknown export format: {fmt}")


def report_to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def _flatten_report_summary(report: dict[str, Any]) -> dict[str, Any]:
    model = report.get("model", {})
    usage = report.get("usage", {})
    todos = report.get("todos", {})
    tools = report.get("tools", {})
    return {
        "Session": report.get("name") or report.get("session_id"),
        "Mode": report.get("mode"),
        "Model": model.get("name") or "unknown",
        "Provider": model.get("provider") or "unknown",
        "Turns": report.get("turn_count"),
        "Messages": report.get("message_count"),
        "Tools": tools.get("count", 0),
        "Active skills": ", ".join(report.get("skills") or []) or "none",
        "Todos": todos.get("count", 0),
        "CWD": report.get("cwd"),
        "Updated": report.get("updated_at"),
    }


def _render_message_html(msg: dict[str, Any]) -> str:
    role = html.escape(str(msg.get("role", "unknown")))
    content = html.escape(str(msg.get("content", "") or ""))
    tool_calls = msg.get("tool_calls")
    tool_call_details = ""
    if tool_calls:
        payload = html.escape(json.dumps(tool_calls, indent=2, default=str))
        tool_call_details = f"<details><summary>Tool calls</summary><pre>{payload}</pre></details>"
    title = html.escape(_message_title(msg))
    open_attr = " open" if role != "tool" else ""
    return f"""<details class="msg role-{role}"{open_attr}>
  <summary>{title}</summary>
  <div class="content"><pre>{content}</pre></div>
  {tool_call_details}
</details>"""


def _message_title(msg: dict[str, Any]) -> str:
    role = str(msg.get("role", "unknown"))
    if role == "tool":
        tool_id = str(msg.get("tool_call_id", ""))[:8]
        return f"Tool result {tool_id}" if tool_id else "Tool result"
    content = str(msg.get("content", "") or "").strip().splitlines()
    preview = content[0][:80] if content else ""
    return f"{role.title()}: {preview}" if preview else role.title()
