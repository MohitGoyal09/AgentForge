# CLI Reference

AgentForge exposes a top-level `agentforge` command and an interactive TUI command set.

## Top-Level Commands

### `agentforge`

Start the interactive TUI.

```bash
agentforge
```

### `agentforge run [PROMPT]`

Run a single prompt or start interactive mode if no prompt is provided.

```bash
agentforge run "summarize this repository"
agentforge run --cwd /path/to/project "inspect the code"
```

### `agentforge init`

Run the setup wizard. It writes project config and optional environment files with private permissions.

```bash
agentforge init
```

### `agentforge doctor`

Check local configuration and runtime readiness without calling a model.

```bash
agentforge doctor
agentforge doctor --json
agentforge doctor --cwd /path/to/project
```

### `agentforge report`

Print a saved session report without calling a model.

```bash
agentforge report
agentforge report --json
agentforge report --session-id <session_id>
agentforge report --data-dir /path/to/data
```

### `agentforge completion`

Print shell completion setup.

```bash
agentforge completion bash
agentforge completion zsh
agentforge completion fish
```

## Interactive Commands

| Command | Purpose |
| --- | --- |
| `/help` | Show TUI commands |
| `/exit`, `/quit` | Exit |
| `/new` | Reset the current session |
| `/clear` | Clear conversation history |
| `/reload` | Reload config from disk |
| `/version` | Show AgentForge version |
| `/retry` | Retry the last user message |
| `/history [n]` | Show recent messages |
| `/config` | Show redacted config |
| `/doctor` | Show doctor report |
| `/doctor fix` | Apply safe doctor fixes, such as `.gitignore` entries and private config permissions |
| `/provider [name]` | Show or switch provider for this session |
| `/models [--page N] [--limit N]` | List model suggestions for the current provider |
| `/model list` | Alias for `/models` |
| `/model [name]` | Show or change the model for this session |
| `/fallbacks` | Show or edit fallback models |
| `/paths` | Show config, env, session, checkpoint, skill, and cwd paths |
| `/compact` | Force context compaction |
| `/errors [n]` | Show recent model/tool errors |
| `/approval <mode>` | Change approval policy |
| `/tools` | List registered tools |
| `/skills` | List available skills |
| `/skill <name>` | Activate a skill manually |
| `/unskill <name>` | Deactivate a skill |
| `/mcp` | Show MCP server status |
| `/name [name]` | Show or set session name |
| `/save` | Save session snapshot |
| `/sessions [--page N] [--limit N]` | List saved sessions |
| `/resume <session_id>` | Resume a saved session |
| `/checkpoint` | Save a checkpoint |
| `/checkpoints [--page N] [--limit N]` | List checkpoints |
| `/restore <checkpoint_id>` | Restore a checkpoint |
| `/plan` | Switch to read-only plan mode |
| `/build` | Switch to normal build mode |
| `/todos` | Show todos |
| `/todos --clear` | Clear todos |
| `/stats` | Show session stats |
| `/report` | Show current session report |
| `/report --json` | Print current session report as JSON |
| `/export` | Export session as markdown |
| `/export html` | Export session as HTML |

## Suggested First Session

```text
/doctor
/tools
/skills
Read README.MD and explain the architecture.
/plan
Suggest a small improvement without editing files.
/build
Create a small notes file summarizing the project.
/checkpoint
/export html
/stats
```

## Approval Tips

- Use `on-request` for normal development.
- Use `never` for read-only exploration.
- Use `auto-edit` when you trust local edits but still want protection around riskier operations.
- Avoid `yolo` outside disposable sandboxes.
