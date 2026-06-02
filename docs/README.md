# AgentForge Documentation

This folder contains the focused documentation for AgentForge. The root README is the front door; these pages explain each harness surface in more detail.

## User Docs

- [Getting Started](getting-started.md) - install, initialize, run, and verify AgentForge.
- [CLI Reference](cli.md) - top-level commands and interactive TUI commands.
- [Provider Setup](providers.md) - OpenRouter, OpenAI, Anthropic, and custom providers.
- [Configuration](configuration.md) - config files, environment variables, hooks, MCP, subagents, and safety flags.
- [Skills](skills.md) - progressive skill discovery, matching, activation, and folder layout.
- [Persistence](persistence.md) - sessions, events, checkpoints, reports, and exports.

## Contributor Docs

- [Architecture](architecture.md) - system shape, runtime flow, and core modules.
- [Extending AgentForge](extensions.md) - custom tools, skills, hooks, and subagents.
- [Tool Reliability Standard](tool-reliability.md) - the v1 quality bar for tool schemas and observations.
- [Security Model](../SECURITY.md) - what AgentForge protects and what still needs sandboxing.
- [Release Checklist](release.md) - local verification, build inspection, TestPyPI, and PyPI.
- [Manual Pre-Release Test](manual-testing.md) - fresh-user smoke test before publishing.

## Examples

- [Examples Index](../examples/README.md)
- [Custom Tool Example](../examples/custom_tool.py)
- [Skill Example](../examples/skills/api-interface-design/SKILL.md)
- [Hook Example](../examples/hooks/log_tool_call.py)
- [Subagent Example](../examples/subagents/code-review.toml)
