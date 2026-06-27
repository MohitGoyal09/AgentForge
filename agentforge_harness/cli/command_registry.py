"""CommandRegistry — maps slash-command names to async handler functions.

Every handler: async (argument: str, ctx: CommandContext) -> CommandResult.
Handlers must NOT call TUI methods; all display intent is encoded in CommandResult.
The CLI (or future TUI) reads the result and renders accordingly.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from agentforge_harness.cli.command_result import CommandResult
from agentforge_harness.cli.models import list_models_for_config
from agentforge_harness.config.config import ApprovalPolicy, Config, ModelProvider
from agentforge_harness.client.thinking import ThinkingLevel
from agentforge_harness.agent.modes import AgentMode

Handler = Callable[[str, Any], Awaitable[CommandResult]]


# ---------------------------------------------------------------------------
# CommandContext
# ---------------------------------------------------------------------------


@dataclass
class CommandContext:
    """All state a command handler may need.  No TUI reference — handlers
    must not render; they return CommandResult instead."""

    session: Any | None         # Session (Any to avoid circular import)
    config: Config
    agent: Any | None           # Agent (Any to avoid circular import)
    last_user_message: str = ""


# ---------------------------------------------------------------------------
# CommandRegistry
# ---------------------------------------------------------------------------


class CommandRegistry:
    """Maps slash-command names to async handler functions."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, handler: Handler, *names: str) -> None:
        for name in names:
            self._handlers[name] = handler

    async def dispatch(
        self,
        name: str,
        argument: str,
        ctx: CommandContext,
    ) -> CommandResult:
        handler = self._handlers.get(name)
        if handler is None:
            return CommandResult(handled=False)
        return await handler(argument, ctx)

    @property
    def known_commands(self) -> list[str]:
        return sorted(self._handlers.keys())


# ---------------------------------------------------------------------------
# Pagination helpers
# ---------------------------------------------------------------------------


def _paginate(items: list[Any], *, page: int, limit: int) -> tuple[list[Any], int, int]:
    total_count = len(items)
    total_pages = max(1, math.ceil(total_count / limit)) if limit else 1
    page = min(max(page, 1), total_pages)
    start = (page - 1) * limit
    return items[start : start + limit], total_pages, total_count


def _parse_page_args(argument: str, *, default_limit: int = 10) -> tuple[int, int]:
    page, limit = 1, default_limit
    parts = argument.split()
    i = 0
    while i < len(parts):
        part = parts[i]
        if part in {"--page", "-p"} and i + 1 < len(parts):
            try:
                page = max(int(parts[i + 1]), 1)
            except ValueError:
                pass
            i += 2
            continue
        if part in {"--limit", "-n"} and i + 1 < len(parts):
            try:
                limit = min(max(int(parts[i + 1]), 1), 100)
            except ValueError:
                pass
            i += 2
            continue
        if part.isdigit():
            try:
                page = max(int(part), 1)
            except ValueError:
                pass
        i += 1
    return page, limit


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _h_exit(argument: str, ctx: CommandContext) -> CommandResult:
    return CommandResult(exit=True)


async def _h_help(argument: str, ctx: CommandContext) -> CommandResult:
    return CommandResult(data_type="help")


async def _h_clear(argument: str, ctx: CommandContext) -> CommandResult:
    if ctx.session and ctx.session.context_manager:
        ctx.session.context_manager.clear()
    return CommandResult(clear=True, notice="Conversation history cleared")


async def _h_config(argument: str, ctx: CommandContext) -> CommandResult:
    return CommandResult(data_type="config", data=ctx.config.to_dict())


async def _h_doctor(argument: str, ctx: CommandContext) -> CommandResult:
    from agentforge_harness.cli.doctor import build_doctor_report
    report = build_doctor_report(ctx.config)
    fix_messages: list[str] = []
    if argument == "fix":
        fix_messages = _doctor_safe_fixes(report, ctx.config)
    return CommandResult(
        data_type="doctor",
        data={"report": report, "fix": argument == "fix", "fix_messages": fix_messages},
    )


def _doctor_safe_fixes(report: Any, config: Config) -> list[str]:
    messages: list[str] = []
    from agentforge_harness.config.loader import get_system_config_path
    for check in report.checks:
        if check.name == "safety.env.gitignore" and check.status == "warn":
            gitignore = config.cwd / ".gitignore"
            existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
            if ".env" not in existing.splitlines():
                suffix = "" if not existing or existing.endswith("\n") else "\n"
                gitignore.write_text(f"{existing}{suffix}.env\n", encoding="utf-8")
                messages.append(f"Added .env to {gitignore}")
        elif check.name == "config.system" and check.status == "warn":
            path = get_system_config_path()
            if path.exists():
                os.chmod(path, 0o600)
                messages.append(f"Set private permissions on {path}")
    return messages or ["No safe automatic fixes were available."]


async def _h_provider(argument: str, ctx: CommandContext) -> CommandResult:
    from agentforge_harness.cli.setup import API_KEY_ENV, DEFAULT_BASE_URLS, DEFAULT_MODELS

    if not argument:
        rows = [
            ("provider", ctx.config.provider.value),
            ("model", ctx.config.model_name),
            ("base url", ctx.config.base_url or "provider default"),
            ("api key env", API_KEY_ENV[ctx.config.provider.value]),
            ("api key", "configured" if ctx.config.api_key else "missing"),
        ]
        return CommandResult(
            data_type="key_values",
            data={
                "title": "Provider",
                "rows": rows,
                "footer": "Usage: /provider <openrouter|openai|anthropic|custom> [base-url] [model]",
            },
        )

    tokens = argument.split()
    provider_name = tokens[0].lower()
    try:
        provider = ModelProvider(provider_name)
    except ValueError:
        choices = ", ".join(item.value for item in ModelProvider)
        return CommandResult(error=f"Unknown provider: {provider_name}\nChoices: {choices}")

    remaining = tokens[1:]
    default_model = DEFAULT_MODELS[provider.value]
    model_name, base_url = default_model, None

    if provider == ModelProvider.CUSTOM:
        if not remaining:
            return CommandResult(
                error="Usage: /provider custom <base-url> [model]\nExample: /provider custom http://localhost:11434/v1 local/model"
            )
        base_url = remaining[0]
        if len(remaining) > 1:
            model_name = remaining[1]
    else:
        base_url = DEFAULT_BASE_URLS[provider.value] or None
        if remaining:
            model_name = remaining[0]

    old_provider = ctx.config.provider.value
    old_model = ctx.config.model_name

    if ctx.session:
        ctx.session.set_provider(provider, model_name=model_name, base_url=base_url)
    else:
        ctx.config.model.provider = provider
        ctx.config.model.name = model_name
        ctx.config.model.base_url = base_url

    rows = [
        ("provider", f"{old_provider} -> {ctx.config.provider.value}"),
        ("model", f"{old_model} -> {ctx.config.model_name}"),
        ("base url", ctx.config.base_url or "provider default"),
        ("api key env", API_KEY_ENV[ctx.config.provider.value]),
        ("api key", "configured" if ctx.config.api_key else "missing"),
    ]
    return CommandResult(
        data_type="key_values",
        data={
            "title": "Provider",
            "rows": rows,
            "footer": "Runtime-only change. Run agentforge init to persist provider settings.",
        },
    )


async def _h_model(argument: str, ctx: CommandContext) -> CommandResult:
    if argument == "list":
        return await _h_models("", ctx)
    if not argument:
        return CommandResult(
            notice="\n".join([
                f"Current model: {ctx.config.model_name}",
                "Usage: /model <model-id>",
                "Example: /model openrouter/free",
            ]),
            notice_title="Model",
        )
    old_model = ctx.config.model_name
    if ctx.session:
        ctx.session.set_model_name(argument)
    else:
        ctx.config.model_name = argument
    return CommandResult(
        notice="\n".join([
            f"Model changed: {old_model} -> {ctx.config.model_name}",
            "This affects the current session. Use /reload to restore config.toml.",
        ]),
        notice_title="Model",
    )


async def _h_models(argument: str, ctx: CommandContext) -> CommandResult:
    page, limit = _parse_page_args(argument)
    result = await list_models_for_config(ctx.config, limit=max(limit * page, limit))
    items, total_pages, total_count = _paginate(result.models, page=page, limit=limit)
    return CommandResult(
        data_type="models",
        data={
            "provider": result.provider,
            "current_model": result.current_model,
            "models": items,
            "live": result.live,
            "message": result.message,
            "page": page,
            "total_pages": total_pages,
            "total_count": total_count,
        },
    )


async def _h_fallbacks(argument: str, ctx: CommandContext) -> CommandResult:
    parts = argument.split()
    action = parts[0].lower() if parts else ""
    values = parts[1:]

    if not action:
        chain = [ctx.config.model_name, *ctx.config.model.fallbacks]
        rows = [(str(i), m) for i, m in enumerate(chain, start=1)]
        return CommandResult(
            data_type="key_values",
            data={
                "title": "Fallbacks",
                "rows": rows,
                "footer": "Usage: /fallbacks add <model>, /fallbacks remove <model>, /fallbacks clear, /fallbacks set <model>...",
            },
        )
    if action == "add":
        if not values:
            return CommandResult(error="Usage: /fallbacks add <model>")
        added = [m for m in values if m != ctx.config.model_name and m not in ctx.config.model.fallbacks]
        ctx.config.model.fallbacks.extend(added)
        return CommandResult(
            notice=f"Added fallback(s): {', '.join(added) if added else 'none'}",
            notice_title="Fallbacks",
        )
    if action == "remove":
        if not values:
            return CommandResult(error="Usage: /fallbacks remove <model>")
        before = list(ctx.config.model.fallbacks)
        ctx.config.model.fallbacks = [m for m in before if m not in values]
        removed = [m for m in before if m not in ctx.config.model.fallbacks]
        return CommandResult(
            notice=f"Removed fallback(s): {', '.join(removed) if removed else 'none'}",
            notice_title="Fallbacks",
        )
    if action == "clear":
        count = len(ctx.config.model.fallbacks)
        ctx.config.model.fallbacks.clear()
        return CommandResult(notice=f"Cleared {count} fallback model(s)", notice_title="Fallbacks")
    if action == "set":
        ctx.config.model.fallbacks = [m for m in values if m != ctx.config.model_name]
        return CommandResult(
            notice=f"Fallback chain set to: {', '.join(ctx.config.model.fallbacks) or 'none'}",
            notice_title="Fallbacks",
        )
    return CommandResult(error="Usage: /fallbacks [add|remove|clear|set]")


async def _h_paths(argument: str, ctx: CommandContext) -> CommandResult:
    from agentforge_harness.config.loader import (
        get_config_dir, get_data_dir, get_global_skills_dir,
        get_system_config_path, get_user_skills_dir,
    )
    data_dir = get_data_dir()
    rows: list[tuple[str, str]] = [
        ("cwd", str(ctx.config.cwd)),
        ("config dir", str(get_config_dir())),
        ("system config", str(get_system_config_path())),
        ("workspace config", str(ctx.config.cwd / ".agentforge" / "config.toml")),
        ("env", str(get_config_dir() / ".env")),
        ("workspace env", str(ctx.config.cwd / ".env")),
        ("data dir", str(data_dir)),
        ("sessions", str(data_dir / "sessions")),
        ("checkpoints", str(data_dir / "checkpoints")),
        ("events", str(data_dir / "events")),
        ("user skills", str(get_user_skills_dir())),
        ("global skills", str(get_global_skills_dir())),
    ]
    rows.extend((f"skill root {i}", str(r)) for i, r in enumerate(ctx.config.skill_roots, start=1))
    return CommandResult(data_type="key_values", data={"title": "Paths", "rows": rows})


async def _h_compact(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session or not ctx.session.context_manager:
        return CommandResult(error="No active session")
    try:
        summary, usage = await ctx.session.context_manager.compress_old_messages(
            ctx.session.chat_compactor
        )
    except Exception as exc:
        return CommandResult(error=f"Compaction failed: {exc}", error_title="Compact")
    if not summary:
        return CommandResult(notice="Nothing to compact yet. Keep chatting first.", notice_title="Compact")
    if usage:
        ctx.session.context_manager.set_latest_usage(usage)
        ctx.session.context_manager.add_usage(usage)
    return CommandResult(
        compact=True,
        notice="Context compacted. Recent turns were preserved.",
        notice_title="Compact",
    )


async def _h_errors(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    limit = max(int(argument), 1) if argument.isdigit() else 10
    events = ctx.session.persistence.list_events(ctx.session.session_id, limit=200)
    rows: list[tuple[str, str]] = []
    for event in reversed(events):
        event_type = str(event.get("type", ""))
        payload = event.get("payload") or {}
        timestamp = str(event.get("timestamp", ""))
        message = ""
        if event_type == "agent_error":
            message = str(payload.get("error", ""))
        elif event_type == "tool_call_complete" and not payload.get("success", True):
            message = f"{payload.get('name', 'tool')}: {payload.get('error') or payload.get('output') or 'failed'}"
        elif event_type == "text_delta":
            content = str(payload.get("content", ""))
            if any(t in content.lower() for t in (" error:", "failed", "rate limit", "circuit open", "trying fallback")):
                message = content.strip()
        if message:
            rows.append((timestamp, " ".join(message.split())))
        if len(rows) >= limit:
            break
    return CommandResult(
        data_type="key_values",
        data={
            "title": "Recent Errors",
            "rows": rows,
            "border_style": "error" if rows else "border",
            "footer": "Showing newest first. Usage: /errors [count]",
        },
    )


async def _h_approval(argument: str, ctx: CommandContext) -> CommandResult:
    if not argument:
        modes = ", ".join(p.value for p in ApprovalPolicy)
        return CommandResult(
            notice=f"Current approval: {ctx.config.approval.value}\nModes: {modes}",
            notice_title="Approval",
        )
    try:
        ctx.config.approval = ApprovalPolicy(argument)
        if ctx.session:
            ctx.session.approval_manager.approval_policy = ctx.config.approval
        return CommandResult(notice=f"Approval set to: {ctx.config.approval.value}", notice_title="Approval")
    except ValueError:
        return CommandResult(error=f"Unknown approval mode: {argument}")


async def _h_thinking(argument: str, ctx: CommandContext) -> CommandResult:
    if not argument:
        levels = ", ".join(l.value for l in ThinkingLevel)
        return CommandResult(
            notice=f"Current thinking level: {ctx.config.thinking_level.value}\nAvailable levels: {levels}",
            notice_title="Thinking",
        )
    try:
        level = ThinkingLevel(argument)
        ctx.config.model.thinking = level
        if ctx.session:
            ctx.session.set_thinking_level(level)
        return CommandResult(notice=f"Thinking level set to: {level.value}", notice_title="Thinking")
    except ValueError:
        return CommandResult(error=f"Unknown thinking level: {argument}")


async def _h_tools(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    return CommandResult(data_type="tools", data=ctx.session.tool_registry.get_tools())


async def _h_skills(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    return CommandResult(
        data_type="skills",
        data={"skills": ctx.session.list_skills(), "active": ctx.session.active_skills},
    )


async def _h_skill(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    if not argument:
        return CommandResult(error="Usage: /skill <name>")
    try:
        skill = ctx.session.skills_manager.get_skill(argument)
        body = ctx.session.activate_skill(argument)
        return CommandResult(
            notice="\n".join([
                f"Activated skill: {argument}",
                "Reason: manual command",
                f"File: {skill.path}",
                f"Loaded {len(body.splitlines())} lines into prompt context.",
            ]),
            notice_title="Skill",
        )
    except (KeyError, ValueError) as exc:
        return CommandResult(error=str(exc))


async def _h_unskill(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    if not argument:
        return CommandResult(error="Usage: /unskill <name>")
    if ctx.session.deactivate_skill(argument):
        return CommandResult(notice=f"Unloaded skill from active context: {argument}", notice_title="Skill")
    return CommandResult(error=f"Skill is not active: {argument}")


async def _h_mcp(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    return CommandResult(data_type="mcp_servers", data=ctx.session.mcp_manager.get_all_servers())


async def _h_name(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    if not argument:
        label = ctx.session.name or ctx.session.session_id
        return CommandResult(notice=f"Session name: {label}", notice_title="Session")
    ctx.session.name = argument
    return CommandResult(notice=f"Session renamed to: {argument}", notice_title="Session")


async def _h_save(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    ctx.session.save_session()
    return CommandResult(notice=f"Saved session: {ctx.session.session_id}")


async def _h_sessions(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    page, limit = _parse_page_args(argument)
    items, total_pages, total_count = _paginate(
        ctx.session.persistence.list_sessions(), page=page, limit=limit
    )
    return CommandResult(
        data_type="sessions",
        data={"items": items, "page": page, "total_pages": total_pages, "total_count": total_count},
    )


async def _h_resume(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    if not argument:
        return CommandResult(error="Usage: /resume <session_id>")
    try:
        snapshot = ctx.session.persistence.load_session(argument)
    except ValueError as exc:
        return CommandResult(error=str(exc))
    if not snapshot:
        return CommandResult(error=f"Session not found: {argument}")
    ctx.session.restore_snapshot(snapshot)
    return CommandResult(notice=f"Resumed session: {snapshot.session_id}")


async def _h_checkpoint(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    checkpoint_id = ctx.session.save_checkpoint()
    return CommandResult(notice=f"Created checkpoint: {checkpoint_id}")


async def _h_checkpoints(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    page, limit = _parse_page_args(argument)
    items, total_pages, total_count = _paginate(
        ctx.session.persistence.list_checkpoints(), page=page, limit=limit
    )
    return CommandResult(
        data_type="checkpoints",
        data={"items": items, "page": page, "total_pages": total_pages, "total_count": total_count},
    )


async def _h_restore(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    if not argument:
        return CommandResult(error="Usage: /restore <checkpoint_id>")
    try:
        snapshot = ctx.session.persistence.load_checkpoint(argument)
    except ValueError as exc:
        return CommandResult(error=str(exc))
    if not snapshot:
        return CommandResult(error=f"Checkpoint not found: {argument}")
    ctx.session.restore_snapshot(snapshot)
    return CommandResult(notice=f"Restored checkpoint: {argument}")


async def _h_new(argument: str, ctx: CommandContext) -> CommandResult:
    if ctx.session:
        ctx.session.reset()
    return CommandResult(clear=True, notice="Session reset to clean state")


async def _h_reload(argument: str, ctx: CommandContext) -> CommandResult:
    from agentforge_harness.config.loader import load_config
    try:
        new_config = load_config(ctx.config.cwd)
    except Exception as exc:
        return CommandResult(error=f"Config reload failed: {exc}")

    if ctx.session:
        ctx.session.config = new_config
        if ctx.agent:
            ctx.agent.config = new_config
        ctx.session.approval_manager.approval_policy = new_config.approval
        ctx.session.approval_manager.cwd = new_config.cwd
        if ctx.session.context_manager:
            ctx.session.context_manager.config = new_config
            ctx.session.context_manager.refresh_system_prompt(
                tools=ctx.session.tool_registry.get_tools(mode=ctx.session.mode),
                mode=ctx.session.mode,
                skills=ctx.session.skills_manager.list_skills(),
                active_skills=ctx.session.active_skills,
                active_skill_bodies=ctx.session.skills_manager.get_active_skill_bodies(ctx.session.active_skills),
            )
    # Return new_config so the CLI can update its own self.config reference.
    return CommandResult(
        notice=f"Config reloaded: model={new_config.model_name}, approval={new_config.approval.value}",
        data_type="reload_config",
        data=new_config,
    )


async def _h_version(argument: str, ctx: CommandContext) -> CommandResult:
    from agentforge_harness.cli.run import VERSION
    return CommandResult(notice=f"AgentForge {VERSION}", notice_title="Version")


async def _h_retry(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.last_user_message:
        return CommandResult(error="No previous message to retry")
    return CommandResult(retry=True)


async def _h_history(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session or not ctx.session.context_manager:
        return CommandResult(error="No active session")
    msgs = ctx.session.context_manager._messages
    n = 10
    if argument:
        try:
            n = max(int(argument), 1)
        except ValueError:
            pass
    recent = msgs[-n:] if len(msgs) > n else msgs
    lines = [f"=== Last {len(recent)} message(s) ==="]
    for msg in recent:
        preview = msg.content[:200].replace("\n", "\\n") if msg.content else ""
        tc = msg.token_count or ""
        if msg.role == "tool" and msg.tool_call_id:
            lines.append(
                f"  [{msg.role}] ({msg.tool_call_id[:8]}): {preview}"
                + (f" [{tc}t]" if tc else "")
            )
        else:
            n_calls = len(msg.tool_calls) if msg.tool_calls else 0
            calls = f" [{n_calls} tool call(s)]" if n_calls else ""
            lines.append(
                f"  [{msg.role}]{calls}: {preview}" + (f" [{tc}t]" if tc else "")
            )
    return CommandResult(data_type="history", data={"lines": lines})


async def _h_report(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    from agentforge_harness.cli.report import build_session_report, format_session_report, report_to_json
    s = ctx.session
    snapshot = s.create_snapshot(mode=s.mode.value)
    report = build_session_report(snapshot)
    is_json = argument == "--json"
    text = report_to_json(report) if is_json else format_session_report(report)
    return CommandResult(data_type="report", data={"text": text, "is_json": is_json})


async def _h_plan(argument: str, ctx: CommandContext) -> CommandResult:
    if ctx.session:
        ctx.session.set_mode(AgentMode.PLAN)
    return CommandResult(switch_mode="plan")


async def _h_build(argument: str, ctx: CommandContext) -> CommandResult:
    if ctx.session:
        ctx.session.set_mode(AgentMode.BUILD)
    return CommandResult(switch_mode="build")


async def _h_todos(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    from agentforge_harness.tools.builtin.todo import TodosTool
    tool = ctx.session.tool_registry.get("todos")
    if argument == "--clear":
        if isinstance(tool, TodosTool):
            count = len(tool._todos)
            tool._todos.clear()
            return CommandResult(notice=f"Cleared {count} todo(s)", notice_title="Todos")
        return CommandResult(notice="Cleared 0 todo(s)", notice_title="Todos")
    items = list(tool._todos.items()) if isinstance(tool, TodosTool) else []
    return CommandResult(data_type="todos", data=items)


async def _h_stats(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    from agentforge_harness.tools.builtin.todo import TodosTool
    usage = ctx.session.context_manager.get_total_usage()
    tool = ctx.session.tool_registry.get("todos")
    todo_count = len(tool._todos) if isinstance(tool, TodosTool) else 0
    return CommandResult(
        data_type="stats",
        data={
            "turns": ctx.session._turn_count,
            "mode": ctx.session.mode.value,
            "todos": todo_count,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "cached_tokens": usage.cached_tokens,
        },
    )


async def _h_export(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    from pathlib import Path
    from agentforge_harness.cli.report import write_session_export
    fmt = argument or "markdown"
    if fmt not in ("markdown", "md", "html"):
        return CommandResult(error=f"Unknown export format: {fmt}")
    s = ctx.session
    snapshot = s.create_snapshot(mode=s.mode.value)
    out_path = write_session_export(snapshot, Path.cwd(), fmt)
    return CommandResult(notice=f"Exported session to: {out_path}", notice_title="Export")


async def _h_branch(argument: str, ctx: CommandContext) -> CommandResult:
    if not ctx.session:
        return CommandResult(error="No active session")
    choices = ctx.session.tree_choices()
    if not argument:
        return CommandResult(data_type="branch_choices", data=choices)

    target_id: str | None = None
    if argument.isdigit():
        pos = int(argument)
        for choice in choices:
            if choice["position"] == pos:
                target_id = choice["id"]
                break
        if target_id is None:
            return CommandResult(error=f"No branch point at position {pos}. Run /branch to list choices.")
    else:
        matches = [c["id"] for c in choices if c["id"].startswith(argument)]
        if len(matches) == 0:
            return CommandResult(error=f"No branch point matches: {argument!r}. Run /branch to list choices.")
        if len(matches) > 1:
            return CommandResult(error=f"Ambiguous prefix {argument!r} matches {len(matches)} entries.")
        target_id = matches[0]

    try:
        ctx.session.branch_to_entry(target_id)
    except ValueError as exc:
        return CommandResult(error=str(exc))

    preview = next((c["preview"][:60] for c in choices if c["id"] == target_id), target_id)
    return CommandResult(
        notice=f"Rewound to: {preview!r}\nNew messages will extend from this point.",
        notice_title="Branch",
    )


# ---------------------------------------------------------------------------
# Registry factory + module-level singleton
# ---------------------------------------------------------------------------


def build_registry() -> CommandRegistry:
    """Return a fully-populated CommandRegistry."""
    registry = CommandRegistry()
    registry.register(_h_exit, "/exit", "/quit")
    registry.register(_h_help, "/help")
    registry.register(_h_clear, "/clear")
    registry.register(_h_config, "/config")
    registry.register(_h_doctor, "/doctor")
    registry.register(_h_provider, "/provider")
    registry.register(_h_model, "/model")
    registry.register(_h_models, "/models")
    registry.register(_h_fallbacks, "/fallbacks")
    registry.register(_h_paths, "/paths")
    registry.register(_h_compact, "/compact")
    registry.register(_h_errors, "/errors")
    registry.register(_h_approval, "/approval")
    registry.register(_h_thinking, "/thinking")
    registry.register(_h_tools, "/tools")
    registry.register(_h_skills, "/skills")
    registry.register(_h_skill, "/skill")
    registry.register(_h_unskill, "/unskill")
    registry.register(_h_mcp, "/mcp")
    registry.register(_h_name, "/name")
    registry.register(_h_save, "/save")
    registry.register(_h_sessions, "/sessions")
    registry.register(_h_resume, "/resume")
    registry.register(_h_checkpoint, "/checkpoint")
    registry.register(_h_checkpoints, "/checkpoints")
    registry.register(_h_restore, "/restore")
    registry.register(_h_new, "/new")
    registry.register(_h_reload, "/reload")
    registry.register(_h_version, "/version")
    registry.register(_h_retry, "/retry")
    registry.register(_h_history, "/history")
    registry.register(_h_report, "/report")
    registry.register(_h_plan, "/plan")
    registry.register(_h_build, "/build")
    registry.register(_h_todos, "/todos")
    registry.register(_h_stats, "/stats")
    registry.register(_h_export, "/export")
    registry.register(_h_branch, "/branch", "/rewind")
    return registry


_REGISTRY: CommandRegistry | None = None


def get_registry() -> CommandRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = build_registry()
    return _REGISTRY
