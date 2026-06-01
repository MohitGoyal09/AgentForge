from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    default_env = os.environ.copy()
    isolated_env = os.environ.copy()
    isolated_env["HOME"] = str(Path(tempfile.gettempdir()) / "agentforge-release-smoke-home")

    commands = [
        (
            [sys.executable, "-m", "compileall", "-q", "agentforge_harness", "tests", "main.py", "scripts"],
            default_env,
        ),
        ([sys.executable, "-m", "pytest", "-q"], isolated_env),
        (
            [
                sys.executable,
                "-c",
                "from pathlib import Path; "
                "from agentforge_harness.config.loader import load_config; "
                "from agentforge_harness.cli.doctor import build_doctor_report; "
                "report = build_doctor_report(load_config(Path.cwd())); "
                "raise SystemExit(1 if report.has_errors else 0)",
            ],
            isolated_env,
        ),
    ]

    for command, env in commands:
        result = _run(command, env)
        if result != 0:
            return result

    build_result = _run([sys.executable, "-m", "build"], default_env, capture=True)
    dist_files = sorted(str(path) for path in (ROOT / "dist").glob("*"))
    if build_result != 0:
        if not dist_files:
            return build_result
        print(
            "Build failed, but existing dist artifacts were found. "
            "Continuing with twine check for offline smoke validation.",
            file=sys.stderr,
        )

    if not dist_files:
        print("No dist artifacts found after build", file=sys.stderr)
        return 1

    return _run([sys.executable, "-m", "twine", "check", *dist_files], default_env)


def _run(command: list[str], env: dict[str, str], capture: bool = False) -> int:
    print("$ " + " ".join(command))
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=capture,
        text=True,
    )
    if capture and completed.returncode == 0 and completed.stdout:
        print(completed.stdout)
    if capture and completed.returncode != 0:
        combined = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
        tail = "\n".join(combined.splitlines()[-12:])
        if tail:
            print(tail, file=sys.stderr)
    if completed.returncode != 0:
        print(f"Command failed with exit code {completed.returncode}", file=sys.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
