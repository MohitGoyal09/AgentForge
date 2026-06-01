# AgentForge Examples

These examples are intentionally small. They show extension shapes without hiding the harness behind a framework.

## Create Your First Skill

Copy the sample skill:

```bash
mkdir -p .agentforge/skills/api-interface-design
cp examples/skills/api-interface-design/SKILL.md .agentforge/skills/api-interface-design/SKILL.md
agentforge
```

Then ask:

```text
use api-interface-design skill and review my tool schema
```

## Create Your First Tool

Read [custom_tool.py](custom_tool.py). A tool needs:

- a stable name
- a Pydantic parameter schema
- a `ToolKind`
- a `ToolResult`

Project-local dynamic tool loading is under `.agentforge/tools`.

## Run Plan Mode

```text
/plan
inspect this project and tell me what needs to change
```

Plan mode filters out mutating tools at the harness level.

## Use Patch Tool

Ask for coherent multi-file changes through `apply_patch`, and use `read_file` before patching files with exact context.

Patch is best for diffs. For simple append-only edits, prefer `append_file`. For exact string replacement, prefer `edit`.

## Resume A Session

```text
/sessions
/resume <session_id>
```

Export a session:

```text
/export html
```
