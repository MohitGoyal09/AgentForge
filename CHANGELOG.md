# Changelog

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
- Shell completion generation (agentforge completion <shell>)
- Config validation for model names, paths, MCP servers, hooks
- Rich terminal UI with tool output visualization
- Pip-installable package metadata (`agentforge-harness` distribution with `agentforge` CLI)
