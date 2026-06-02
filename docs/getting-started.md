# Getting Started

AgentForge is a Python CLI package for learning how coding-agent harnesses work. It runs in your terminal, loads configuration from your project and user environment, calls an LLM provider, and exposes local tools through an approval-aware harness.

## Install

From PyPI after release:

```bash
pip install agentforge-harness
```

From a local checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## First Run

Create config with the setup wizard:

```bash
agentforge init
```

Check local readiness:

```bash
agentforge doctor
```

Start the TUI:

```bash
agentforge
```

Or run a single prompt:

```bash
agentforge run "read this project and summarize the harness architecture"
```

## Minimum Provider Setup

AgentForge needs one configured model provider. The setup wizard writes the project config and tells you which API key to set.

For hosted providers such as OpenRouter, OpenAI, and Anthropic, the wizard asks for the provider, API key, and default model. It does not ask for a base URL. OpenRouter gets its default base URL automatically, while OpenAI and Anthropic use their SDK defaults.

For custom OpenAI-compatible providers, the wizard asks for the base URL first, then the API key and model.

Common keys:

```bash
OPENROUTER_API_KEY=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
API_KEY=...
```

See [Provider Setup](providers.md) for provider-specific examples.

## Basic TUI Flow

Inside the interactive session:

```text
/help
/doctor
/tools
/skills
/plan
/build
/stats
/exit
```

Recommended first manual test:

1. Ask AgentForge to list files.
2. Ask it to read `README.MD`.
3. Ask it to create a tiny file and approve the write.
4. Ask it to edit that file.
5. Run `/checkpoint`.
6. Run `/export html`.
7. Run `/stats`.

## Where State Is Stored

Project config lives in:

```text
.agentforge/config.toml
```

Runtime state such as sessions and checkpoints is stored in the platform data directory for `agentforge`. Use `/sessions`, `/resume`, `/checkpoints`, and `/restore` to inspect and reuse it.

## Development Checks

For local development:

```bash
HOME=/tmp/agentforge-test-home python3 -m pytest -q
python3 -m compileall -q agentforge_harness tests main.py scripts
python3 scripts/release_smoke.py
```

Use an isolated `HOME` during tests so session/config writes do not depend on machine-specific user directories.
