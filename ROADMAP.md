# AgentForge Roadmap

AgentForge is an open-source Python package for learning and experimenting with AI coding-agent harness engineering. This roadmap is intentionally release-oriented: it explains where the project is today, what must happen before v1, and which ideas are planned for later.

The project is still alpha. The goal for v1 is not to clone every commercial coding agent feature. The goal is a small, understandable, reliable harness that demonstrates the core systems clearly enough for developers to study, extend, and trust.

## Current Status

AgentForge already includes the main pieces of a coding-agent harness:

| Area | Status |
| --- | --- |
| Agent loop | ReAct-style async loop with streamed events |
| Model providers | OpenRouter, OpenAI, Anthropic, and custom OpenAI-compatible endpoints |
| Tools | File tools, shell, search/fetch, todos, memory, patch, and subagents |
| Safety | Approval policies, path checks, shell safety rules, mutating-tool prompts, secret/param redaction, and untrusted tool-observation wrapping |
| Context | Token estimation, pruning, compression, and loop detection |
| Skills | Progressive SKILL.md discovery and activation |
| Modes | Plan and build modes with tool restrictions |
| Persistence | Sessions, checkpoints, event logs, resume, and markdown export |
| TUI | Rich terminal UI with tool call rendering and status panels |
| Packaging | `agentforge-harness` package with `agentforge` CLI |

## Release Goals

### v0.2.x - Alpha Stabilization

Focus: make the current harness easier to install, configure, debug, and contribute to.

- Keep package metadata, README, changelog, and roadmap current.
- Harden setup and config validation across supported providers.
- Improve tool observations so every failure gives the model a useful retry path.
- Add missing tests around safety, patching, setup, and provider adapters.
- Reduce obvious TUI rendering issues and make command output easier to scan.
- Document extension points for tools, skills, hooks, and subagents.

### v0.3.x - Measurement and Safety

Focus: make harness changes measurable instead of vibe-based.

- Add a lightweight eval runner with mock and real-model modes.
- Add regression scenarios for file edits, shell use, patching, skills, and plan/build mode.
- Expand prompt-injection scenarios for shell output, web content, MCP responses, and multi-turn follow-up actions.
- Track token usage and estimated cost per turn/session.
- Save eval reports as artifacts that can be compared across runs.

### v0.4.x - Daily Driver Tools

Focus: make the tool useful for real coding workflows while keeping it inspectable.

- Add structured git tools for diff, status, commit preparation, and PR summaries.
- Add browser automation for local web QA and visual verification.
- Add HTML session export with collapsible tool calls.
- Add `/review` to summarize changes made during a session.
- Improve patch ergonomics with parent-directory creation, stronger path-security tests, and optional formatting hooks.

### v0.5.x - Orchestration

Focus: explore multi-agent coordination carefully, starting with low-risk workflows.

- Add read-only swarm investigation mode.
- Add structured subagent result objects instead of plain text only.
- Add file/path scoping for child agents.
- Add per-child timeouts, cancellation, and result aggregation.
- Defer write-capable swarm mode until worktree isolation and merge safety are solid.

### v1.0 - Stable Learning Harness

Focus: a stable public release that users can install, understand, and extend.

v1 should include:

- Reliable `pip install agentforge-harness` flow.
- Clear `agentforge init` onboarding for all supported providers.
- Stable config format with migration notes for breaking changes.
- Documented tool, skill, hook, and subagent extension APIs.
- Good default safety posture for shell, file writes, patches, and MCP servers.
- Reproducible test and eval commands.
- Security notes that are honest about what is protected and what is not.
- Enough examples for a new contributor to build one tool, one skill, and one subagent.

## Pre-v1 Quick Wins

These are small, high-leverage improvements pulled from the older internal PRD-style notes. They are good candidates before v1 because they improve trust, packaging quality, or day-to-day usability without requiring a large new architecture.

| Priority | Status | Quick win | Why it matters |
| --- | --- | --- | --- |
| P0 | Done | Add a smoke test for `agentforge init` output | Prevents broken first-run config files. |
| P0 | Done | Add provider adapter tests for OpenAI-compatible and Anthropic tool calls | Keeps multi-provider support from silently regressing. |
| P0 | Done | Add secret redaction for tool outputs | Stops obvious key leaks from entering model context or logs. |
| P0 | Done | Add prompt-injection fixture tests and untrusted tool-observation wrapping | Tests the most important safety boundary for coding agents. |
| P0 | Done | Add approval prompt and tool-param redaction | Keeps secrets out of approval previews, TUI argument panels, and hook params. |
| P1 | Open | Add `/cost` using token usage already collected | Turns existing telemetry into useful feedback. |
| P1 | Done | Add structured `git_diff` read-only tool | Safer and more useful than asking the model to parse raw shell output. |
| P1 | Done | Improve patch tests around symlinks, parent dirs, and no-newline files | Patch is powerful, so confidence here matters. |
| P1 | Open | Add `--json` output for `/stats` or a new report command | Helps automation and future eval tooling. |
| P1 | Done | Add a minimal `CONTRIBUTING.md` | Makes the project feel like an open-source package, not a private experiment. |
| P1 | Done | Add issue templates for bug reports and feature requests | Makes outside feedback easier to act on. |
| P2 | Open | Add HTML session export | Useful, but not required for the core harness. |
| P2 | Open | Add browser tool for local QA | Valuable, but it brings dependency and sandboxing complexity. |

Recommended order before v1:

1. `/cost` command from existing token usage.
2. Add central output cleanup for control characters and large outputs.
3. Add automation-friendly JSON reporting.
4. Consider HTML session export once the core safety work is stronger.

## Security Roadmap

Security work should land in layers. AgentForge should be honest about its protections instead of pretending the harness is sandboxed when it is not.

| Layer | Planned work |
| --- | --- |
| Output hygiene | Secret and param redaction are in place; strip control characters and cap large outputs consistently |
| Prompt injection | Basic untrusted wrapping is in place; add origin tracking for high-risk follow-up actions |
| Shell safety | Expand obfuscation detection and add stricter allowlist mode |
| Config safety | Warn on risky config/env file permissions and committed `.env` files |
| MCP safety | Document that MCP servers are trusted code until sandboxing exists |
| Sandboxing | Explore OS-level isolation after the core harness stabilizes |

## Eval Roadmap

The eval system should start small and local.

Initial eval scenarios:

- Write one file and verify contents.
- Read a file and answer a question.
- Edit multiple files.
- Use `apply_patch` successfully.
- Avoid a dangerous shell command.
- Use a named skill only when relevant.
- Stay in plan mode without mutating files.
- Recover from a tool error.
- Ignore prompt injection inside a file.

Initial metrics:

- Pass/fail assertions.
- Turns per task.
- Tool errors per task.
- Token usage per task.
- Cost estimate per task.

Later eval work can add LLM-as-judge scoring, model comparisons, and baseline diffing.

## Multi-Agent Roadmap

Subagents and swarm mode should stay separate concepts:

- Subagents are specialist calls: one bounded task, one result, parent remains in control.
- Swarm mode is orchestration: multiple child agents, parallel work, aggregation, and eventually conflict handling.

Planned order:

1. Improve built-in subagents and structured result output.
2. Add read-only swarm investigation.
3. Add scoped child-agent workspaces.
4. Add worktree-based write isolation.
5. Add merge/conflict handling only after read-only swarm is reliable.

## Not Planned for v1

These are useful ideas, but they should not block v1:

- Write-capable swarm mode.
- Full browser automation.
- OS-level sandboxing.
- LLM judge evals.
- Hosted service or cloud sync.
- Plugin marketplace.
- Multi-user collaboration.
- Enterprise policy management.

## Contribution Areas

Good first contribution areas:

- Tests for existing tools.
- Documentation examples.
- Small built-in skills.
- TUI rendering fixes.
- Safer tool output formatting.
- Config validation improvements.

Larger contribution areas:

- Eval runner.
- Secret scanning.
- Structured git tools.
- Browser tool.
- Read-only swarm mode.
- Sandboxing research.
