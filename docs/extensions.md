# Extending AgentForge

AgentForge is designed as a learning harness. Extension points should stay small, explicit, and easy to inspect.

## Custom Tools

Tools live behind the `Tool` interface:

- define a stable `name`
- write a concise `description`
- choose a `ToolKind`
- expose a Pydantic schema
- return a `ToolResult`

Good tool results include:

- `summary`: one-line outcome
- `artifacts`: paths or identifiers created/read
- `next_actions`: safe follow-up steps for the model
- `recovery_hint`: what to do when the tool fails

See [examples/custom_tool.py](../examples/custom_tool.py).

## Skills

Skills use the global `SKILL.md` format:

```markdown
---
name: my-skill
description: Use when ...
---

# My Skill

Short, task-specific instructions.
```

AgentForge discovers skills from:

1. project skills: `.agentforge/skills/*/SKILL.md`
2. global user skills: `~/.agents/skills/*/SKILL.md`
3. config skills: platform config `agentforge/skills/*/SKILL.md`
4. optional configured roots: `skill_roots = [".skills"]`

Progressive disclosure matters: only the skill name and description are indexed at startup. The full skill body is loaded into the prompt only when the user explicitly asks for it or the matcher selects it with enough confidence.

See [examples/skills/api-interface-design/SKILL.md](../examples/skills/api-interface-design/SKILL.md).

## Hooks

Hooks are external commands or scripts triggered around agent/tool events. They are useful for logging, policy checks, or local notifications.

Hook commands run as trusted local code. Keep them deterministic, avoid printing secrets, and prefer fail-open for observability hooks.

See [examples/hooks/log_tool_call.py](../examples/hooks/log_tool_call.py).

## Subagents

Subagents are bounded specialist calls. The parent agent stays in control and receives one result back from each child.

Use subagents for focused work such as:

- codebase exploration
- debugging analysis
- review
- test planning
- architecture mapping

Do not treat subagents as swarm mode. Swarm mode is orchestration across multiple workers, shared state, budgets, and result aggregation.

See [examples/subagents/code-review.toml](../examples/subagents/code-review.toml).

## Extension Checklist

- Keep schemas narrow and typed.
- Return structured tool observations.
- Add tests for success and failure paths.
- Document trust boundaries.
- Prefer project-local examples over hidden machine state.
