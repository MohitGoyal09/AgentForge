# Manual Pre-Release Test

Run this before publishing a package. The goal is to experience AgentForge like a first-time user.

## 1. Build Fresh Artifacts

```bash
python3 scripts/release_smoke.py
```

This removes old `dist/` artifacts, runs tests, runs doctor checks, builds a fresh wheel/sdist, and runs `twine check`.

## 2. Install the Local Wheel

Use a clean environment:

```bash
python3 -m venv /tmp/agentforge-v1-test
source /tmp/agentforge-v1-test/bin/activate
pip install /path/to/Agentforge/dist/agentforge_harness-0.1.0-py3-none-any.whl
agentforge --version
```

## 3. Create a Fresh Demo Project

```bash
mkdir -p /tmp/agentforge-demo
cd /tmp/agentforge-demo
agentforge init
agentforge doctor
```

Confirm:

- config is created
- API key guidance is clear
- hosted providers do not ask for a base URL
- custom provider asks for base URL before API key
- doctor output is understandable
- no private machine paths leak into generated config

## 4. TUI Smoke Test

Start:

```bash
agentforge
```

Then test:

```text
/help
/doctor
/tools
/skills
List the files in this directory.
Create a file called notes.txt with one sentence about AgentForge.
Read notes.txt.
Edit notes.txt to add one more sentence.
/checkpoint
/checkpoints
/export html
/stats
/exit
```

Confirm:

- approval prompts are readable
- file tools show useful summaries
- failed commands give recovery hints
- TUI text does not overlap badly
- `/export html` creates a readable export

## 5. Skill Test

Create a local skill:

```text
.agentforge/skills/demo/SKILL.md
```

With content:

```markdown
---
name: demo
description: Use when the user asks for a tiny AgentForge demo response.
---

# Demo

Answer in two short bullet points.
```

Then run:

```text
/reload
/skills
use demo skill and explain AgentForge
/unskill demo
```

Confirm:

- the skill appears in `/skills`
- the TUI shows activation reason and file path
- the skill body affects the response
- inactive skills are not all dumped into context

## 6. Provider Test

At least one real model call should work for the provider you intend to document as the default.

Test:

```text
Read README.MD if it exists, otherwise explain this empty project.
```

Confirm:

- streaming works
- tool calls work
- final answer appears
- no provider-specific crash occurs

## 7. Publish Readiness

You are ready to publish an alpha package when:

- local wheel install works
- `agentforge init` works in a clean directory
- `agentforge doctor` gives actionable output
- one real model call works
- read/write/edit tool flow works
- approval prompt is understandable
- skills list and manual activation work
- session export works
- release smoke passes

If any step feels confusing, fix docs or UX before publishing.
