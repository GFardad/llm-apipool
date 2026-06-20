# llm-keypool

[![Tests](https://img.shields.io/badge/tests-451%20passing-brightgreen)](https://github.com/your-username/llm-keypool/actions)
[![Coverage](https://img.shields.io/badge/coverage-99%25-brightgreen)](https://github.com/your-username/llm-keypool/actions)
[![License](https://img.shields.io/badge/license-MIT-blue)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://www.python.org/downloads/)

## llm-keypool: The Ultimate Free-Tier LLM Gateway

A unified, production-grade CLI/TUI/Proxy/LangChain key-pool manager for 40+ free-tier LLM APIs with intelligent model routing.

### Features

- **40+ providers** - Groq, Cerebras, Mistral, OpenRouter, Google, SambaNova, and more
- **Auto-import from file** - Load keys from key-per-line, provider:key, multi-line blocks with `---`, or NDJSON formats
- **Smart Tier-based routing** - 4-tier model quality system with graceful fallbacks
- **Textual TUI** - Interactive interface for managing keys, viewing audit log, and importing keys
- **OpenAI-compatible proxy** - Local server that speaks the OpenAPI API for seamless integration with any agent or tool
- **LangChain integration** - `AggregatorChat` drop-in replacement for any LLM in LangChain chains
- **Batch key management** - Add, deactivate, clear cooldown, and audit keys via CLI
- **Alembic migrations** - Proper schema versioning instead of inline migration lists
- **Real streaming** - True SSE streaming for OpenAI-compatible providers (simulated for others)
- **99% test coverage** - 451 passing tests, zero lint/type/security issues
- **Think-token stripping** - Removes `\\{...\\}\\}` from reasoning model outputs
- **Persistent state** - SQLite with WAL mode; rotation position and cooldowns survive restarts
- **Subscriber tracking** - Attribute LLM calls to specific subscribers (e.g., `hermes.main`, `mdcore.ingest`)

### Quick Installation

```bash
# Install with all optional dependencies (TUI + proxy)
pip install "llm-keypool[all]"

# Or install minimal core
pip install llm-keypool
```

### Quick Start

```bash
# Register your free-tier API keys (one-time setup)
llm-keypool add --provider groq     --key gsk_...     --model llama-3.3-70b-versatile --capabilities general_purpose,fast
llm-keypool add --provider cerebras --key csk_...     --model llama3.3-70b          --capabilities general_purpose,fast
llm-keypool add --provider mistral  --key sk_...      --model mistral-large-latest  --capabilities agentic

# Check your key pool status
llm-keypool status

# Launch the interactive TUI
llm-keypool gui

# Or start the proxy server for OpenAI-compatible access
llm-keypool proxy --port 8000

# Use in your favorite OpenAI-compatible tool or agent
export OPENAI_API_BASE="http://localhost:8000/v1"
export OPENAI_API_KEY="keypool"

# Or use directly with LangChain
from llm_keypool import AggregatorChat
llm = AggregatorChat(capabilities=["general_purpose", "fast"])
response = llm.invoke("What is the capital of France?")
```

### Configuration

The key pool database is stored at `~/.llm-keypool/keys.db` by default.

Override the location by setting the `LLM_KEYPOOL_DB` environment variable:

```bash
export LLM_KEYPOOL_DB=/path/to/my/keys.db
```

### Providers List

llm-keypool supports the following 40+ free-tier LLM providers:

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

llm-keypool implements a intelligent 4-tier model routing system:

- **Tier 1 (Frontier)**: Best performance, highest cost (e.g., GPT-4o, Claude 3 Opus)
- **Tier 2 (High-Performance)**: Excellent balance (e.g., Llama 3 70B, Gemma 2 27B)
- **Tier 3 (Good OSS)**: Solid open-source options (e.g., Mistral Small, Phi-3)
- **Tier 4 (Fallback)**: Reliable fallbacks for when higher tiers are exhausted

The rotator automatically tries Tier 1 first, then falls back through Tiers 2-4 as keys become rate-limited. You can configure the preferred `quality_tier` and maximum `max_fallback_tier` via the CLI or LangChain wrapper.

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing guidelines, and how to add new providers.

### License

llm-keypool is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

### Acknowledgments

Special thanks to the open-source LLM providers who offer generous free tiers, enabling democratized access to AI technology.
