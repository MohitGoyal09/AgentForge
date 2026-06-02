# Persistence

AgentForge records enough state to resume sessions, inspect runs, export reports, and create checkpoints. This is the foundation for future deterministic replay.

## Persistence Surfaces

| Surface | Status | Purpose |
| --- | --- | --- |
| Session snapshot | Implemented | Resume a saved interactive session |
| Event log | Implemented | Inspect what happened during a run |
| Checkpoint | Implemented | Restore chat/context state to a saved point |
| Markdown export | Implemented | Human-readable session export |
| HTML export | Implemented | Richer export with collapsible transcript entries |
| JSON report | Implemented | Machine-readable session summary |
| Deterministic replay | Planned | Re-run a trace without calling a model |
| Workspace rollback | Planned | Restore file state, not only chat/context state |

## Sessions

Snapshots store:

- schema version
- session ID and optional name
- created and updated timestamps
- turn count
- working directory
- redacted config snapshot
- message history
- tool call metadata
- latest and total token usage
- active tools
- MCP server names
- todos
- active mode
- active skills
- event sequence

Interactive commands:

```text
/save
/sessions
/resume <session_id>
/name <name>
```

Top-level report command:

```bash
agentforge report
agentforge report --json
agentforge report --session-id <session_id>
```

## Event Logs

Event logs are append-only JSONL records. They capture the sequence of runtime events such as:

- user turn start
- model text deltas
- tool call start
- tool call complete
- approval decisions
- errors

Event logs are useful for debugging and will become the base for deterministic replay.

## Checkpoints

Checkpoints currently restore chat/context state. They do not yet restore changed files.

Interactive commands:

```text
/checkpoint
/checkpoints
/restore <checkpoint_id>
```

Current checkpoint state includes:

- message history
- token usage
- redacted config snapshot
- working directory
- active tools
- MCP server names
- todos
- event sequence

Still planned:

- changed-file snapshots
- git diff capture
- checkpoint reasons such as manual, before mutation, or before dangerous command
- workspace restore
- deterministic replay from event logs

## Exports

```text
/export
/export html
```

Markdown export is useful for notes and handoffs. HTML export is better for reviewing a session transcript with tool calls and summary cards.

## Safety Notes

Persistence uses redacted config snapshots and redacted tool observations, but users should still avoid storing secrets in prompts or files. Redaction catches common secret shapes; it is not a complete data-loss-prevention system.

## Future Replay Direction

Replay should eventually allow:

- loading an event log
- reconstructing tool calls and observations
- skipping model calls
- comparing old and new harness behavior
- debugging why a tool/action loop happened

This should land before local evals, because evals need a reliable trace format.
