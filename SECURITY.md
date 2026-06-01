# Security Model

AgentForge is a local coding-agent harness. It helps make agent actions inspectable and approval-gated, but it is not a sandbox.

## What AgentForge Protects

- Mutating tools can require approval before running.
- Tool arguments and approval previews are redacted before display and hooks.
- Tool outputs are cleaned for unsafe control characters.
- Tool outputs are redacted before model context, hooks, persistence, and exports.
- Tool observations are marked as untrusted model-visible content.
- `agentforge doctor` checks common local safety risks.

## What AgentForge Does Not Protect

- Shell commands run on your machine.
- MCP servers are trusted executable integrations.
- Hooks run as local commands or scripts.
- File tools can change files you approve.
- Approval gates are not operating-system isolation.
- Secret redaction is best-effort and should not be treated as a secret manager.

## Recommended Defaults

- Use `approval = "on-request"` for normal interactive work.
- Keep `redaction_enabled = true`.
- Keep `output_hygiene_enabled = true`.
- Keep `prompt_injection_protection_enabled = true`.
- Store secrets in the user config directory or in an ignored `.env`.
- Keep `.env` and config files private: `chmod 600`.
- Run `agentforge doctor` after setup and before releases.

## MCP Trust Boundary

MCP servers are code you choose to run. Treat them like local dependencies:

- install them from trusted sources
- review their command and arguments
- avoid passing unnecessary secrets
- prefer project-scoped working directories

AgentForge warns about MCP trust, but it does not sandbox MCP servers yet.

## Reporting Security Issues

Do not open public issues for private vulnerabilities or exposed credentials. Contact the maintainer privately, rotate any exposed secrets immediately, and include the smallest safe reproduction.
