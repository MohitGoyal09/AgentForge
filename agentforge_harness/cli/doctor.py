from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from agentforge_harness.config.config import ApprovalPolicy, Config
from agentforge_harness.config.loader import (
    get_data_dir,
    get_global_skills_dir,
    get_system_config_path,
    get_user_skills_dir,
)


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    message: str
    detail: str = ""


@dataclass(frozen=True)
class DoctorReport:
    checks: list[DoctorCheck]

    @property
    def has_errors(self) -> bool:
        return any(check.status == "error" for check in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(check.status == "warn" for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": not self.has_errors,
            "errors": sum(1 for check in self.checks if check.status == "error"),
            "warnings": sum(1 for check in self.checks if check.status == "warn"),
            "checks": [asdict(check) for check in self.checks],
        }


def build_doctor_report(config: Config) -> DoctorReport:
    checks: list[DoctorCheck] = []

    checks.extend(_check_package())
    checks.extend(_check_config(config))
    checks.extend(_check_config_files(config))
    checks.extend(_check_provider(config))
    checks.extend(_check_cwd(config))
    checks.extend(_check_workspace_paths(config))
    checks.extend(_check_data_dir())
    checks.extend(_check_skills(config))
    checks.extend(_check_mcp(config))
    checks.extend(_check_safety(config))

    return DoctorReport(checks=checks)


def print_doctor_report(
    report: DoctorReport,
    *,
    console: Console,
    json_output: bool = False,
) -> None:
    if json_output:
        console.file.write(json.dumps(report.to_dict(), indent=2) + "\n")
        return

    border_style = "error" if report.has_errors else "warning" if report.has_warnings else "success"
    console.print(
        Panel(
            _doctor_compact_body(report, border_style),
            title=Text("Doctor", style=border_style),
            title_align="left",
            border_style=border_style,
            padding=(1, 2),
            width=min(console.width, 110),
        )
    )


def _status_marker(status: str) -> tuple[str, str]:
    if status == "ok":
        return "OK", "success"
    if status == "warn":
        return "WARN", "warning"
    return "ERROR", "error"


def _doctor_compact_body(report: DoctorReport, border_style: str) -> Text:
    error_count = sum(1 for check in report.checks if check.status == "error")
    warning_count = sum(1 for check in report.checks if check.status == "warn")
    ok_count = sum(1 for check in report.checks if check.status == "ok")

    if error_count:
        headline = "AgentForge is not ready yet."
        next_step = "Fix the errors below, then run agentforge doctor again."
    elif warning_count:
        headline = "AgentForge can run, but a few things need attention."
        next_step = "Warnings are usually safe for local testing, but review them before release."
    else:
        headline = "AgentForge looks ready."
        next_step = "You can start the TUI with agentforge."

    text = Text()
    text.append(headline + "\n", style=border_style)
    text.append(
        f"{ok_count} ok, {warning_count} warning(s), {error_count} error(s)\n\n",
        style="code",
    )
    text.append(next_step + "\n\n", style="muted")

    sections = _doctor_sections(report)
    for index, (title, checks) in enumerate(sections):
        _append_compact_section(text, title, checks)
        if index != len(sections) - 1:
            text.append("\n")

    return text


def _doctor_sections(report: DoctorReport) -> list[tuple[str, list[DoctorCheck]]]:
    groups = [
        ("Setup", ("package", "config", "config.")),
        ("Provider", ("provider.",)),
        ("Workspace", ("cwd", "paths.", "data_dir")),
        ("Skills", ("skills", "skills.")),
        ("MCP", ("mcp", "mcp.")),
        ("Safety", ("safety.",)),
    ]

    sections: list[tuple[str, list[DoctorCheck]]] = []
    assigned: set[int] = set()
    for title, prefixes in groups:
        checks = [
            check
            for index, check in enumerate(report.checks)
            if index not in assigned and _matches_group(check.name, prefixes)
        ]
        if not checks:
            continue
        check_ids = {id(check) for check in checks}
        for index, check in enumerate(report.checks):
            if id(check) in check_ids:
                assigned.add(index)
        sections.append((title, checks))

    remaining = [
        check for index, check in enumerate(report.checks)
        if index not in assigned
    ]
    if remaining:
        sections.append(("Other", remaining))
    return sections


def _matches_group(name: str, prefixes: tuple[str, ...]) -> bool:
    return any(name == prefix.rstrip(".") or name.startswith(prefix) for prefix in prefixes)


def _append_compact_section(text: Text, title: str, checks: list[DoctorCheck]) -> None:
    group_status = _worst_status(checks)
    marker, marker_style = _status_marker(group_status)
    ok_count = sum(1 for check in checks if check.status == "ok")
    warning_count = sum(1 for check in checks if check.status == "warn")
    error_count = sum(1 for check in checks if check.status == "error")

    text.append(f"{marker:<5} ", style=marker_style)
    text.append(title, style="highlight")
    text.append(f"  {ok_count} ok")
    if warning_count:
        text.append(f", {warning_count} warn", style="warning")
    if error_count:
        text.append(f", {error_count} error", style="error")
    text.append("\n")

    visible_checks = [check for check in checks if check.status != "ok"]
    if not visible_checks:
        return

    for check in visible_checks:
        marker, marker_style = _status_marker(check.status)
        text.append(f"  {marker:<5} ", style=marker_style)
        text.append(check.name, style="code")
        text.append(f" - {_truncate(check.message)}\n", style="assistant")
        if check.detail:
            text.append(f"        detail: {_truncate(check.detail)}\n", style="muted")
        fix_hint = _fix_hint(check)
        if fix_hint:
            text.append(f"        fix: {_truncate(fix_hint)}\n", style="warning")


def _truncate(value: str, limit: int = 96) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "..."


def _worst_status(checks: list[DoctorCheck]) -> str:
    statuses = {check.status for check in checks}
    if "error" in statuses:
        return "error"
    if "warn" in statuses:
        return "warn"
    return "ok"


def _fix_hint(check: DoctorCheck) -> str | None:
    if check.status == "ok":
        return None
    if check.name == "provider.key":
        return "Run agentforge init, or set the provider API key environment variable."
    if check.name == "provider.base_url":
        return "Set model.base_url in config.toml or BASE_URL in the environment."
    if check.name in {"config.files", "config"}:
        return "Run agentforge init, or edit the reported config file."
    if check.name.startswith("config.") and (
        "permissions" in check.message.lower()
        or "readable or writable" in check.message.lower()
    ):
        return "Run chmod 600 on the config file."
    if check.name == "data_dir":
        return "Check directory permissions or run with a writable HOME/AgentForge data directory."
    if check.name == "safety.env.permissions":
        return "Run chmod 600 .env."
    if check.name == "safety.env.git":
        return "Remove .env from git tracking and rotate any exposed keys."
    if check.name == "safety.env.gitignore":
        return "Add .env to .gitignore."
    if check.name == "mcp.trust":
        return "Only configure MCP servers you trust; AgentForge does not sandbox them yet."
    if check.name.startswith("mcp.") and "not found" in check.message.lower():
        return "Install the command, fix the MCP config, or disable this server."
    if check.name.startswith("paths."):
        return "Prefer paths inside the workspace unless you intentionally trust the external path."
    if check.name.startswith("skills."):
        return "Create .agentforge/skills or ~/.agents/skills, or disable skills if unused."
    if check.name == "safety.approval":
        return 'Use approval = "on-request" for normal interactive work.'
    if check.name.startswith("safety.") and "disabled" in check.message.lower():
        return "Enable this safety flag in config.toml for normal use."
    return None


def _check_package() -> list[DoctorCheck]:
    try:
        package_version = version("agentforge-harness")
    except PackageNotFoundError:
        package_version = "0.1.0"

    return [
        DoctorCheck(
            name="package",
            status="ok",
            message=f"AgentForge {package_version}",
            detail="CLI import succeeded",
        )
    ]


def _check_config(config: Config) -> list[DoctorCheck]:
    errors = config.validate()
    if not errors:
        return [
            DoctorCheck(
                name="config",
                status="ok",
                message="Configuration is valid",
                detail=str(config.cwd),
            )
        ]

    return [
        DoctorCheck(
            name="config",
            status="error",
            message=error,
            detail="Fix config or run agentforge init",
        )
        for error in errors
    ]


def _check_config_files(config: Config) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    paths = [
        ("config.system", get_system_config_path()),
        ("config.project", config.cwd / ".agentforge" / "config.toml"),
    ]

    for name, path in paths:
        if not path.exists():
            continue
        checks.append(_file_permission_check(name, path, recommended_private=True))

    if checks:
        return checks

    return [
        DoctorCheck(
            name="config.files",
            status="warn",
            message="No config.toml file found",
            detail="Defaults are in use; run agentforge init for a saved config",
        )
    ]


def _check_provider(config: Config) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    provider = config.provider.value

    if config.api_key:
        checks.append(
            DoctorCheck(
                name="provider.key",
                status="ok",
                message=f"API key found for {provider}",
                detail="Secret value is not displayed",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                name="provider.key",
                status="error",
                message=f"No API key found for {provider}",
                detail="Run agentforge init or set provider-specific environment variable",
            )
        )

    checks.append(
        DoctorCheck(
            name="provider.model",
            status="ok" if config.model_name else "error",
            message=config.model_name or "Model name is empty",
            detail=f"provider={provider}",
        )
    )

    if config.provider.value == "custom" and not config.base_url:
        checks.append(
            DoctorCheck(
                name="provider.base_url",
                status="error",
                message="Custom provider requires a base URL",
                detail="Set model.base_url or BASE_URL",
            )
        )
    elif config.base_url:
        checks.append(
            DoctorCheck(
                name="provider.base_url",
                status="ok",
                message=config.base_url,
                detail="Resolved provider base URL",
            )
        )

    return checks


def _check_cwd(config: Config) -> list[DoctorCheck]:
    cwd = config.cwd
    if not cwd.exists():
        return [
            DoctorCheck(
                name="cwd",
                status="error",
                message="Working directory does not exist",
                detail=str(cwd),
            )
        ]
    if not cwd.is_dir():
        return [
            DoctorCheck(
                name="cwd",
                status="error",
                message="Working directory is not a directory",
                detail=str(cwd),
            )
        ]

    return [
        DoctorCheck(
            name="cwd",
            status="ok",
            message="Working directory is readable",
            detail=str(cwd),
        )
    ]


def _check_workspace_paths(config: Config) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    root = config.cwd.resolve()

    for name, server in config.mcp_servers.items():
        if not server.cwd:
            continue
        resolved = server.cwd.expanduser()
        if not resolved.is_absolute():
            resolved = root / resolved
        try:
            resolved = resolved.resolve()
        except OSError:
            continue
        if not _is_relative_to(resolved, root):
            checks.append(
                DoctorCheck(
                    name=f"paths.mcp.{name}",
                    status="warn",
                    message="MCP server cwd is outside the workspace",
                    detail=str(resolved),
                )
            )

    for hook in config.hooks:
        if not hook.enabled or not hook.script:
            continue
        path = Path(hook.script).expanduser()
        if not path.is_absolute():
            path = root / path
        try:
            path = path.resolve()
        except OSError:
            continue
        if not _is_relative_to(path, root):
            checks.append(
                DoctorCheck(
                    name=f"paths.hook.{hook.name}",
                    status="warn",
                    message="Hook script is outside the workspace",
                    detail=str(path),
                )
            )

    if checks:
        return checks

    return [
        DoctorCheck(
            name="paths.workspace",
            status="ok",
            message="Configured workspace paths look scoped",
            detail=str(root),
        )
    ]


def _check_data_dir() -> list[DoctorCheck]:
    data_dir = get_data_dir()
    probe = data_dir / ".doctor-write-test"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as exc:
        return [
            DoctorCheck(
                name="data_dir",
                status="error",
                message="Data directory is not writable",
                detail=f"{data_dir}: {exc}",
            )
        ]

    return [
        DoctorCheck(
            name="data_dir",
            status="ok",
            message="Data directory is writable",
            detail=str(data_dir),
        )
    ]


def _check_skills(config: Config) -> list[DoctorCheck]:
    if not config.skills_enabled:
        return [
            DoctorCheck(
                name="skills",
                status="warn",
                message="Skills are disabled",
                detail="skills_enabled=false",
            )
        ]

    checks: list[DoctorCheck] = []
    if config.skill_roots:
        checks.append(
            DoctorCheck(
                name="skills.roots",
                status="ok",
                message=f"{len(config.skill_roots)} skill root(s) detected",
                detail=", ".join(str(root) for root in config.skill_roots[:3]),
            )
        )
    else:
        checks.append(
            DoctorCheck(
                name="skills.roots",
                status="warn",
                message="No skill roots detected",
                detail="Create .agentforge/skills or ~/.agents/skills",
            )
        )

    global_skills = get_global_skills_dir()
    user_skills = get_user_skills_dir()
    if not global_skills.exists() and not user_skills.exists():
        checks.append(
            DoctorCheck(
                name="skills.global",
                status="warn",
                message="No global skill directory found",
                detail=f"Checked {global_skills} and {user_skills}",
            )
        )

    return checks


def _check_mcp(config: Config) -> list[DoctorCheck]:
    if not config.mcp_servers:
        return [
            DoctorCheck(
                name="mcp",
                status="ok",
                message="No MCP servers configured",
                detail="",
            )
        ]

    checks: list[DoctorCheck] = [
        DoctorCheck(
            name="mcp.trust",
            status="warn",
            message="MCP servers are trusted executable integrations",
            detail="AgentForge does not sandbox MCP servers yet",
        )
    ]

    for name, server in config.mcp_servers.items():
        if not server.enabled:
            checks.append(
                DoctorCheck(
                    name=f"mcp.{name}",
                    status="warn",
                    message="MCP server is disabled",
                    detail=name,
                )
            )
            continue

        if server.command:
            command_path = Path(server.command).expanduser()
            command_ok = command_path.exists() if command_path.is_absolute() else shutil.which(server.command) is not None
            checks.append(
                DoctorCheck(
                    name=f"mcp.{name}",
                    status="ok" if command_ok else "error",
                    message="Command found" if command_ok else "Command not found",
                    detail=server.command,
                )
            )
        elif server.url:
            checks.append(
                DoctorCheck(
                    name=f"mcp.{name}",
                    status="ok",
                    message="HTTP/SSE MCP server configured",
                    detail=server.url,
                )
            )

    return checks


def _check_safety(config: Config) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []

    checks.append(
        DoctorCheck(
            name="safety.approval",
            status="warn" if config.approval in {ApprovalPolicy.YOLO, ApprovalPolicy.NEVER} else "ok",
            message=f"Approval mode: {config.approval.value}",
            detail="Use on-request for normal interactive work",
        )
    )

    safety_flags = {
        "safety.output_hygiene": config.output_hygiene_enabled,
        "safety.redaction": config.redaction_enabled,
        "safety.prompt_injection": config.prompt_injection_protection_enabled,
    }
    for name, enabled in safety_flags.items():
        checks.append(
            DoctorCheck(
                name=name,
                status="ok" if enabled else "warn",
                message="Enabled" if enabled else "Disabled",
                detail="Recommended for normal use",
            )
        )

    env_path = config.cwd / ".env"
    if env_path.exists():
        checks.extend(_check_env_file(env_path, config.cwd))
    else:
        checks.append(
            DoctorCheck(
                name="safety.env",
                status="ok",
                message="No workspace .env file found",
                detail="Provider keys can also live in the user config directory",
            )
        )

    return checks


def _check_env_file(env_path: Path, cwd: Path) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    checks.append(_file_permission_check("safety.env.permissions", env_path, recommended_private=True))

    if _is_git_tracked(env_path, cwd):
        checks.append(
            DoctorCheck(
                name="safety.env.git",
                status="error",
                message=".env appears to be tracked by git",
                detail="Remove it from git history/index and rotate exposed keys",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                name="safety.env.git",
                status="ok",
                message=".env is not tracked by git",
                detail=str(env_path),
            )
        )

    if _is_git_ignored(env_path, cwd):
        checks.append(
            DoctorCheck(
                name="safety.env.gitignore",
                status="ok",
                message=".env is ignored by git",
                detail=str(env_path),
            )
        )
    else:
        checks.append(
            DoctorCheck(
                name="safety.env.gitignore",
                status="warn",
                message=".env is not ignored by git",
                detail="Add .env to .gitignore to reduce accidental secret commits",
            )
        )

    return checks


def _file_permission_check(name: str, path: Path, recommended_private: bool) -> DoctorCheck:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        return DoctorCheck(
            name=name,
            status="warn",
            message=f"Could not inspect permissions for {path.name}",
            detail=str(exc),
        )

    if recommended_private and mode & (stat.S_IRWXG | stat.S_IRWXO):
        return DoctorCheck(
            name=name,
            status="warn",
            message=f"{path.name} is readable or writable by group/other users",
            detail=f"mode={oct(mode)}; recommended=0o600",
        )

    return DoctorCheck(
        name=name,
        status="ok",
        message=f"{path.name} permissions are private",
        detail=f"mode={oct(mode)}",
    )


def _is_git_tracked(path: Path, cwd: Path) -> bool:
    if not (cwd / ".git").exists():
        return False
    try:
        relative = os.path.relpath(path.resolve(), cwd.resolve())
    except ValueError:
        return False
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _is_git_ignored(path: Path, cwd: Path) -> bool:
    if not (cwd / ".git").exists():
        return False
    try:
        relative = os.path.relpath(path.resolve(), cwd.resolve())
    except ValueError:
        return False
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", relative],
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
