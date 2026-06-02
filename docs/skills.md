# Skills

Skills are local `SKILL.md` files that let AgentForge load task-specific guidance only when needed. This is the main progressive-disclosure mechanism in the harness.

## Why Skills Matter

Without skills, the system prompt grows every time you add guidance. That makes the agent slower, more expensive, and more confused.

With skills:

1. AgentForge indexes small metadata.
2. The matcher selects a relevant skill.
3. The full skill body is loaded only after selection.
4. References, assets, and scripts stay unloaded until needed.

## Skill Format

```markdown
---
name: api-interface-design
description: Use when designing APIs, module boundaries, public contracts, or frontend/backend interfaces.
---

# API Interface Design

Task-specific guidance goes here.
```

Required frontmatter:

- `name`
- `description`

The description should say when to use the skill. Good descriptions are specific enough to avoid loading the skill for unrelated tasks.

## Skill Roots

AgentForge discovers skills from:

1. Project skills: `.agentforge/skills/*/SKILL.md`
2. Global user skills: `~/.agents/skills/*/SKILL.md`
3. User config skills: platform config `agentforge/skills/*/SKILL.md`
4. Extra configured roots from `skill_roots`

Example:

```toml
skills_enabled = true
skill_roots = [".skills"]
```

## Folder Shape

```text
.agentforge/
`-- skills/
    |-- api-interface-design/
    |   `-- SKILL.md
    |-- debugging/
    |   |-- SKILL.md
    |   `-- references/
    `-- frontend-design/
        |-- SKILL.md
        `-- assets/
```

The global user directory follows the same shape:

```text
~/.agents/skills/
`-- my-skill/
    `-- SKILL.md
```

## Matching Rules

Automatic matching is intentionally conservative:

- Explicit user mentions win first, such as `use frontend-design skill`.
- Exact skill names beat fuzzy matches.
- Aliases, command names, display names, and folder names can count as metadata.
- Inferred matching should load at most one skill per user message.
- Low-confidence overlap should be ignored instead of bloating the prompt.

The TUI should show:

- matched skill
- match reason
- source file
- loaded line count

## Manual Commands

```text
/skills
/skill api-interface-design
/unskill api-interface-design
```

Manual activation is useful when the user knows exactly which skill should guide the run.

## Progressive Disclosure Rules

Keep these rules strict:

- Do not put inactive skill bodies in the system prompt.
- Do not load all global skills into model context.
- Do not load references unless the selected skill asks for them.
- Keep skill matching explainable in the TUI.
- Cap skill bodies so one large skill cannot crowd out the task.

## Writing Good Skills

Good skills:

- Solve one recurring task type.
- Say clearly when they should be used.
- Prefer checklists and decision rules over long essays.
- Link to references instead of embedding huge documents.
- Include examples only when they change behavior.

Avoid:

- broad skills that match everything
- vague descriptions like "use for coding"
- huge bodies with unrelated advice
- hidden dependencies that are not documented in the skill folder

## Planned Skills v2

The next major skill work after v1:

- better ranking without hardcoded task rules
- aliases and categories
- `agentforge skills validate`
- TUI explanation for selected and skipped skills
- lazy reference/asset/script loading
- install/list/update flows for local and global skill roots
