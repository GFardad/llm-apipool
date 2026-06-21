# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-21 00:00:00
**Commit:** 8a0aaca
**Branch:** main

## OVERVIEW
Production-grade CLI/TUI/Proxy/LangChain key-pool manager for 40+ free-tier LLM APIs with intelligent tier-based model routing. Python 3.11+, Typer CLI, Textual TUI, FastAPI proxy, SQLite persistence, Alembic migrations.

## STRUCTURE
```
llm-keypool/
├── llm_keypool/          # Core package (see AGENTS.md)
│   ├── providers/        # Provider implementations (see AGENTS.md)
│   └── config/           # providers.json - 40+ provider configs
├── tests/                # 451 tests, 99% coverage
├── alembic/              # 5 migrations (0001-0005)
├── docs/                 # Screenshots, Hermes integration guide
├── pyproject.toml        # Build config, deps, entry points
├── README.md             # User guide
├── CONTRIBUTING.md       # Developer guide
└── stress_test.py        # Live rotation stress tester
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| CLI commands | `llm_keypool/cli.py` | Typer app, 9 commands |
| Key persistence | `llm_keypool/key_store.py` | SQLite WAL, audit log, rotation state |
| Model routing | `llm_keypool/rotator.py` | 4-tier quality, 429 fallback |
| Provider dispatch | `llm_keypool/providers/dispatch.py` | Retry loop, header parsing |
| TUI | `llm_keypool/tui.py` | Textual app, 3 tabs |
| OpenAI proxy | `llm_keypool/proxy.py` | FastAPI, SSE streaming |
| LangChain wrapper | `llm_keypool/langchain_wrapper.py` | AggregatorChat |
| Add provider | | |
| Provider configs | `llm_keypool/config/providers.json` | 40+ entries, capabilities, limits |
| Migrations | `alembic/versions/` | Run `alembic upgrade head` |
| Test patterns | `tests/` | pytest-asyncio, mocks |

## CODE MAP
| Symbol | Type | Location | Refs | Role |
|--------|------|----------|------|------|
| `KeyStore` | class | `key_store.py` | 12 | DB CRUD, audit, rotation |
| `Rotator` | class | `rotator.py` | 8 | Tier routing, cooldown |
| `AggregatorChat` | class | `langchain_wrapper.py` | 3 | LangChain drop-in |
| `dispatch()` | func | `providers/dispatch.py` | 5 | Retry, 429 rotate |
| `extract_remaining_requests()` | func | `providers/headers.py` | 4 | Rate-limit headers |
| `OpenAICompatibleProvider` | class | `providers/openai_compat.py` | 6 | AsyncOpenAI + think-token strip |
| `CompletionResult` | dataclass | `providers/base.py` | 8 | Unified response |

## CONVENTIONS
- **Imports**: `from __future__ import annotations` in all new files
- **Types**: Modern `list[str]` / `dict` (PEP 604), not `List`/`Optional`
- **Errors**: Never broad `except Exception` — catch specific exceptions (see ANTI-PATTERNS)
- **Async**: All provider calls `async`; CLI/TUI bridge via `asyncio.run()`
- **Config**: JSON in `config/` loaded at runtime, not hardcoded
- **Tests**: `pytest-asyncio`, mock external HTTP, `tests/test_*.py`

## ANTI-PATTERNS (THIS PROJECT)
- ❌ `except Exception` — 4 locations currently violate this (see quality report)
- ❌ Raw `f-string` SQL — `key_store.py:270` builds SET clause dynamically
- ❌ Legacy `category` param — 8 locations still carry deprecated field
- ❌ Char-count token estimation — `dispatch.py:45` uses `len//4`
- ❌ Silent migration failures — `key_store.py:117-126` swallows `OperationalError`
- ❌ Plaintext API keys in SQLite — no encryption layer

## UNIQUE STYLES
- **4-tier model quality**: Tier 1 Frontier → Tier 4 Fallback (config in `model_quality.json`)
- **Subscriber tracking**: Every call tagged (e.g., `hermes.main`, `mdcore.ingest`)
- **Think-token stripping**: Regex `r'\\{.*?\\}\\}'` on all responses
- **Provider auto-detect**: 9 key prefixes (gsk_, sk-, cs_, mi_, AIza, hf_, or_, cohere_, cf-)
- **Import formats**: 4 formats (key-per-line, provider:key, --- blocks, NDJSON)

## COMMANDS
```bash
# Install
pip install -e ".[all]"        # TUI + proxy
pip install -e .               # core only

# Dev
pytest -xvs                    # 451 tests
ruff check . && mypy --strict  # lint + type
bandit -r llm_keypool          # security

# Run
llm-keypool status             # show pool
llm-keypool gui                # TUI
llm-keypool proxy --port 8000  # OpenAI-compatible proxy
```

## NOTES
- DB at `~/.llm-keypool/keys.db` (override via `LLM_KEYPOOL_DB`)
- Alembic replaces old inline `MIGRATIONS` list — always run migrations on deploy
- Version 1.0.0 — `python -m build` + `twine check dist/*` passes
- GitHub remote: `https://github.com/GFardad/llm-keypool` (forked from piyush-tyagi-13)