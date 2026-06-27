# AgentForge Improvement Plan & Status

> **Pickup doc for a fresh session.** Read this top-to-bottom and you have full context:
> what's done, how the code is structured now, how we work, and exactly what's left with specs.
> A reference harness exists locally at `/Users/mohit/Code/tau` (a Pi-style coding agent) used for
> design comparison. **Do NOT name that reference project in PR/commit text** — describe patterns
> generically. It's fine to consult it while implementing.

---

## 1. Current status (as of PR #10 merged)

`master` is green: **489 tests pass** (`/.venv/bin/python -m pytest -q`).

| Phase / item | Status | PR |
|---|---|---|
| **Phase 0** — correctness & safety bug fixes (6) | ✅ merged | #1 |
| **Phase 1** — provider abstraction, circular-import break, typed events, parallel reads, transcript repair | ✅ merged | #2 |
| **P2.2** — thinking/reasoning controls | ✅ merged | #3 |
| **P2.3a** — session introspection accessors + cooperative cancellation | ✅ merged | #3 |
| `set_thinking_level` regression hotfix | ✅ merged | #5 |
| **Audit bug fixes A–J** (thinking-delta regression, MCP, path traversal, approval bypass, SSRF, …) | ✅ merged | #6 |
| **P2.1** — append-only session tree: foundation | ✅ merged | #4 |
| **P2.1** — session tree live integration + audit fixes | ✅ merged | #7 |
| **P2.1 layer 4** — branching API (`tree_choices`/`branch_to_entry`) | ✅ merged | #8 |
| **P2.3b** — command registry (`handle_command → CommandResult`) | ✅ merged | #8 |
| **P2.3c** — re-entrant steering / follow-up queue (`session.prompt(steer/follow_up)`) | ✅ merged | #9 |
| **P2.4** — secondary hardening + remaining LOW bugs | ✅ merged | #10 |
| **Phase 3** — Textual TUI replacement | ⬜ pending | — |

**Recommended next step:** Phase 3 — Textual TUI replacement (all blockers resolved).

---

## 2. How we work here (conventions — follow these)

- **One PR per logical unit.** Branch from `master` (`feat/...` or `fix/...`), implement, test, PR, merge, sync. Never commit straight to `master`.
- **Sonnet subagents implement; the main session reviews.** Dispatch `general-purpose` subagents with `model: sonnet` and precise specs. **Run implementation subagents sequentially**, not in parallel, when they touch overlapping files (parallel edits on the same working tree corrupt each other). Read-only audit subagents may run in parallel.
- **A subagent saying "done, tests pass" is NOT done.** Always: (a) confirm the changes are actually in the working tree/branch (subagents sometimes run in an isolated git worktree under `.claude/worktrees/` and leave changes there — copy them in and re-run the suite in the main tree), (b) review the diff yourself, (c) **independently re-verify any CRITICAL finding/fix** before trusting it, (d) check that any modified existing tests reflect *corrected* behavior, not tests bent to pass a bug.
- **Test the seam, not just the parts.** Two shipped bugs (`set_thinking_level` crash; broken compaction-restore) both lived in an end-to-end path that unit tests never crossed. For any roundtrip (save/load, encode/decode, mirror/reconstruct) write a test that exercises the **full roundtrip with the hard case in the middle** and asserts an invariant like `restored == live`.
- **Reviewing a refactor = diff for deletions too.** A subagent rewriting a file can silently drop methods/branches (this happened twice). Grep that prior additions still exist.
- **PR/commit text:** conventional-commit style; never name the reference project; PR bodies end with the Claude Code generated-with line.
- **Run the full suite before every commit**; keep `master` green at all times.

---

## 3. Architecture as it exists now (navigation map)

```
agentforge_harness/
├── client/
│   ├── providers/            # P1.1 — provider Strategy pattern
│   │   ├── base.py           #   BaseProvider ABC (shared retry loop, catch-all → ERROR event)
│   │   ├── openai_compatible.py  #   OpenAI / OpenRouter / custom; reasoning_effort
│   │   ├── anthropic.py      #   native streaming; extended-thinking budget; thinking_delta
│   │   ├── fake.py           #   FakeProvider for deterministic tests
│   │   └── __init__.py       #   PROVIDER_REGISTRY + create_provider(config)
│   ├── llm_client.py         #   thin facade delegating to the resolved provider
│   ├── response.py           #   StreamEvent (provider layer): TEXT_DELTA, THINKING_DELTA, TOOL_*, MESSAGE_COMPLETE, ERROR
│   └── thinking.py           # P2.2 — ThinkingLevel enum + per-provider mappings
├── agent/
│   ├── agent.py              #   the agentic loop: streaming, retry/circuit/fallback, PARALLEL read-only tools,
│   │                         #   cancellation checkpoints, compaction trigger, loop detection, event emit+record
│   ├── events.py             # P1.3 — typed AgentEvent variants (frozen dataclasses) w/ .type + computed .data;
│   │                         #   factories return the subclasses (backward compatible)
│   ├── session.py            #   composition root: owns client/registry/context/approval/skills/mcp/persistence/
│   │                         #   tree_store; accessors; cancel; set_thinking_level/set_mode/set_provider; snapshot
│   ├── subagent_runner.py    # P1.2 — run_subagent() injected so tools never import Agent (breaks the cycle)
│   ├── persistence.py        #   flat SessionSnapshot JSON + checkpoints + events JSONL (PersistenceManager)
│   ├── session_tree.py       # P2.1 — SessionEntry DAG + path_to_entry / active_leaf_id / reconstruct_messages (pure)
│   ├── session_store.py      # P2.1 — SessionTreeStore (append-only JSONL, write_all) + migrate_snapshot_to_entries
│   └── modes.py              #   AgentMode {PLAN, BUILD}
├── context/
│   ├── manager.py            #   ContextManager: messages + token budget tiers + compaction + prune +
│   │                         #   repair_dangling_tool_calls + the append-only entry mirror (_entries)
│   ├── compaction.py         #   ChatCompactor (LLM summary; logs failures)
│   └── loop_detector.py
├── tools/
│   ├── base.py               #   Tool ABC, ToolResult, ToolKind {READ,WRITE,SHELL,NETWORK,MEMORY,MCP}, ToolConfirmation
│   ├── registry.py           #   invoke(): validate → hooks → approval → execute → hygiene/redaction/injection
│   ├── discovery.py          #   dynamic custom-tool loading (raises+logs on failure; abs-path module names)
│   ├── subagents.py          #   SubagentTool (injected runner; wait_for timeout)
│   ├── builtin/              #   read/write/edit/append/patch/shell/glob/grep/list_dir/git_diff/web_*/memory/todo
│   └── mcp/                  #   MCPManager + MCPClient + MCPTool (kind=MCP; reads CallToolResult correctly)
├── safety/                   #   approval.py (policy matrix; async request_confirmation), circuit_breaker,
│                             #   output_hygiene, prompt_injection
├── skills/manager.py
├── hooks/hook_system.py
├── ui/tui.py                 #   current Rich print-renderer (to be replaced in Phase 3)
└── cli/                      #   commands.py (slash-command dispatch), run.py, setup.py, doctor.py, models.py, report.py
```

### Key concepts a new session must know
- **Two-layer events.** Providers emit `StreamEvent` (`client/response.py`); the agent loop converts them to typed `AgentEvent`s (`agent/events.py`). `AgentEvent` keeps `.type`/`.data` for backward compat while being `isinstance`-dispatchable — this is what the Phase 3 TUI will consume.
- **Session history tree (P2.1).** `ContextManager` keeps the live flat `_messages` AND mirrors every add into an append-only `_entries` log (`SessionEntry` nodes). Compaction is **non-destructive**: it records a `CompactionEntry` (originals stay in the log) and reconstruction applies it on read. `Session` persists the log via `SessionTreeStore` and reconstructs on restore (falling back to / migrating the flat snapshot when no tree exists). Invariant under test: a save→restore (incl. after compaction) yields the same messages as the live session.
- **Provider abstraction (P1.1).** Add a provider by adding a `BaseProvider` subclass + a `PROVIDER_REGISTRY` entry — no central `if` to edit.
- **Approval (P0/P1/audit).** `check_approval` is policy-driven; `request_confirmation` is **async** (await it); path checks use `.resolve()`; MCP tools are `kind=MCP` (excluded from plan mode).

---

## 4. Completed work — one-line summaries

**Phase 0 (#1):** approval-bypass on empty `affected_paths`; duplicate `shutdown()`; OpenAI path dropped temperature/max_tokens; silent compaction failure; useless `critical` budget tier; `parse_tool_call_arguments` hardening; doctor test isolation.

**Phase 1 (#2):** provider `BaseProvider` abstraction + real Anthropic streaming + `FakeProvider`; broke `agent→tools→agent` circular import via injected runner; typed two-layer event model + agent-side event recording + diagnostic events; parallel execution for read-only tool batches; transcript repair before provider requests.

**P2.2 + P2.3a (#3, hotfix #5):** thinking/reasoning controls (Anthropic budget + OpenAI reasoning_effort + thinking_delta stream); session introspection accessors + cooperative cancellation.

**Audit fixes A–J (#6):** restored dropped THINKING_DELTA handler; MCP `CallToolResult` extraction; path-traversal resolve; async approval-callback bypass; discovery raise+log+namespacing; subagent `wait_for` timeout; MCP `kind=MCP`; `web_fetch` SSRF guard; no partial-text re-stream on retry; provider catch-all + balanced message frame on crash.

**P2.1 (#4, #7):** append-only `SessionEntry` tree (model + pure reconstruction) and JSONL store + migration; live integration with faithful non-destructive compaction on restore, `/new` reset, flat-restore seeding, dangling-leaf graceful fallback.

**P2.3b (#8):** `CommandRegistry` replaces the CLI's `if name == "/x"` chain; every handler returns a typed `CommandResult`; CLI becomes a thin render layer. 21 unit tests.

**P2.3c (#9):** `SteeringQueue` (two-lane FIFO deque); `Session.prompt(text, mode)` enqueues messages; agent loop drains the steer lane at every tool-batch boundary and the follow-up lane at turn-end; `/steer` and `/follow-up` CLI commands; `asyncio.to_thread` wraps blocking `console.input()`; `CancelledError` re-raised (never swallowed). User-created tools can import `agentforge_harness.*` (sys.path fix in discovery). Tests: `test_steering_queue.py`, `test_session_prompt.py`.

**P2.4 (#10):** `MCPClient.reconnect()` with exponential backoff + stale-tool-state clear; `SkillManager.get_active_allowed_tools()` union enforcement wired into `Session.activate_skill/deactivate_skill`; 32 000-char cap on injected skill bodies; per-run UUID threaded into `AGENT_START`/`AGENT_END` events + JSONL diagnostics via `PersistenceManager.append_run_diagnostic()`; `context_manager=None` guards on `/stats` and `/report`; `schema_version` future-version rejection in `load_session()` and `load_checkpoint()`; `add_assistant_message(content: str | None, ...)` annotation fix. 76 new tests.

---

## 5. Remaining work (specs)

### P2.1 layer 4 — Branching API  ✅ done (#8)
`Session.tree_choices()` / `Session.branch_to_entry(entry_id)` + `/branch` CLI command. Branch to a past message, live messages reconstruct that path, new messages extend the new branch, save→restore preserves active branch.

### P2.3b — Command registry  ✅ done (#8)
`CommandRegistry` + `CommandResult` replace the CLI `if/elif` chain. CLI is now a thin render layer.

### P2.3c — Re-entrant steering / follow-up queue  ✅ done (#9)
`SteeringQueue` two-lane FIFO; `Session.prompt(text, mode)` enqueues; agent drains at tool-batch boundaries (steer) and turn-end (follow-up); `asyncio.to_thread` for blocking input; `CancelledError` re-raised.

### P2.4 — Secondary hardening  ✅ done (#10)
All items resolved: MCP reconnect backoff, `allowed_tools` enforcement, 32 k skill-body cap, per-run UUID/JSONL diagnostics, `context_manager=None` guards, schema version validation, type annotation fix.

---

### Phase 3 — Textual TUI replacement  ⬅ recommended next

All prerequisites met. Replace the Rich print-renderer (`ui/tui.py`) with a full [Textual](https://textual.textualize.io/) app.

**Capabilities to build:**
- Non-blocking input field (no more `asyncio.to_thread` hack)
- Scrollback panel for assistant/tool output
- Slash + `@file` autocomplete in the input bar
- Sidebar: model / provider / thinking level / context-token meter
- Session picker (list + switch)
- Tree/branch picker (uses `Session.tree_choices()` + `Session.branch_to_entry()`)
- Steering input (uses `Session.prompt(text, "steer")` / `"follow_up"`)
- Thinking panel (collapsible, streams `THINKING_DELTA` events)
- Tool call panels (expandable diff/output, success/error styling)

**Architecture constraints:**
- `CommandResult` is the command layer — the TUI calls `get_registry().dispatch(...)` exactly as the CLI does today; no business logic in the TUI
- All events consumed via `AgentEvent` typed stream (`agent/events.py`) — no raw string parsing
- Keep a `--plain` / `--no-tui` flag that falls back to the current Rich renderer (`ui/tui.py`) for headless/pipe use
- The current `ui/tui.py` should be renamed `ui/plain.py`; `ui/tui.py` becomes the Textual app
- New dependency: `textual` (add to `pyproject.toml`)

**Tests:**
- Unit-test the TUI's event-to-widget mapping in isolation (mock widget tree)
- Integration-test the `--plain` fallback path to avoid regressions
- Snapshot tests for the sidebar stat display and tool-call panels

---

## 6. Guiding principles (unchanged)
1. **Bugs first** — correctness/safety before refactors.
2. **Adopt proven patterns** rather than inventing.
3. **The TUI swap comes last** — it depends on the session contract + typed events + branching above.
4. **No destructive migration without a fallback** — the tree always falls back to / migrates the flat snapshot.
