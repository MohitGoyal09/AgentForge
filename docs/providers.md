# Provider Setup

AgentForge supports four provider modes.

## OpenRouter

Use this when you want one OpenAI-compatible endpoint that can route to many hosted models.

```toml
[model]
provider = "openrouter"
name = "openai/gpt-4o-mini"
```

Environment:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
```

Optional:

```bash
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

`agentforge init` sets the OpenRouter base URL automatically. You only need to override it manually if you use a proxy.

## OpenAI

Use this for the native OpenAI SDK path.

```toml
[model]
provider = "openai"
name = "gpt-4o-mini"
```

Environment:

```bash
OPENAI_API_KEY=sk-...
```

Leave `base_url` empty unless you intentionally use a proxy.

`agentforge init` does not ask for an OpenAI base URL.

## Anthropic

Use this for the native Anthropic SDK path.

```toml
[model]
provider = "anthropic"
name = "claude-3-5-sonnet-latest"
```

Environment:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

Leave `base_url` empty for the hosted Anthropic API.

`agentforge init` does not ask for an Anthropic base URL.

## Custom OpenAI-Compatible

Use this for local or self-hosted OpenAI-compatible endpoints such as Ollama, vLLM, LM Studio, or a private gateway.

```toml
[model]
provider = "custom"
name = "local/model"
base_url = "http://localhost:11434/v1"
```

Environment:

```bash
API_KEY=local-or-placeholder-key
BASE_URL=http://localhost:11434/v1
```

Custom providers must expose OpenAI-compatible chat completions and tool-call behavior.

`agentforge init` asks for the custom base URL before the API key so the local endpoint is explicit.

## Google / Gemini

Google/Gemini is not supported by the current provider adapter. Add it only after the runtime has a real Google client path or a documented OpenAI-compatible gateway path.

## Validation

After editing provider settings:

```bash
agentforge doctor
```

`doctor` checks local configuration without calling the provider.
