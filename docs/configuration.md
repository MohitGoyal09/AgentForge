# Configuration

AgentForge configuration combines environment variables and TOML config. Project-local config should live in `.agentforge/config.toml`.

## Load Order

Configuration is loaded from:

1. `.env`
2. user config directory from `platformdirs`
3. project-local `.agentforge/config.toml`

Project-local settings are the normal place to configure a repository.

## Minimal Config

```toml
approval = "on-request"
max_turns = 100

[model]
provider = "openrouter"
name = "minimax/minimax-m2.5:free"
temperature = 1.0
context_window = 256000
max_output_tokens = 4096
```

## Model Providers

Supported providers:

| Provider | API key env | Base URL env | Notes |
| --- | --- | --- | --- |
| `openrouter` | `OPENROUTER_API_KEY` or `API_KEY` | `OPENROUTER_BASE_URL` or `BASE_URL` | OpenAI-compatible routing |
| `openai` | `OPENAI_API_KEY` or `API_KEY` | `OPENAI_BASE_URL` or `BASE_URL` | Native OpenAI SDK path |
| `anthropic` | `ANTHROPIC_API_KEY` or `API_KEY` | `ANTHROPIC_BASE_URL` or `BASE_URL` | Native Anthropic SDK path |
| `custom` | `API_KEY` | `BASE_URL` | Local or self-hosted OpenAI-compatible endpoint |

See [Provider Setup](providers.md) for examples.

The setup wizard only asks for base URL when `provider = "custom"`. Hosted providers use their known defaults: OpenRouter receives `https://openrouter.ai/api/v1`, while OpenAI and Anthropic use their SDK defaults.

## Approval Modes

```toml
approval = "on-request"
```

| Mode | Meaning |
| --- | --- |
| `on-request` | Ask before non-safe mutating operations |
| `on-failure` | Allow most operations; useful for autonomous retries |
| `auto` | Auto-approve most operations except explicitly dangerous ones |
| `auto-edit` | Auto-approve safe commands; ask for edits and riskier operations |
| `never` | Reject non-safe operations |
| `yolo` | Approve all operations, including dangerous ones |

Use `on-request` for normal development. Use `yolo` only in disposable workspaces.

## Safety Flags

```toml
output_hygiene_enabled = true
redaction_enabled = true
prompt_injection_protection_enabled = true
```

- `output_hygiene_enabled`: strips terminal control noise and caps large tool output.
- `redaction_enabled`: removes common API keys, tokens, JWTs, private keys, and secret assignments from tool results and previews.
- `prompt_injection_protection_enabled`: marks tool observations as untrusted data before they reach the model.

These are not a sandbox. They reduce common risk, but shell commands, MCP servers, and local tools still run as trusted local code.

## Shell Environment

```toml
[shell_environment]
ignore_default_excludes = false
exclude_patterns = ["*KEY*", "*TOKEN*", "*SECRET*"]
set_vars = { NODE_ENV = "test" }
```

This controls which environment variables are passed to shell commands.

## Tool Allowlist

```toml
allowed_tools = ["read_file", "grep", "glob", "list_dir", "git_diff"]
```

If set, only these tools are available. This is useful for constrained demos, read-only work, or debugging tool behavior.

## Skills

```toml
skills_enabled = true
skill_roots = [".skills"]
```

AgentForge automatically detects project skills under `.agentforge/skills` and global user skills under `~/.agents/skills`. Use `skill_roots` for extra roots.

See [Skills](skills.md).

## Subagents

```toml
[[subagents]]
name = "code-explainer"
description = "Explains how specific code works"
goal_prompt = "You are a code explanation specialist."
allowed_tools = ["read_file", "glob", "list_dir"]
max_turns = 10
timeout_seconds = 120
```

Subagents are specialist tool calls. Keep them scoped and prefer read-only tools until orchestration is more mature.

## Hooks

```toml
hooks_enabled = true

[[hooks]]
name = "log_tool_call"
trigger = "after_tool"
command = "python3 examples/hooks/log_tool_call.py"
timeout_sec = 30
enabled = true
fail_closed = false
```

Supported triggers:

- `before_agent`
- `after_agent`
- `before_tool`
- `after_tool`
- `on_error`

Hooks run as trusted local code.

## MCP Servers

Stdio server:

```toml
[mcp_servers.filesystem]
enabled = true
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "."]
startup_timeout_sec = 10
```

HTTP/SSE server:

```toml
[mcp_servers.remote]
enabled = true
url = "http://localhost:8000/sse"
startup_timeout_sec = 10
```

MCP tools are registered with `server__tool` names to avoid collisions.

## Validation

Run:

```bash
agentforge doctor
agentforge doctor --json
```

Doctor checks config, provider keys, skill roots, MCP commands, hook paths, local trust warnings, and safety flags.
