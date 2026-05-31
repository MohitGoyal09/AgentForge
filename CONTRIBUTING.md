# Contributing to AgentForge

Thanks for helping improve AgentForge. This project is a learning-focused AI coding-agent harness, so contributions should prefer clarity, testability, and inspectable behavior over clever abstractions.

## Development Setup

```bash
git clone https://github.com/MohitGoyal09/Agentforge.git
cd Agentforge
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
agentforge --version
```

## Before Opening a PR

Run the core checks:

```bash
python3 -m compileall -q agentforge_harness tests main.py scripts
HOME=/tmp/agentforge-test-home .venv/bin/python -m pytest -q
```

For packaging changes, also run:

```bash
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```

## Contribution Guidelines

- Keep changes focused. One feature or fix per PR is easiest to review.
- Match existing code style before introducing a new abstraction.
- Add tests for behavior changes, especially tools, config, approvals, skills, and persistence.
- For tool changes, return useful `summary`, `next_actions`, `artifacts`, and `recovery_hint` fields.
- For safety-sensitive changes, include both success and failure tests.
- Update `README.MD`, `ROADMAP.md`, or `CHANGELOG.md` when user-facing behavior changes.

## Good First Contributions

- Add tests around existing tools.
- Improve docs and examples.
- Add small built-in skills.
- Improve TUI rendering for edge cases.
- Improve recovery hints in tool errors.
- Add config validation tests.

## Design Principles

AgentForge should stay:

- Understandable: a learner should be able to follow the harness flow.
- Inspectable: state, tool calls, approvals, and errors should be visible.
- Safe by default: mutating operations should be explicit and reviewable.
- Provider-aware: OpenRouter, OpenAI, Anthropic, and custom endpoints should not rely on hidden assumptions.
- Extensible: tools, skills, hooks, and subagents should be easy to add without touching the core loop.

## Reporting Security Issues

Please do not open public issues for secrets, sandbox escapes, prompt-injection bypasses that exfiltrate private data, or other sensitive vulnerabilities. Open a minimal public issue asking for a private contact path, or contact the maintainer directly if you already have one.
