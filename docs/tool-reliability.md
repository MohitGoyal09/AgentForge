# Tool Reliability Standard

AgentForge tools are the action space of the harness. A model can only recover well when tool schemas, observations, and errors are designed well.

## v1 Reliability Bar

Every built-in tool should aim for:

- A narrow, schema-first input model.
- A clear success summary.
- Useful artifacts such as touched paths, created files, or command metadata.
- Safe next actions when the model should inspect, retry, or stop.
- A recovery hint on failures.
- Cleaned and capped output before it enters model context.
- Secret redaction before output reaches the model, hooks, TUI, persistence, or exports.

## Error Contract

Tool errors should answer three questions:

1. What probably went wrong?
2. What is the safe retry path?
3. When should the model stop instead of retrying?

Example shape:

```text
Error: patch failed: target context did not match
[Next: Re-read the target file before retrying this patch.]
[Recovery: The file may have changed or may not have a trailing newline. Re-read exact bytes and retry only if the intended edit is still valid.]
```

## Observation Contract

Prefer structured `ToolResult` fields over burying everything in free-form output:

- `summary`: one-line outcome.
- `artifacts`: paths or identifiers the user/model may inspect.
- `next_actions`: concrete follow-up steps.
- `recovery_hint`: safe retry guidance for failures.
- `metadata`: machine-readable details for hooks, reports, and future replay.

## Mutating Tools

Mutating tools should be more explicit than read-only tools:

- Show affected paths before approval.
- Show a diff when practical.
- Reject paths outside the workspace unless explicitly allowed by config.
- Avoid partial writes when validation fails.
- Return enough information for the model to verify the result.

## Current Focus

Before v1, prioritize reliability tests for:

- `patch`: stale context, no trailing newline, missing parent directory, deletion fallback, path traversal, symlinks.
- `edit_file`: missing old text, duplicate matches, no-op edits, newline handling.
- `write_file`: parent directories, overwrite previews, binary-looking content, path safety.
- `shell`: dangerous commands, timeout, non-zero exit, very large output, control characters.
- `web_fetch` and `web_search`: network failures, empty results, untrusted web content.

## Design Rule

If a tool fails, the model should learn how to recover without guessing. If the safe recovery path is not obvious, the tool should say so.
