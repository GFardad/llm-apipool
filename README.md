# llm-apipool

[![Tests](https://img.shields.io/badge/tests-514%20passing-brightgreen)](https://github.com/GFardad/llm-apipool/actions)
[![Coverage](https://img.shields.io/badge/coverage-80%25-yellow)](https://github.com/GFardad/llm-apipool/actions)
[![License](https://img.shields.io/badge/license-MIT-blue)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/llm-apipool)](https://pypi.org/project/llm-apipool/)
[![Ruff](https://img.shields.io/badge/lint-ruff-orange)](https://github.com/astral-sh/ruff)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://hub.docker.com/)

## llm-apipool: The Ultimate Free-Tier LLM Gateway

A unified, production-grade CLI/TUI/Proxy/LangChain key-pool manager for 40+ free-tier LLM APIs with intelligent model routing.

### Features

- **40+ providers** — Groq, Cerebras, Mistral, OpenRouter, Google, SambaNova, and more
- **Auto-import from file** — Load keys from key-per-line, provider:key, multi-line blocks with `---`, or NDJSON formats
- **Smart Tier-based routing** — 4-tier model quality system with graceful fallbacks
- **React Dashboard** — Full-featured web UI with key management, model table, analytics, and settings
- **Textual TUI** — Interactive terminal interface for managing keys, viewing audit log, and importing keys
- **OpenAI-compatible proxy** — Local server that speaks the OpenAI API for seamless integration with any agent or tool
- **LangChain integration** — `AggregatorChat` drop-in replacement for any LLM in LangChain chains
- **Batch key management** — Add, deactivate, clear cooldown, and audit keys via CLI
- **Alembic migrations** — Proper schema versioning instead of inline migration lists
- **Real streaming** — True SSE streaming for OpenAI-compatible providers (simulated for others)
- **514 passing tests** — Comprehensive test suite covering key detection, effort config, bulk import, settings save-all, and routing
- **Think-token stripping** — Removes `\\{...\\}\\}` from reasoning model outputs
- **Effort/thinking per-model config** — Set reasoning_effort (OpenAI/xAI), thinking mode (Anthropic/Google/DeepSeek) with unified levels
- **Set-all effort** — Apply Low/Medium/High effort level across all providers at once via API or dashboard dropdown
- **Model context display** — See context window size at a glance in the dashboard model table
- **Persistent state** — SQLite with WAL mode; rotation position and cooldowns survive restarts
- **Docker support** — Multi-stage Dockerfile with healthcheck and docker-compose for production deployment
- **Subscriber tracking** — Attribute LLM calls to specific subscribers (e.g., `hermes.main`, `mdcore.ingest`)

### Quick Installation

```bash
# Install with all optional dependencies (TUI + proxy)
pip install "llm-apipool[all]"

# Or install minimal core
pip install llm-apipool
```

### Quick Start

```bash
# Register your free-tier API keys (one-time setup)
llm-apipool add --provider groq     --key gsk_...     --model llama-3.3-70b-versatile --capabilities general_purpose,fast
llm-apipool add --provider cerebras --key csk_...     --model llama3.3-70b          --capabilities general_purpose,fast
llm-apipool add --provider mistral  --key sk_...      --model mistral-large-latest  --capabilities agentic

# Check your key pool status
llm-apipool status

# Launch the interactive TUI
llm-apipool gui

# Or start the proxy server for OpenAI-compatible access
llm-apipool proxy --port 8000

# Use in your favorite OpenAI-compatible tool or agent
export OPENAI_API_BASE="http://localhost:8000/v1"
export OPENAI_API_KEY="keypool"

# Or use directly with LangChain
from llm_apipool import AggregatorChat
llm = AggregatorChat(capabilities=["general_purpose", "fast"])
response = llm.invoke("What is the capital of France?")
```

### Dashboard

Once the proxy is running, open **http://localhost:8000** in your browser to access the React dashboard:

- **Keys page** — Add, import, deactivate, and search keys with provider detection
- **Models page** — Browse all models with tier, context window, scoring, and effort configuration
- **Analytics page** — Usage statistics, rate-limit penalties, and key health
- **Settings page** — Routing strategy, sticky sessions, handoff mode, and quality tiers

### Effort & Thinking Configuration

Control reasoning effort across providers that support it:

```bash
# Via the dashboard — click the Effort button on any model row, or
# use the "Effort all…" dropdown in the Models toolbar to set a
# unified Low/Medium/High level for every model.

# Via API — unified level across all providers:
curl -X POST http://localhost:8000/api/models/effort/set-all \
  -H "Content-Type: application/json" \
  -d '{"level": "medium"}'

# Per-model override:
curl -X PUT http://localhost:8000/api/models/effort \
  -H "Content-Type: application/json" \
  -d '{"model_key": "openai:gpt-4o", "params": {"reasoning_effort": "high"}}'
```

The unified level maps to provider-specific parameters automatically:

| Level | OpenAI / xAI | Anthropic | Google | DeepSeek |
|-------|-------------|-----------|--------|----------|
| low | reasoning_effort: low | thinking: off | thinking: off | thinking: off |
| medium | reasoning_effort: medium | thinking: on (16K budget) | thinking: on | thinking: off |
| high | reasoning_effort: high | thinking: on (64K budget) | thinking: on | thinking: on |

### Configuration

The key pool database is stored at `~/.llm-apipool/keys.db` by default.

Override the location by setting the `LLM_APIPOOL_DB` environment variable:

```bash
export LLM_APIPOOL_DB=/path/to/my/keys.db
```

### Providers List

llm-apipool supports the following 40+ free-tier LLM providers:

| Provider | Suggested Model | Capabilities | Signup Link |
|----------|----------------|--------------|-------------|
| Groq | `llama-3.3-70b-versatile` | general_purpose, fast | https://console.groq.com/keys |
| Cerebras | `llama3.3-70b` | general_purpose, fast | https://cloud.cerebras.ai |
| Mistral | `mistral-large-latest` | agentic | https://console.mistral.ai/api-keys |
| OpenRouter | `meta-llama/llama-3.3-70b-instruct:free` | general_purpose | https://openrouter.ai/settings/keys |
| Google | `gemini-2.0-flash` | general_purpose, fast | https://aistudio.google.com/apikey |
| SambaNova | `Meta-Llama-3.3-70B-Instruct` | general_purpose | https://cloud.sambanova.ai/apis |
| Hugging Face | `google/gemma-2-27b-it` | general_purpose | https://huggingface.co/settings/tokens |
| Replicate | `meta/meta-llama-3.3-70b-instruct` | general_purpose | https://replicate.com/account/api-tokens |
| Cohere | `command-r-plus` | general_purpose | https://dashboard.cohere.com/api-keys |
| Anthropic | `claude-3-haiku-20240307` | agentic | https://console.anthropic.com/ |
| OpenAI | `gpt-4o-mini` | general_purpose | https://platform.openai.com/api-keys |
| ... and many more |

See [PROVIDER_GUIDE.md](PROVIDER_GUIDE.md) for the complete list with rate limits and signup instructions.

### Model Quality Tiers

llm-apipool implements a intelligent 4-tier model routing system:

- **Tier 1 (Frontier)**: Best performance, highest cost (e.g., GPT-4o, Claude 3 Opus)
- **Tier 2 (High-Performance)**: Excellent balance (e.g., Llama 3 70B, Gemma 2 27B)
- **Tier 3 (Good OSS)**: Solid open-source options (e.g., Mistral Small, Phi-3)
- **Tier 4 (Fallback)**: Reliable fallbacks for when higher tiers are exhausted

The rotator automatically tries Tier 1 first, then falls back through Tiers 2-4 as keys become rate-limited. You can configure the preferred `quality_tier` and maximum `max_fallback_tier` via the CLI or LangChain wrapper.

### Docker Deployment

```bash
# Build and run with docker-compose
docker compose up -d

# Or build manually
docker build -t llm-apipool .
docker run -d \
  -p 8000:8000 \
  -v llm-apipool-data:/data \
  -e LLM_APIPOOL_API_KEY=your-api-key \
  llm-apipool

# The proxy is now available at http://localhost:8000
# Health check: http://localhost:8000/health
```

Environment variables for Docker:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_APIPOOL_DB` | `/data/keys.db` | Database path (persisted via volume) |
| `LLM_APIPOOL_API_KEY` | (empty) | API key for proxy auth |
| `LLM_APIPOOL_ENCRYPTION_KEY` | (empty) | Key encryption passphrase |
| `LLM_APIPOOL_HEALTH_CHECK_INTERVAL` | `300` | Seconds between health checks |
| `LLM_APIPOOL_FORCE_PROVIDER` | (empty) | Force all traffic to one provider |

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing guidelines, and how to add new providers.

### License

llm-apipool is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

### Acknowledgments

Special thanks to the open-source LLM providers who offer generous free tiers, enabling democratized access to AI technology.
