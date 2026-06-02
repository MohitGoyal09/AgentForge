from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    default_env = os.environ.copy()
    isolated_env = os.environ.copy()
    isolated_env["HOME"] = str(Path(tempfile.gettempdir()) / "agentforge-release-smoke-home")
    dist_dir = ROOT / "dist"

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

    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    build_result = _run([sys.executable, "-m", "build"], default_env, capture=True)
    dist_files = sorted(str(path) for path in (ROOT / "dist").glob("*"))
    if build_result != 0:
        print("Fresh package build failed. Refusing to validate stale dist artifacts.", file=sys.stderr)
        return build_result

    if not dist_files:
        print("No dist artifacts found after build", file=sys.stderr)
        return 1

    twine_result = _run([sys.executable, "-m", "twine", "check", *dist_files], default_env)
    if twine_result != 0:
        return twine_result

    return _smoke_console_script(dist_files, default_env)


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


def _smoke_console_script(dist_files: list[str], env: dict[str, str]) -> int:
    wheel = next((Path(path) for path in dist_files if path.endswith(".whl")), None)
    if not wheel:
        print("No wheel artifact found for console-script smoke", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="agentforge-wheel-smoke-") as tmpdir:
        venv_dir = Path(tmpdir) / "venv"
        result = _run([sys.executable, "-m", "venv", str(venv_dir)], env)
        if result != 0:
            return result

        python_bin = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        result = _run(
            [str(python_bin), "-m", "pip", "install", "--no-deps", "--force-reinstall", str(wheel)],
            env,
        )
        if result != 0:
            return result

        script_path = venv_dir / ("Scripts/agentforge.exe" if os.name == "nt" else "bin/agentforge")
        if os.name == "nt":
            return _run([str(script_path), "--version"], env)

        script = script_path.read_text(encoding="utf-8")
        expected = "from agentforge_harness.cli.run import cli"
        if expected not in script:
            print("agentforge console script has the wrong entry point", file=sys.stderr)
            print(script, file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
