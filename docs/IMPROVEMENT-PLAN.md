# AgentForge Improvement Plan & Status

> **Pickup doc for a fresh session.** Read this top-to-bottom and you have full context:
> what's done, how the code is structured now, how we work, and exactly what's left with specs.
> A reference harness exists locally at `/Users/mohit/Code/tau` (a Pi-style coding agent) used for
> design comparison. **Do NOT name that reference project in PR/commit text** — describe patterns
> generically. It's fine to consult it while implementing.

---

## 1. Current status (as of PR #7 merged)

`master` is green: **413 tests pass** (`/.venv/bin/python -m pytest -q`).

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
| **P2.1 layer 4** — branching API (`tree_choices`/`branch_to_entry`) | ✅ merged | — |
| **P2.3b** — command registry (`handle_command → CommandResult`) | 🔄 in progress | — |
| **P2.3c** — re-entrant steering / follow-up queue (`session.prompt(steer/follow_up)`) | ⬜ pending (highest risk) | — |
| **P2.4** — secondary hardening + remaining LOW bugs | ⬜ pending | — |
| **Phase 3** — Textual TUI replacement | ⬜ blocked on P2.3b/c + P2.1 layer 4 | — |

**Recommended next step:** P2.1 layer 4 (branching API) — it completes the session-tree feature and is lower risk than steering.

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

---

## 5. Remaining work (specs)

### P2.1 layer 4 — Branching API  ⬅ recommended next
Make the tree user-visible. Build on `session_tree.py`/`session_store.py`/`ContextManager`.
- `Session.tree_choices() -> list[...]`: list branchable points = the `KIND_MESSAGE` entries on the **active path** (id, short preview of content, role, position). Read from `context_manager.get_entries()` + `active_leaf_id`/`path_to_entry`.
- `Session.branch_to_entry(entry_id, *, summarize=False)`: append a `KIND_LEAF` entry pointing at `entry_id` (the new active tip), then `context_manager.load_from_entries(entries)` so the live messages become that branch's path. Persist via `tree_store.write_all`. Optional: when `summarize=True`, record a `BranchSummaryEntry`/compaction of the abandoned tail.
- Add a `/branch` (or `/rewind`) CLI command listing choices and switching.
- **Tests:** branch to a past message → live messages == that path; new messages after branching extend the new branch; original branch still reconstructable from its leaf; save→restore preserves the active branch.

### P2.3b — Command registry
Refactor the CLI's `if name == "/x"` chain (`cli/commands.py`) into a registry that maps command → handler and returns a structured `CommandResult` (fields like `exit`, `clear`, `notice`, `compact`, `switch_mode`, `error`, …) so both the CLI and the future TUI share one command layer. `Session.handle_command(text) -> CommandResult`. Keep behavior identical; this is enabling, not behavioral. Risk: medium (touches every command).

### P2.3c — Re-entrant steering / follow-up queue  (highest risk)
`Session.prompt(text, streaming_behavior="steer"|"follow_up")` with an internal queue so the user can inject a message mid-run without cancelling: *steer* = insert after the current tool batch; *follow_up* = run when the agent would otherwise stop. Emit `QueueUpdateEvent` (already defined in `events.py`) on queue changes. Also expose `is_running` (exists), `pop_latest_follow_up_message()`. No existing base to build on — design carefully, lots of edge cases.

### P2.4 — Secondary hardening + remaining LOW bugs
- MCP reconnection/backoff (a dropped server is permanently `ERROR`).
- Enforce skills `allowed_tools`; cap injected `SKILL.md` body size.
- Structured per-run diagnostics (UUID per run → JSONL) for debuggability.
- **Deferred LOW bugs (from the audit, still open):**
  - CLI `/stats`,`/report`,`/save`,`/checkpoint` lack a `context_manager`-None guard (only bites before `initialize()`).
  - `persistence.py` `schema_version` is read but never validated/migrated (`load_session`).
  - `agent.add_assistant_message` typing: param is `str` but called with `str | None` (works, but annotation lies).
  - (Fixed already in #7: atomic `memory.json` write; `write_file` bare excepts.)

### Phase 3 — Textual TUI replacement (blocked)
Replace the Rich print-renderer (`ui/tui.py`) with a full Textual app: non-blocking input, scrollback, slash + `@file` autocomplete, sidebar (model/provider/thinking/context tokens), session/tree pickers, steering input, thinking panel. **Depends on:** typed events ✅, session contract (P2.3b command registry + P2.3c steering + accessors ✅), and the branching API (P2.1 layer 4) for the tree picker. Keep a `--plain` fallback renderer. Preserve the current per-tool rich rendering.

---

## 6. Guiding principles (unchanged)
1. **Bugs first** — correctness/safety before refactors.
2. **Adopt proven patterns** rather than inventing.
3. **The TUI swap comes last** — it depends on the session contract + typed events + branching above.
4. **No destructive migration without a fallback** — the tree always falls back to / migrates the flat snapshot.
