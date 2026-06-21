# Provider Implementations

**Generated:** 2026-06-21
**Commit:** 8a0aaca

## OVERVIEW
All providers unified via `dispatch()` → `CompletionResult`. OpenAI-compatible providers share `OpenAICompatibleProvider`; Cloudflare & Cohere have native clients.

## STRUCTURE
```
providers/
├── __init__.py          # empty
├── base.py              # CompletionResult dataclass
├── dispatch.py          # Retry loop, 429 rotation, header parsing
├── headers.py           # Rate-limit header extraction (Groq, Cerebras, Mistral)
├── openai_compat.py     # AsyncOpenAI + think-token strip (Groq, Cerebras, OpenRouter, etc.)
├── cloudflare.py        # Cloudflare Workers AI (native REST)
└── cohere.py            # Cohere native API
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Add OpenAI-compat provider | `openai_compat.py` | Subclass `OpenAICompatibleProvider`, add to `providers.json` |
| Add native provider | `cloudflare.py` / `cohere.py` | Implement `async def complete(...)` → `CompletionResult` |
| Rate-limit parsing | `headers.py` | `extract_remaining_requests(provider, headers)` |
| Retry/rotation logic | `dispatch.py` | `MAX_RETRY_ATTEMPTS=10`, immediate retry on 429 |
| Think-token strip | `openai_compat.py:47` | `re.sub(r'\\{.*?\\}\\}', '', content, flags=re.DOTALL)` |

## CONVENTIONS
- **All provider calls**: `async def complete(messages, model, api_key, base_url, **kwargs) -> CompletionResult`
- **Streaming**: OpenAI-compat uses `AsyncOpenAI(stream=True)`; Cohere/Cloudflare simulate (single chunk)
- **429 handling**: Return `CompletionResult(..., was_429=True)` → `dispatch()` rotates to next key
- **Headers**: `extract_remaining_requests()` returns `int | None` for remaining requests
- **Error format**: `CompletionResult(ok=False, error="...", was_429=False)`

## ANTI-PATTERNS (THIS MODULE)
- ❌ `openai_compat.py:54` `except Exception as e:` — swallows all errors
- ❌ `cohere.py:46` `except Exception as e:` — same
- ❌ `cloudflare.py:38` `except Exception as e:` — same
- ❌ Error truncation: `str(e)[:200]` (openai_compat) / no body (cohere, cloudflare)
- ❌ No exponential backoff in `dispatch.py` — immediate 10 retries

## PROVIDER CONFIG (providers.json)
Each entry:
```json
{
  "name": "groq",
  "base_url": "https://api.groq.com/openai/v1",
  "key_prefix": "gsk_",
  "default_model": "llama-3.3-70b-versatile",
  "capabilities": ["general_purpose", "fast"],
  "rate_limit_rpm": 30,
  "quality_score": 90
}
```

## EXTENDING
1. Add entry to `providers.json`
2. If OpenAI-compatible: no code is auto-routed via `openai_compat.py`
3. If native: add module, implement `complete()`, register in `dispatch.py:PROVIDER_MAP`

## PROVIDER_MAP (dispatch.py:17)
```python
PROVIDER_MAP = {
    "groq": openai_compat,
    "cerebras": openai_compat,
    "openrouter": openai_compat,
    "sambanova": openai_compat,
    "mistral": openai_compat,
    "cloudflare": cloudflare,
    "google": openai_compat,
    "cohere": cohere,
    # ... auto-detected via key_prefix
}
```

## GOTCHAS
- `key_prefix` in config enables auto-detect on import (`gsk_` → groq, `sk-` → openai, etc.)
- `extra_params` passed via CLI `--extra key=val` stored as JSON in DB, forwarded to provider
- Cohere/Cloudflare streaming = single chunk (non-streaming response wrapped)
- `dispatch()` expects providers to return `was_429=True` on rate limit