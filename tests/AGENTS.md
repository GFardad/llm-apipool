# Test Suite

**Generated:** 2026-06-22 03:30:08
**Commit:** 69232d0

## OVERVIEW
pytest suite for CLI, key store, rotator, providers, proxy, streaming, TUI, and LangChain wrapper. Tests mock HTTP/TUI and avoid real API keys.

## STRUCTURE
```
tests/
├── __init__.py
├── test_cli.py                  # Typer CLI, import parsing, add/import flows
├── test_cli_extended.py         # CLI edge cases and isolated DB fixtures
├── test_headers.py              # Rate-limit header parsing
├── test_key_store.py            # KeyStore CRUD, cooldown, legacy migration
├── test_key_store_extended.py   # DB path resolution, capability parsing, edge cases
├── test_langchain_wrapper.py    # AggregatorChat sync/async wrapper tests
├── test_main.py                 # Console entry point
├── test_providers.py            # Provider clients, dispatch helpers, errors
├── test_proxy.py                # FastAPI TestClient proxy endpoints
├── test_rotator.py              # Rotator selection, 429, cooldown strategies
├── test_rotator_extended.py     # Tier filtering, model quality, scoring
├── test_streaming.py            # OpenAI chunk format, dispatch streaming path
├── test_tui_helpers.py          # Import parsing and TUI helper functions
└── test_tui_ui.py               # Textual `run_test()` UI flows
```

## WHERE TO LOOK
| Task | File | Pattern |
|------|------|---------|
| CLI isolated DB | `test_cli.py`, `test_cli_extended.py` | `CliRunner`, autouse `isolated_db` fixture |
| KeyStore tests | `test_key_store.py`, `test_key_store_extended.py` | `tmp_path`, SQLite fixture, legacy path copy |
| Rotator tests | `test_rotator.py`, `test_rotator_extended.py` | `Rotator` fixture, provider config dict |
| Provider tests | `test_providers.py` | `unittest.mock.patch`, `AsyncMock`, `MagicMock` |
| Proxy tests | `test_proxy.py` | FastAPI `TestClient`, monkeypatched DB |
| Streaming tests | `test_streaming.py` | Mock `AsyncOpenAI` stream and dispatch generators |
| TUI tests | `test_tui_ui.py` | `LLMKeyPoolApp().run_test(size=(80, 24))` |
| Header parsing | `test_headers.py` | `extract_remaining_requests()` edge cases |

## CONVENTIONS
- **Async**: mark async tests with `@pytest.mark.asyncio`.
- **Fixtures**: no `conftest.py`; fixtures are local to test files.
- **DB isolation**: use `tmp_path` + `monkeypatch.setenv("LLM_KEYPOOL_DB", ...)`.
- **HTTP**: mock `AsyncOpenAI`/provider clients; do not call real APIs.
- **TUI**: use Textual `run_test()` for headless UI flows.
- **Secrets**: test keys are dummy strings; never add real credentials.

## KEY FIXTURES / HELPERS
| Helper | Purpose |
|--------|---------|
| `isolated_db` | Autouse fixture in CLI tests; points DB at `tmp_path` |
| `db_path` | Per-file SQLite path fixture |
| `store` / `rotator` | Local KeyStore/Rotator fixtures in rotation tests |
| `key_data` | Minimal provider key dict for provider/streaming tests |
| `runner = CliRunner()` | Typer CLI invocation helper |

## RUN
```bash
pytest -xvs                    # All tests, verbose
pytest tests/test_rotator.py   # Single file
pytest -k "not extended"       # Skip extended suites
pytest --cov=llm_keypool       # Coverage report
```

## GOTCHAS
- `test_tui_ui.py` is large and uses real Textual app state; prefer helper tests for pure parsing.
- `test_providers.py` patches `llm_keypool.providers.openai_compat.AsyncOpenAI`.
- `test_streaming.py` validates OpenAI SSE chunk shapes, not live provider behavior.
- Pydantic/LangChain deprecation warnings may appear in wrapper tests.
- No CI workflow or pytest config was found; command defaults come from pytest/pytest-asyncio.