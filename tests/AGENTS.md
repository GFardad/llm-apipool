# Test Suite

**Generated:** 2026-06-21
**Commit:** 8a0aaca

## OVERVIEW
451 tests, 99% coverage. pytest-asyncio, extensive mocking of external HTTP.

## STRUCTURE
```
tests/
├── __init__.py
├── test_cli.py                 # CLI commands (Typer CliRunner)
├── test_cli_extended.py        # Extended CLI scenarios
├── test_key_store.py           # KeyStore CRUD, cooldown, migration
├── test_key_store_extended.py  # Extended KeyStore edge cases
├── test_rotator.py             # Rotator selection, 429, persistence
├── test_rotator_extended.py    # Extended rotator scenarios
├── test_langchain_wrapper.py   # AggregatorChat mock tests
├── test_providers.py           # Provider dispatch, headers
├── test_streaming.py           # SSE streaming, think-token strip
├── test_tui_helpers.py         # TUI widget helpers
└── test_tui_ui.py              # TUI UI interactions
```

## WHERE TO LOOK
| Task | File | Pattern |
|------|------|---------|
| KeyStore tests | `test_key_store.py` | `KeyStore` fixture, in-memory SQLite |
| Rotator tests | `test_rotator.py` | `Rotator` fixture, mocked keys |
| CLI tests | `test_cli.py` | `runner = CliRunner()` |
| Provider tests | `test_providers.py` | `httpx_mock` / `respx` |
| Streaming tests | `test_streaming.py` | Mock `AsyncOpenAI` stream |
| TUI tests | `test_tui_ui.py` | `app.run_test()` |

## CONVENTIONS
- **Async**: `@pytest.mark.asyncio` on all async tests
- **Fixtures**: `key_store`, `rotator`, `provider_config` in `conftest.py` (if exists)
- **Mocking**: `httpx_mock` for HTTP, `AsyncMock` for provider calls
- **No external calls**: All HTTP mocked; no real API keys in tests
- **Coverage target**: 95%+ (currently 99%)

## KEY FIXTURES
| Fixture | Purpose |
|---------|---------|
| `key_store` | In-memory SQLite KeyStore |
| `sample_keys` | Pre-populated keys for rotation tests |
| `provider_config` | Minimal provider config dict |

## RUN
```bash
pytest -xvs                    # All tests, verbose
pytest tests/test_rotator.py   # Single file
pytest -k "not extended"       # Skip extended tests
pytest --cov=llm_keypool       # With coverage
```

## GOTCHAS
- `test_tui_ui.py` uses Textual's `run_test()` — headless TUI testing
- `test_streaming.py` mocks `AsyncOpenAI` chunk iteration
- Pydantic v2 deprecation warnings in `test_langchain_wrapper.py` (expected)
- 7 uncovered lines: `__main__.py:12`, `rotator.py:223,259`, `dispatch.py:90`, `cloudflare.py:73`, `cohere.py:73`, `langchain_wrapper.py:195`