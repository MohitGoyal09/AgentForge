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
from rich.table import Table
from rich.text import Text

from agentforge_harness.config.config import ApprovalPolicy, Config
from agentforge_harness.config.loader import get_data_dir, get_global_skills_dir, get_user_skills_dir


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

    table = Table(
        show_header=True,
        header_style="highlight",
        expand=True,
    )
    table.add_column("Status", no_wrap=True)
    table.add_column("Check", style="code", no_wrap=True)
    table.add_column("Message", overflow="fold")
    table.add_column("Detail", style="muted", overflow="fold")

    for check in report.checks:
        marker, style = _status_marker(check.status)
        table.add_row(
            Text(marker, style=style),
            check.name,
            check.message,
            check.detail,
        )

    title = "Doctor"
    border_style = "error" if report.has_errors else "warning" if report.has_warnings else "success"
    console.print(
        Panel(
            table,
            title=Text(title, style=border_style),
            title_align="left",
            border_style=border_style,
            padding=(1, 2),
        )
    )


def _status_marker(status: str) -> tuple[str, str]:
    if status == "ok":
        return "OK", "success"
    if status == "warn":
        return "WARN", "warning"
    return "ERROR", "error"


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
    try:
        mode = stat.S_IMODE(env_path.stat().st_mode)
    except OSError as exc:
        return [
            DoctorCheck(
                name="safety.env",
                status="warn",
                message="Could not inspect workspace .env",
                detail=str(exc),
            )
        ]

    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        checks.append(
            DoctorCheck(
                name="safety.env.permissions",
                status="warn",
                message=".env is readable or writable by group/other users",
                detail=f"mode={oct(mode)}; recommended=0o600",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                name="safety.env.permissions",
                status="ok",
                message=".env permissions are private",
                detail=f"mode={oct(mode)}",
            )
        )

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

    return checks


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


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
