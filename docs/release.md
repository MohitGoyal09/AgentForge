# Release Checklist

This checklist is for publishing AgentForge as the `agentforge-harness` Python package.

## Before Building

- Confirm `README.MD`, `ROADMAP.md`, `CHANGELOG.md`, `SECURITY.md`, and package metadata describe the same release.
- Confirm the changelog has one current release section.
- Confirm `.env`, `.agentforge/config.toml`, local sessions, checkpoints, caches, and test artifacts are not included in the package.
- Run `agentforge doctor` in a fresh or isolated config environment.

## Local Verification

Use an isolated home directory when running tests that touch user-level AgentForge paths:

```bash
HOME=/tmp/agentforge-test-home python3 -m pytest -q
python3 -m compileall -q agentforge_harness tests main.py scripts
python3 scripts/release_smoke.py
```

The smoke script must build fresh artifacts and run `twine check`. Do not publish artifacts from a failed build.

## Build and Inspect

```bash
python3 -m build
python3 -m twine check dist/*
```

Before publishing, inspect the generated archive:

```bash
tar -tzf dist/agentforge_harness-*.tar.gz | sort | less
```

The package should include:

- `agentforge_harness/`
- `README.MD`
- `LICENSE`
- `SECURITY.md`
- `docs/*.md`
- `examples/`

The package should not include:

- `tests/`
- `scripts/`
- `.agentforge/`
- `.env`
- session logs
- checkpoints
- `__pycache__/`

## Publish Flow

Use TestPyPI first when possible:

```bash
python3 -m twine upload --repository testpypi dist/*
```

Then install from TestPyPI in a clean environment and run:

```bash
agentforge --version
agentforge init
agentforge doctor
```

After that, publish to PyPI:

```bash
python3 -m twine upload dist/*
```

## After Publishing

- Create a GitHub release using the changelog notes.
- Verify `pip install agentforge-harness` in a clean environment.
- Run `agentforge init`, `agentforge doctor`, and `agentforge --help`.
- Open a follow-up issue for any known post-v1 work instead of hiding it in the release notes.
