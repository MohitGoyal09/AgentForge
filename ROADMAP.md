# AgentForge Roadmap

AgentForge is an open-source Python package for learning AI coding-agent harness engineering by building the harness directly. The roadmap is intentionally release-oriented: it separates what must be stable for v1 from the larger research features that should come later.

The goal for v1 is not to clone every commercial coding agent. The goal is a compact, inspectable, installable harness that teaches the important systems clearly: model loops, tool calls, observations, approvals, context, skills, persistence, and recovery.

## Where AgentForge Is Today

AgentForge already has the foundation of a real coding-agent harness:

- A streamed ReAct-style agent loop with typed tool calls.
- Provider support for OpenRouter, OpenAI, Anthropic, and custom OpenAI-compatible endpoints.
- Built-in tools for file IO, search, shell, web fetch/search, memory, todos, patching, git diff, and subagents.
- Approval policies, path checks, shell safety checks, output hygiene, redaction, and prompt-injection boundaries around untrusted observations.
- Context management with token estimation, pruning, compaction, and loop detection.
- Progressive `SKILL.md` discovery and activation.
- Plan/build modes with mode-aware tool filtering.
- Sessions, checkpoints, event logs, resume/restore, markdown export, HTML export, and JSON reports.
- A Rich terminal UI that shows model output, tool calls, approvals, skills, and status panels.
- Package metadata for the `agentforge-harness` distribution and `agentforge` CLI.

## v1.0: Stable Learning Harness

v1 should be the first release that feels good to install, run, inspect, and extend. It should be stable enough for people learning harness engineering to trust the examples and copy the patterns.

Before v1, focus on four areas.

### 1. Roadmap and Docs Polish

The docs should explain the project as an open-source package, not as a private experiment.

- Keep the README focused on what AgentForge is, how to install it, how the architecture works, and where to go next.
- Keep this roadmap focused on release direction and feature sequencing.
- Keep provider setup, extension examples, security notes, and release steps in separate docs.
- Make sure README, changelog, roadmap, package metadata, and examples agree with each other.

### 2. Tool Reliability

Tools are the harness action space. For v1, every built-in tool should be predictable enough that the model can recover from ordinary failures.

The v1 reliability bar:

- Tool schemas are explicit and narrow.
- Tool outputs include a summary when useful.
- Tool failures include a recovery hint and safe next action.
- Mutating tools expose affected paths and diffs before approval when practical.
- Observations are cleaned, capped, redacted, and marked as untrusted when needed.
- Patch and edit tools handle common edge cases such as no trailing newline, missing parent directories, stale context, and path safety.

Good near-term work:

- Audit every built-in tool for consistent `summary`, `artifacts`, `next_actions`, and `recovery_hint` behavior.
- Add focused tests for confusing failure modes, especially patch, edit, shell, and file writes.
- Keep `git_diff` read-only and use it as the preferred way to inspect repository changes.
- Improve TUI rendering for long tool output, truncated observations, and failed tool calls.

### 3. Release Hygiene

v1 should be publishable without guesswork.

The release path should include:

- `agentforge init` works in a fresh directory.
- `agentforge doctor` catches common config, provider, skill, MCP, and local trust problems.
- `python3 -m pytest -q` passes with an isolated writable home directory.
- `python3 -m compileall -q agentforge_harness tests main.py scripts` passes.
- `python3 scripts/release_smoke.py` runs tests, doctor checks, a fresh package build, and `twine check`.
- The built distribution contains docs and examples, but does not include tests, local config, caches, secrets, or development-only scripts.
- The changelog has a single v1 section that names the important user-facing changes.

### 4. Safety Baseline

AgentForge should be honest about what it protects and what it does not protect.

The v1 safety baseline:

- Approval modes are documented and easy to understand.
- Mutating tools ask for confirmation under the right policies.
- Secrets are redacted from tool outputs, approval previews, hook params, TUI panels, persistence, and exports.
- Tool observations are treated as data, not instructions.
- Doctor warnings flag risky config permissions, committed `.env` files, unsafe MCP paths, and missing provider keys.
- The docs clearly say that MCP servers, shell commands, and local tools are trusted code unless an external sandbox is added.

## After v1: Feature Roadmap

These features are important, but they should not block the first stable learning release.

### v1.1: Skills v2

Skills are one of the clearest ways to teach progressive disclosure. v1.1 should make them more precise, more explainable, and easier to share.

Planned work:

- Better skill ranking without hardcoded task rules.
- Aliases, categories, and display names.
- `agentforge skills validate` for checking frontmatter, paths, and oversized bodies.
- Token budgets per skill and clearer truncation behavior.
- TUI explanations for why a skill matched and what content was loaded.
- Lazy loading for skill references, assets, and scripts.
- Skill install/list/update flows for local and global skill roots.

### v1.2: Replay and Trace Debugging

Replay is the bridge between "the agent did something" and "I can understand why it happened."

Planned work:

- Deterministic replay from event logs without model calls.
- Trace inspection for model messages, tool calls, approvals, and observations.
- Regression comparison between two runs.
- Better session reports for debugging failed tasks.

### v1.3: Local Evals

Evals should come after replay, because replay gives the project a clean source of truth for what happened.

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
- Estimated cost per task.

Later eval work can add LLM-as-judge scoring, model comparisons, and baseline diffing.

### v1.4: Browser-Assisted Local QA

Browser QA makes AgentForge more useful for frontend work while teaching a major harness pattern: observing the environment, not only files.

Planned work:

- Open localhost targets.
- Capture screenshots.
- Read console errors and network failures.
- Produce a small QA report.
- Keep browser tools optional so the base package stays lightweight.

### v1.5: Read-Only Swarm

Subagents and swarm mode should stay separate concepts.

- Subagents are specialist tool calls: one bounded task, one result, parent remains in control.
- Swarm mode is orchestration: multiple child agents, shared task state, aggregation, budgets, and eventually conflict handling.

Read-only swarm should come first:

- Investigation swarm for codebase exploration.
- Role-specific child agents such as explorer, reviewer, debugger, and test planner.
- Per-child timeout and budget controls.
- Structured result aggregation.
- No file writes until isolation and merge safety exist.

### v2.0: Isolated Write-Capable Orchestration

Write-capable swarm mode should be treated as a bigger release because it needs real isolation.

Prerequisites:

- Workspace rollback for checkpoints.
- Worktree-based child-agent isolation.
- File ownership and conflict detection.
- Merge planning and review.
- Cancellation and cleanup for child agents.
- Stronger replay/debug support for multi-agent runs.

## Later Ideas

These are useful, but they should stay behind the core learning path:

- Cost tracking and `/cost`.
- Structured git status, commit preparation, and PR summary tools.
- Secret scanning for workspace files.
- OS-level sandboxing research.
- Plugin marketplace.
- Hosted sync or multi-user collaboration.
- Enterprise policy management.

## Contribution Areas

Good first contributions:

- Tests for existing tools.
- Documentation examples.
- Small built-in skills.
- TUI rendering fixes.
- Safer tool output formatting.
- Config validation improvements.

Larger contributions:

- Skills v2.
- Deterministic replay.
- Local eval runner.
- Browser QA tool.
- Read-only swarm mode.
- Sandboxing research.
