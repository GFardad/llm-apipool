# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-29 18:30:00
**Commit:** 0bdbb17
**Branch:** main

## OVERVIEW
Python 3.11 CLI/TUI/Proxy/LangChain key-pool manager for 40+ free-tier LLM APIs with tier-based routing, cooldown tracking, audit logging, and OpenAI-compatible proxy access. Stack: Typer, FastAPI, SQLite, Alembic, OpenAI SDK, LangChain Core. TUI (Textual) modules exist locally but are uncommitted.

## STRUCTURE
```
llm-apipool/
├── llm_apipool/              # Core package (see llm_apipool/AGENTS.md)
│   ├── __init__.py           # Exports AggregatorChat
│   ├── __main__.py           # Script entry
│   ├── cli.py                # Typer CLI: import/add/deactivate/logs/proxy/gui
│   ├── key_checker.py        # Provider probing for bulk-import auto-detect
│   ├── key_store.py          # SQLite WAL DB, audit log, rotation counters
│   ├── rotator.py            # Tier routing, cooldowns, balanced rotation
│   ├── proxy.py              # FastAPI OpenAI-compatible proxy
│   ├── group_routing.py      # Group-based routing (orphaned at root)
│   ├── providers/            # Provider dispatch and clients (see AGENTS.md)
│   ├── config/               # providers.json + model_quality.json
│   ├── api/                  # FastAPI app, routes, middleware (see api/AGENTS.md)
│   └── core/                 # 36 modules: routing, affinity, effort, pool, scoring (see core/AGENTS.md)
├── frontend/                 # React dashboard (see frontend/AGENTS.md)
├── tests/                    # 525+ pytest tests (see tests/AGENTS.md)
├── alembic/                  # Migration env + 9 schema versions
├── docs/                     # Screenshots and Hermes integration notes
├── scripts/                  # Benchmarks, utilities (bench_ttft.py)
├── .github/workflows/        # CI/CD (test.yml, publish.yml)
├── pyproject.toml            # Package metadata, deps, console script
├── README.md                 # User guide
├── CONTRIBUTING.md           # Dev setup and provider extension guide
└── .pre-commit-config.yaml   # pre-commit hooks (ruff, mypy, bandit)
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| CLI entry point | `__main__.py`, `cli.py` | `llm-apipool` script → `main()` → Typer `app` |
| Import formats | `cli.py:_parse_import_entry()`, tui local | key-per-line, `provider:key`, `---` blocks, NDJSON |
| Key persistence | `key_store.py` | SQLite WAL, parameterized queries, plaintext keys |
| Model routing | `rotator.py`, `config/model_quality.json` | 4 quality tiers, cooldown, slot rotation |
| Provider dispatch | `providers/dispatch.py` | Retry + rotate + audit; non-429 errors separated from rate-limits |
| OpenAI-compatible providers | `providers/openai_compat.py` | `AsyncOpenAI.with_raw_response`, think-token stripping, connection pooling |
| Rate-limit headers | `providers/headers.py` | Groq/Cerebras/Mistral/GitHub/Interfaze parsers |
| OpenAI proxy | `proxy.py:make_app()` | `/v1/chat/completions`, `/v1/models`, `/health`, `/audit`, `/logs/*` |
| FastAPI app builder | `api/app.py:make_app()` | Composes all routers, middleware, background services |
| TUI | tui.py (local, uncommitted) | Textual `run_test()` coverage; `tui_logs.py` log viewer |
| LangChain wrapper | `langchain_wrapper.py` | `AggregatorChat` bridges sync/async calls |
| Migrations | `alembic/env.py`, `alembic/versions/` | Dynamic DB path from env; 0001-0009 |
| API routes | `api/routes/` | keys, settings, models, chat, health, analytics, effort, bulk-import, tiers, anthropic, benchmarks |
| Settings save-all | `api/routes/settings.py:save_all_settings` | POST /api/settings/save-all — 12+ fields, error collection |
| Bulk import (probe) | `api/routes/bulk_import.py:auto_import` | POST /api/keys/auto-import — analyse + probe ambiguous keys |
| Effort/thinking config | `core/model_effort.py` | Per-model + global effort levels, injection priority (per-model ≻ global ≻ preset) |
| Affinity routing | `core/affinity.py` | UID-based key+model pinning, busy/semi-busy tracking |
| Health scoring | `core/health_scoring.py` | Key health scoring with seasonal/linear models |
| A/B testing | `core/ab_testing.py` | Variant assignment and experiment tracking |
| Prompt caching | `core/prompt_caching.py` | Provider-agnostic prompt caching layer |
| Fallback modes | `core/fallback_modes.py` | Tier-fallback strategies and mode switching |
| Test patterns | `tests/test_*.py` | No `conftest.py`; local fixtures/mocks |
| Frontend | `frontend/` | React dashboard with 7+ pages, Vitest tests, routing |
| CI/CD | `.github/workflows/test.yml` | Ruff, mypy, bandit, pytest + coverage, frontend build + test + tsc |
| Benchmarks | `scripts/bench_ttft.py` | Cold vs warm connection pool TTFT measurement, --ci mode |

## CODE MAP
| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `KeyStore` | class | `key_store.py:129` | DB CRUD, audit log, cooldown/counters |
| `Rotator` | class | `rotator.py:119` | Best-key selection, tier filtering, 429+non-429 error separation |
| `AggregatorChat` | class | `langchain_wrapper.py:79` | LangChain `BaseChatModel` wrapper |
| `complete()` | func | `providers/dispatch.py:52` | Dispatch, retry, rotate, audit usage |
| `extract_remaining_requests()` | func | `providers/headers.py:215` | Normalize remaining-request headers |
| `make_app()` | func | `api/app.py:41` | Build FastAPI proxy app with all routes |
| `_get_client()` | func | `providers/openai_compat.py` | Cached `AsyncOpenAI` client (connection pooling) |
| `handle_error()` | func | `rotator.py` | Separates 429 from non-429 to prevent false cooldowns |
| `analyse_bulk()` | func | `core/key_detection.py:113` | Bulk-import text classification |
| `check_key_against_provider()` | func | `key_checker.py` | Probe a key against a provider |
| `set_global_effort_level()` | func | `core/model_effort.py` | Apply unified effort level across all providers |
| `get_state_snapshot()` | func | `core/affinity.py:205` | Affinity routing introspection for dashboard |

## CONVENTIONS
- **Imports**: new Python files start with `from __future__ import annotations`; older files are mixed.
- **Types**: prefer modern `list[str]`, `dict[str, Any]`, and `X | Y`; avoid `typing.List`/`Optional`.
- **Async**: provider calls are `async`; CLI/TUI bridge with `asyncio.run()` or Textual workers.
- **Config**: provider metadata lives in `llm_apipool/config/providers.json`; model tiers in `model_quality.json`.
- **DB**: SQLite WAL; `LLM_APIPOOL_DB` overrides `~/.llm-apipool/keys.db`; SQL should stay parameterized.
- **Capabilities**: use `capabilities: list[str]`; `category` is legacy/migration-only.
- **Tests**: `pytest-asyncio`; mock external HTTP and TUI; no real API keys.
- **Provider contract**: return `CompletionResult` for non-streaming or an async generator of OpenAI chunk dicts for streaming.
- **Settings error handling**: `save_all_settings` collects errors per-field; invalid values never cause a 500.
- **Error handling**: `rotator.handle_error()` separates 429 (rate-limit, sets cooldown) from non-429 (transient, no cooldown).

## ANTI-PATTERNS (THIS PROJECT)
- Broad `except Exception` catches remain in provider, TUI, and local log modules; narrow new catches.
- Plaintext API keys are stored in SQLite; mask keys in logs and avoid printing raw values.
- Legacy `category` appears in migrations, docs, and tests; new APIs should use `capabilities`.
- Silent migration/index suppression in `key_store.py:148-153`; new migrations should fail loudly.
- Token estimation falls back to `len(content)//4` only when tiktoken fails; prefer tiktoken.
- Non-streaming 429 retries are immediate/capped in `dispatch.py`; streaming makes one attempt and does not retry.
- Do NOT call `available_slots()` from inside `affinity._lock` (threading.Lock, not RLock).
- Do NOT store raw API keys in new schema fields; `api_keys.api_key` is grandfathered plaintext.
- Do NOT hardcode `http://localhost:8000` in frontend — use `VITE_API_BASE` env var.
- Do NOT add a new provider by subclassing a non-existent `OpenAICompatibleProvider`.
- Do NOT rely on `key_store.MIGRATIONS` as canonical source (Alembic is the deploy path).
- `seen_key_ids` in streaming path can cause premature exhaustion — consider per-request uniqueness.

## UNIQUE STYLES
- **4-tier model quality**: Tier 1 Frontier → Tier 4 Fallback (`model_quality.json`).
- **Subscriber tracking**: every call/audit entry includes `subscriber_id` (e.g. `hermes.main`, `mdcore.ingest`).
- **Think-token stripping**: removes `\u001b{...}\u001b}` style reasoning artifacts.
- **Provider auto-detect**: key prefixes map imports to providers (e.g. `gsk_`, `sk-`, `cs_`, `AIza`, `hf_`).
- **Proxy model alias**: `LLM-Apipool` is exposed by `/v1/models`.
- **Effort level mapping**: unified low/medium/high maps to reasoning_effort (OpenAI), thinking+budget_tokens (Anthropic), thinking (DeepSeek), etc.
- **Connection pooling**: `_get_client()` caches `AsyncOpenAI` by connection params to reuse HTTP keep-alive.
- **Health scoring**: seasonal + linear models score key reliability per T1/T2 time windows.
- **A/B testing**: hash-based variant assignment with configurable experiment parameters.
- **Prompt caching**: provider-agnostic cache layer for repeated prompt prefixes.
- **Dark mode**: full dashboard dark mode with Radix UI + Tailwind, persisted via settings API.
- **Benchmarks page**: client-side benchmark display with historical run tracking.

## COMMANDS
```bash
# Install
pip install -e ".[all]"        # TUI + proxy
pip install -e ".[dev,all]"    # dev + optional deps
pip install -e .               # core only
uv sync --group dev --all-extras  # uv install with all extras

# Dev (Python)
pytest -xvs                    # all tests, verbose
pytest --cov=llm_apipool       # coverage
uv run pytest -q --tb=short    # quick run
ruff check .                   # lint
ruff format --check .          # format check
mypy llm_apipool               # type check
bandit -r llm_apipool -x tests # security scan

# Dev (Frontend)
cd frontend
npm ci                         # install deps
npm run build                  # tsc + vite build
npm test                       # vitest run
npx tsc --noEmit               # type check only

# Pre-commit
pre-commit install             # enable hooks
pre-commit run --all-files     # run once

# Run
llm-apipool status             # show key pool
llm-apipool proxy --port 8000  # OpenAI-compatible proxy
alembic upgrade head           # apply DB migrations

# Benchmark
uv run python scripts/bench_ttft.py --provider groq --ci
```

## NOTES
- `.github/workflows/test.yml` runs ruff, mypy, bandit (continue-on-error), pytest with coverage, frontend build + test + tsc.
- DB default: `~/.llm-apipool/keys.db`; legacy path `~/.llm-aggregator/keys.db` is copied forward if present.
- Version: `1.0.0`; GitHub remote: `https://github.com/GFardad/llm-apipool`.
- TUI modules (`tui.py`, `tui_logs.py`, `db/connection.py`) exist locally but are NOT committed; update docs if committed.
- `group_routing.py` at package root is orphaned — logically belongs in `core/`.
- `providers/adapters/` has file-name collisions with provider root (`cloudflare.py`, `cohere.py` at both levels).
- `core/` has duplicates remaining: health ×3, fallback ×2 (fallback.py kept, tiering/types/ratelimit removed Jun 2026).
- `pyproject.toml` has duplicate dev deps in `[project.optional-dependencies]` vs `[dependency-groups]`.
