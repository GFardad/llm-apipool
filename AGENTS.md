# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-22 03:30:08
**Commit:** 69232d0
**Branch:** main

## OVERVIEW
Python 3.11 CLI/TUI/Proxy/LangChain key-pool manager for 40+ free-tier LLM APIs with tier-based routing, cooldown tracking, audit logging, and OpenAI-compatible proxy access. Stack: Typer, Textual, FastAPI, SQLite, Alembic, OpenAI SDK, LangChain Core.

## STRUCTURE
```
llm-keypool/
├── llm_keypool/          # Core package (see llm_keypool/AGENTS.md)
│   ├── __init__.py       # Exports AggregatorChat
│   ├── __main__.py       # Script entry
│   ├── cli.py            # Typer CLI: import/add/deactivate/logs/proxy/gui
│   ├── key_store.py      # SQLite WAL DB, audit log, rotation counters
│   ├── rotator.py        # Tier routing, cooldowns, balanced rotation
│   ├── proxy.py          # FastAPI OpenAI-compatible proxy
│   ├── tui.py            # Textual app, 5 tabs
│   ├── providers/        # Provider dispatch and clients (see AGENTS.md)
│   └── config/           # providers.json + model_quality.json
├── frontend/             # React dashboard (see frontend/AGENTS.md)
├── tests/                # pytest-asyncio, mocked HTTP/TUI/proxy tests
├── alembic/              # Migration env + 5 schema versions (see AGENTS.md)
├── docs/                 # Screenshots and Hermes integration notes
├── pyproject.toml        # Package metadata, deps, console script
├── README.md             # User guide
├── CONTRIBUTING.md       # Dev setup and provider extension guide
└── stress_test.py        # Live rotation stress tester (currently deleted)
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| CLI entry point | `__main__.py`, `cli.py` | `llm-keypool` script → `main()` → Typer `app` |
| Import formats | `cli.py:_parse_import_entry()`, `tui.py:_resolve_import_entries()` | key-per-line, `provider:key`, `---` blocks, NDJSON |
| Key persistence | `key_store.py` | SQLite WAL, parameterized queries, plaintext keys |
| Model routing | `rotator.py`, `config/model_quality.json` | 4 quality tiers, cooldown, slot rotation |
| Provider dispatch | `providers/dispatch.py` | 10 non-streaming retries, streaming single attempt |
| OpenAI-compatible providers | `providers/openai_compat.py` | `AsyncOpenAI.with_raw_response`, think-token stripping |
| Rate-limit headers | `providers/headers.py` | Groq/Cerebras/Mistral/GitHub/Interfaze parsers |
| OpenAI proxy | `proxy.py:make_app()` | `/v1/chat/completions`, `/v1/models`, `/health`, `/audit`, `/logs/*` |
| TUI | `tui.py`, local `tui_logs.py` | Textual `run_test()` coverage; local untracked log viewer exists |
| LangChain wrapper | `langchain_wrapper.py` | `AggregatorChat` bridges sync/async calls |
| Migrations | `alembic/env.py`, `alembic/versions/` | Dynamic DB path from env; 0001-0005 |
| Test patterns | `tests/test_*.py` | No `conftest.py`; local fixtures/mocks |
| Frontend | `frontend/` | React dashboard with KeyManager, TestConsole, dynamic providers/models |

## CODE MAP
| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `KeyStore` | class | `key_store.py:129` | DB CRUD, audit log, cooldown/counters |
| `Rotator` | class | `rotator.py:119` | Best-key selection, tier filtering, 429 handling |
| `AggregatorChat` | class | `langchain_wrapper.py:79` | LangChain `BaseChatModel` wrapper |
| `complete()` | func | `providers/dispatch.py:52` | Dispatch, retry, rotate, audit usage |
| `extract_remaining_requests()` | func | `providers/headers.py:215` | Normalize remaining-request headers |
| `make_app()` | func | `proxy.py:50` | Build FastAPI proxy app |
| `LLMKeyPoolApp` | class | `tui.py:596` | Main Textual TUI app |
| `ProxyLogsApp` | class | `tui_logs.py:147` | Local untracked TUI log viewer |

## CONVENTIONS
- **Imports**: new Python files start with `from __future__ import annotations`; older files are mixed.
- **Types**: prefer modern `list[str]`, `dict[str, Any]`, and `X | Y`; avoid `typing.List`/`Optional`.
- **Async**: provider calls are `async`; CLI/TUI bridge with `asyncio.run()` or Textual workers.
- **Config**: provider metadata lives in `llm_keypool/config/providers.json`; model tiers in `model_quality.json`.
- **DB**: SQLite WAL; `LLM_KEYPOOL_DB` overrides `~/.llm-keypool/keys.db`; SQL should stay parameterized.
- **Capabilities**: use `capabilities: list[str]`; `category` is legacy/migration-only.
- **Tests**: `pytest-asyncio`; mock external HTTP and TUI; no real API keys.
- **Provider contract**: return `CompletionResult` for non-streaming or an async generator of OpenAI chunk dicts for streaming.

## ANTI-PATTERNS (THIS PROJECT)
- Broad `except Exception` catches remain in provider, TUI, and local log modules; narrow new catches.
- Plaintext API keys are stored in SQLite; mask keys in logs and avoid printing raw values.
- Legacy `category` appears in migrations, docs, and tests; new APIs should use `capabilities`.
- Silent migration/index suppression in `key_store.py:148-153`; new migrations should fail loudly.
- Token estimation falls back to `len(content)//4` only when tiktoken fails; prefer tiktoken.
- Non-streaming 429 retries are immediate/capped in `dispatch.py`; streaming makes one attempt and does not retry.
- Local repo currently has `.bak` files and untracked local modules; do not delete or merge them without explicit instruction.

## UNIQUE STYLES
- **4-tier model quality**: Tier 1 Frontier → Tier 4 Fallback (`model_quality.json`).
- **Subscriber tracking**: every call/audit entry includes `subscriber_id` (e.g. `hermes.main`, `mdcore.ingest`).
- **Think-token stripping**: removes `` and `{...}}` style reasoning artifacts.
- **Provider auto-detect**: key prefixes map imports to providers (e.g. `gsk_`, `sk-`, `cs_`, `AIza`, `hf_`).
- **Proxy model alias**: `LLM-Keypool` is exposed by `/v1/models`.
- **Provider config**: 42 providers; paxsenix added for Claude via `sk-paxsenix-` prefix.

## COMMANDS
```bash
# Install
pip install -e ".[all]"        # TUI + proxy
pip install -e ".[dev,all]"    # dev + optional deps
pip install -e .               # core only

# Dev
pytest -xvs                    # all tests, verbose
pytest --cov=llm_keypool       # coverage
ruff check .                   # lint
mypy --strict llm_keypool      # type check
bandit -r llm_keypool          # security scan

# Run
llm-keypool status             # show key pool
llm-keypool gui                # Textual TUI
llm-keypool proxy --port 8000  # OpenAI-compatible proxy
alembic upgrade head           # apply DB migrations
```

## NOTES
- Current working tree is dirty; do not assume a clean repo or commit generated docs without checking diffs.
- No `.github/workflows`, `Makefile`, `ruff.toml`, or pytest config was found; `pyproject.toml` defines deps/scripts only.
- `llm_keypool/providers/openai_compat.py:258` currently has an f-string quoting syntax error; verify before changing provider code.
- DB default: `~/.llm-keypool/keys.db`; legacy path `~/.llm-aggregator/keys.db` is copied forward if present.
- Version: `1.0.0`; GitHub remote: `https://github.com/GFardad/llm-keypool`.