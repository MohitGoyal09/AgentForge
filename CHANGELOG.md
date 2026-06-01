# Changelog

## Unreleased

### Added

- Multi-provider model configuration for OpenRouter, OpenAI, Anthropic, and custom OpenAI-compatible endpoints.
- Anthropic client adapter with message and tool-call conversion.
- Setup wizard prompts for provider, model, and base URL.
- Provider and setup tests covering config resolution, Anthropic conversion, and generated TOML shape.
- Read-only `git_diff` tool for structured repository diff inspection.
- `CONTRIBUTING.md` and GitHub issue templates for open-source contributors.
- Patch tool intent metadata, parent-directory policy, deletion fallback handling, and edge-case tests.
- Centralized secret redaction for tool results before they reach model context, hooks, TUI events, persistence, or exports.
- Approval confirmation, TUI argument, and hook parameter redaction for tool inputs.
- Prompt-injection boundary handling that marks tool observations as untrusted data and wraps model-visible tool output.

### Changed

- Roadmap rewritten as an open-source release roadmap with pre-v1 quick wins and v1 release criteria.
- Package metadata now points to the Agentforge GitHub repository.

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
