# Changelog

## 1.0.0 (planned)

### Added

- Multi-provider model configuration for OpenRouter, OpenAI, Anthropic, and custom OpenAI-compatible endpoints.
- Anthropic client adapter with message and tool-call conversion.
- Setup wizard prompts for provider, model, and base URL.
- Setup wizard overwrite protection, provider-specific hints, and optional local doctor check.
- Provider and setup tests covering config resolution, Anthropic conversion, and generated TOML shape.
- Provider setup docs, security model docs, release smoke script, and runnable examples index.
- Read-only `git_diff` tool for structured repository diff inspection.
- `agentforge doctor` and `/doctor` health checks with optional JSON output.
- `agentforge report` command and `/report --json` for saved-session reporting without model calls.
- HTML session export with `/export html`.
- Extension docs and examples for custom tools, skills, hooks, and subagents.
- `CONTRIBUTING.md` and GitHub issue templates for open-source contributors.
- Patch tool intent metadata, parent-directory policy, deletion fallback handling, and edge-case tests.
- Central output hygiene for tool results, including ANSI/control-character stripping and model-visible field caps.
- Centralized secret redaction for tool results before they reach model context, hooks, TUI events, persistence, or exports.
- Approval confirmation, TUI argument, and hook parameter redaction for tool inputs.
- Prompt-injection boundary handling that marks tool observations as untrusted data and wraps model-visible tool output.

### Changed

- Roadmap rewritten as an open-source release roadmap with v1 release criteria and post-v1 feature sequencing.
- Roadmap polished into a release and feature-sequencing document without internal priority tables.
- Package metadata now points to the Agentforge GitHub repository.
- Setup now writes config and env files with private permissions and nudges users toward `agentforge doctor`.
- HTML session export now includes summary cards, usage table, dark-mode styles, and collapsible transcript entries.
- Tool errors now get a default recovery contract when a specific tool does not provide one.
- Doctor now reports config permissions, `.env` permissions, tracked `.env` files, missing `.env` ignore rules, and out-of-workspace executable paths more explicitly.
- Release smoke now removes old `dist/` artifacts and requires a fresh package build before `twine check`.

## 0.1.0 (2026-05-30)

### Added

- Agent harness with ReAct loop and tool execution
- 13 built-in tools: read, write, edit, shell, grep, glob, list_dir, web_search, web_fetch, todos, memory, patch
- Subagent system: explore, debugger, codebase_investigator, code_reviewer, test_planner, architect
- MCP server integration with dynamic tool registration
- Skill system: file-based SKILL.md discovery, matching, and activation
- Plan and Build modes (/plan, /build) with mode-aware tool filtering and system prompts
- Session persistence with snapshots, checkpoints, and crash recovery
- Context management with token-aware pruning and LLM-based compression
- Loop detection with automatic breaker prompts
- Approval system with configurable policies (on-request, auto, yolo, never, etc.)
- Hook system for lifecycle automation
- CLI with interactive and single-prompt modes
- Setup wizard (agentforge init)
- Shell completion generation (agentforge completion)
- Config validation for model names, paths, MCP servers, hooks
- Rich terminal UI with tool output visualization
- Pip-installable package metadata (`agentforge-harness` distribution with `agentforge` CLI)
