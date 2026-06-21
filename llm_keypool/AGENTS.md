# llm_keypool Core Package

**Generated:** 2026-06-21
**Commit:** 8a0aaca

## OVERVIEW
Core logic: key storage, rotation, dispatch, CLI, TUI, proxy, LangChain wrapper.

## STRUCTURE
```
llm_keypool/
├── __init__.py           # Exports AggregatorChat
├── __main__.py           # Entry point → cli.app()
├── cli.py                # 9 Typer commands (293 lines)
├── key_store.py          # SQLite CRUD + audit + rotation (367 lines)
├── rotator.py            # Tier-based key selection (286 lines)
├── langchain_wrapper.py  # AggregatorChat (234 lines)
├── proxy.py              # FastAPI OpenAI-compatible (154 lines)
├── tui.py                # Textual TUI, 3 tabs (379 lines)
├── providers/            # Provider implementations (see AGENTS.md)
└── config/
    └── providers.json    # 40+ provider definitions
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Add/remove key | `cli.py:add` / `key_store.py` | `--provider`, `--key`, `--model`, `--capabilities` |
| Rotator logic | `rotator.py:select_key()` | Tier sort, cooldown, 429 handling |
| DB schema | `key_store.py:_init_db()` | keys, requests, rotation_state tables |
| Streaming | `proxy.py:_stream()` | SSE generator, real tokens for OpenAI-compat |
| TUI actions | `tui.py:action_*` | refresh, deactivate, clear cooldown |
| Provider dispatch | `dispatch.py:dispatch()` | Retry loop, header extraction |
| LangChain | `langchain_wrapper.py:AggregatorChat` | `_generate()`, `_agenerate()` |

## CONVENTIONS
- **DB**: All SQL uses parameterized queries EXCEPT `update_key()` dynamic SET (see parent ANTI-PATTERNS)
- **Async**: `dispatch()`, provider `complete()` are async; CLI wraps via `asyncio.run()`
- **Capabilities**: Use `capabilities: list[str]`, NOT legacy `category: str`
- **Errors**: `CompletionResult(ok, content, error, was_429, ...)` for all providers
- **Token count**: `tiktoken cl100k_base` for prompt tokens; chars/4 fallback

## ANTI-PATTERNS (THIS MODULE)
- ❌ `category` param in 6 signatures: `register_key()`, `complete()`, `make_app()`, `AggregatorChat`, `add()`, `proxy`
- ❌ `key_store.py:270` f-string SQL in `update_key()`
- ❌ `dispatch.py:45` `len(content)//4` token estimation
- ❌ `key_store.py:117-126` silent migration `except OperationalError: pass`
- ❌ `tui.py:278` bare `except Exception:` in `_load_audit()`

## KEY FUNCTIONS
| Function | File | Purpose |
|----------|------|---------|
| `KeyStore.register_key()` | `key_store.py:155` | Insert key with caps, model, provider |
| `KeyStore.get_active_keys()` | `key_store.py:200` | Filter by capability, respect cooldown |
| `Rotator.select_key()` | `rotator.py:180` | Pick key by tier → score → rotation |
| `Rotator.handle_429()` | `rotator.py:240` | Mark cooldown, persist state |
| `dispatch()` | `dispatch.py:13` | Route to provider, retry, extract headers |
| `_load_provider_configs()` | `cli.py:31`, `proxy.py:17` | Read `providers.json` |

## ENTRY POINTS
- `llm-keypool` → `__main__.py:main()` → `cli.app()`
- `python -m llm_keypool` → same

## GOTCHAS
- Rotation state persisted in `rotation_state` table (keyed by `cap_key`)
- `cap_key` = JSON-sorted capabilities joined by `,` (e.g., `general_purpose,fast`)
- Provider `extra_params` stored as JSON string in DB
- Think-token regex: `re.sub(r'\\{.*?\\}\\}', '', content, flags=re.DOTALL)`