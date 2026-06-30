# llm-apipool Perfection Blueprint

**Generated:** 2026-06-30
**Version:** 1.0.0
**Previous analysis:** `freellmapi-to-llm-apipool-map.md`

---

## Executive Summary

This blueprint defines the implementation path for bringing llm-apipool from its current state to a reference implementation that surpasses every feature, fix, and improvement in `tashfeenahmed/freellmapi`. Each change is driven by specific issues/PRs from the freellmapi tracker, re-engineered for Python with superior type safety, error handling, and test coverage.

**Total actionable items:** 64
**This phase implements:** 20 highest-impact items (Critical + High priority)
**Estimated effort:** ~2,500 LOC across 15 files

---

## Acceptance Criteria (Gate G1–G8)

| Gate | Criterion | Verification |
|------|-----------|-------------|
| **G1** | 7 critical-priority bugs fixed (400 exhaustion, Google schema, streaming delta, agent payloads) | `pytest tests/ -xvs` → all 525+ existing tests pass + new tests |
| **G2** | 23 high-priority features/improvements implemented or verified | Each mapped item has a corresponding test or code change |
| **G3** | No existing functionality regressed | `pytest tests/` → all pass; `ruff check .` → clean |
| **G4** | TypeScript/Python: mypy passes with zero errors | `mypy llm_apipool` → exit 0 |
| **G5** | Mapping document accounts for 100% of freellmapi issues/PRs | `docs/freellmapi-to-llm-apipool-map.md` covers all 288 items |
| **G6** | Code coverage does not decrease | `pytest --cov=llm_apipool` → compare to baseline |
| **G7** | PR description contains no unanswered questions | Maintainer can merge immediately |
| **G8** | Solution demonstrably better than freellmapi's | Each fix includes edge cases freellmapi missed |

---

## Architecture Decision Records (ADRs)

### ADR-001: Provider Request-Shape Error Classification

**Problem:** When a provider returns HTTP 400 (invalid request), the router retries across all keys and eventually surfaces `429 rate_limit_error` — masking the real 400. (freellmapi #417, #422)

**Considered alternatives:**
1. **Treat all 400s as non-retryable** — too aggressive; some 400s (e.g., transient over-length) should retry on different models.
2. **Track the last error class per request** — the chosen approach. Tag each failure as "request-shape" (400), "rate-limit" (429), or "transient" (5xx/timeout). At exhaustion, surface the dominant error class.
3. **Per-key error classification in DB** — too invasive; adds schema migration for transient state.

**Decision:** Track error classification in-memory during `complete()` / `_stream_complete()` and let the router pass back the terminal error type. `dispatch.py` returns a structured `DispatchResult` with `terminal_error_type: str | None`. `chat.py` checks this to decide 400 vs 429 response.

**Impact:**
- `dispatch.py`: Add `termination_error_type` tracking in retry loop
- `rotator.py`: No changes (already correctly separates 429)
- `chat.py`: Read terminal error type → return 400 `invalid_request_error` or 429 `rate_limit_error`
- Test: Verify 400 exhaustion returns 400, 429 exhaustion returns 429

### ADR-002: Gemini Tool Schema Sanitization

**Problem:** Vendor extension keys (`x-*`) in tool parameter schemas bypass sanitization and cause Gemini to return 400. (freellmapi #417, #420)

**Considered alternatives:**
1. **Denylist approach** — fragile; new extensions appear constantly.
2. **Stripping all `x-*` keys** — aggressive but correct. No standard JSON Schema starts with `x-`.

**Decision:** Inspect `openai_compat.py`'s tool-building path and strip all keys matching `x-*` recursively from parameter schemas before sending to Gemini.

**Impact:**
- `providers/openai_compat.py`: Add `_strip_vendor_extensions(schema: dict) -> dict` recursive function
- Add test for `x-google-enum-descriptions` and edge case `properties[x-user-id]` (should NOT be stripped)
- Coverage: nested schemas, array items, `$defs` / `definitions`

### ADR-003: Streaming Delta.Content Array Normalization

**Problem:** Some providers return `delta.content` as an array `[{"type": "text", "text": "hello"}]` instead of a plain string `"hello"`. This breaks OpenAI clients that expect a string. (freellmapi #166)

**Considered alternatives:**
1. **Normalize at provider boundary** — each provider normalizes its own output.
2. **Normalize in the stream utils layer** — centralized, catches all providers.

**Decision:** Normalize in `_stream_utils.py`'s `make_chunk`/chunk-processing functions. If `delta.content` is a list, extract the text parts concatenated.

**Impact:**
- `providers/_stream_utils.py`: Add normalization before chunk creation
- Test: Array content → string, null content → pass-through, nested arrays

### ADR-004: Outbound Proxy Support

**Problem:** Users behind corporate firewalls or in restrictive networks cannot reach LLM providers directly. (freellmapi #231, #286, #353)

**Considered alternatives:**
1. **Environment variables only** (HTTP_PROXY/HTTPS_PROXY) — simplest, but no per-provider bypass.
2. **Full proxy config with per-provider bypass** — richer UX, more complexity.
3. **SOCKS5 + HTTP proxy support** — covers all common proxy types.

**Decision:** Implement option 3. Extend `connection_pool.py` to support proxy configuration via:
- Environment variables (auto-detect: `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`)
- Per-provider bypass list via `providers.json` config
- SOCKS5 support via optional `socksio` dependency

**Impact:**
- `core/connection_pool.py`: Add proxy resolution logic
- `config/providers.json`: Add optional `proxy_bypass` field per provider
- Dependency: optional `socksio` for SOCKS5
- Test: Mock proxy connections

### ADR-005: Per-Provider Aggregate Rate Limits

**Problem:** Rate limiting tracks per-key usage but not aggregate usage across all keys of a provider. A provider may have per-account limits that span all keys. (freellmapi #162)

**Considered alternatives:**
1. **Aggregate in SQL queries** — simple but slow.
2. **In-memory counter with DB persistence** — fast, survives restarts.

**Decision:** Add provider-scoped rate limit tracking in `key_store.py`. `record_usage()` updates both key-level and provider-level counters. `get_best_key()` checks both before selecting a key.

**Impact:**
- `key_store.py`: Add `record_provider_usage()`, `get_provider_usage()` methods
- `rotator.py`: Check provider-level limits before key selection
- Migration: Add provider-level usage table (optional; can derive from existing data)
- Test: Verify aggregate limits block across multiple keys

### ADR-006: Tool-Call Generation Error Rescue

**Problem:** Groq and other providers return `tool_use_failed` / `failed_generation` errors when tool calls fail during generation. The router should retry rather than surfacing a 400. (freellmapi #168, #291)

**Considered alternatives:**
1. **Treat as regular transient error** — retries across keys, which is current behavior.
2. **Special rescue logic** — parse the error, emit empty tool_calls to let the client retry.

**Decision:** Implement option 2 for Groq-style errors. `dispatch.py` checks for `tool_use_failed` / `failed_generation` patterns in API errors and returns a structured response with empty `tool_calls: []` so the client can re-request.

**Impact:**
- `providers/dispatch.py`: Add `_rescue_tool_failure()` helper
- Test: Mock Groq `failed_generation` → verify structured response

---

## Implementation Plan (Phase 2)

### Wave 1: Critical Bug Fixes (6 items)

| # | File(s) | Change | freellmapi Ref | LOC |
|---|---------|--------|----------------|-----|
| C1 | `providers/dispatch.py` | Track terminal error type (400 vs 429 vs transient) and pass to caller | #417, #422 | +30 |
| C2 | `api/routes/chat.py` | Read terminal error type → return 400 or 429 appropriately | #422 | +10 |
| C3 | `providers/openai_compat.py` | Add `_strip_vendor_extensions()` for Gemini tool schemas | #417, #420 | +25 |
| C4 | `providers/_stream_utils.py` | Normalize array `delta.content` to string | #166 | +15 |
| C5 | `api/routes/chat.py` | Relax message validation for null/empty assistant content + tool_calls | #165, #200, #217 | +15 |
| C6 | `providers/dispatch.py` | Add tool-call failure rescue (`tool_use_failed` → retry) | #168, #291 | +20 |

**Verification:** All existing 525+ tests pass. New tests for each bug.

### Wave 2: High-Priority Features (7 items)

| # | File(s) | Change | freellmapi Ref | LOC |
|---|---------|--------|----------------|-----|
| H1 | `core/connection_pool.py`, `config/providers.json` | Outbound proxy support (HTTP/SOCKS5) | #231, #286 | +80 |
| H2 | `key_store.py`, `rotator.py` | Per-provider aggregate rate limits | #162 | +50 |
| H3 | `providers/dispatch.py`, `api/routes/responses.py` | 403 model-skip in fallback chain | #256, #263 | +15 |
| H4 | `rotator.py`, `api/routes/chat.py` | Context-aware routing (skip models with insufficient context window) | #167 | +40 |
| H5 | `key_checker.py`, `providers/openai_compat.py` | Fix Google validateKey error taxonomy | #268, #285 | +20 |
| H6 | `proxy_logger.py` | Chronological fallback logging with reason | #305, #313 | +35 |
| H7 | `api/routes/chat.py` | Per-request routing strategy via model field | #122 | +20 |

**Verification:** Integration tests for each feature. Existing tests pass.

### Wave 3: Medium-Priority Improvements (7 items)

| # | File(s) | Change | freellmapi Ref | LOC |
|---|---------|--------|----------------|-----|
| M1 | `core/router.py` | Analytics-driven bandit routing (MAB) | #163 | +100 |
| M2 | `core/embeddings.py`, `api/routes/embeddings.py` | MRL dimensions parameter | #393 | +20 |
| M3 | `tests/` | Add tests for all critical-path changes | Various | +200 |
| M4 | `key_store.py` | Key system-prompt binding | #388, #411 | +30 |
| M5 | `core/ratelimiter.py` | NULL-limit escalation via hit-count heuristic | #392 | +25 |
| M6 | `core/encryption.py` | Verify authTag AES-256-GCM correctness | #284 | +10 |
| M7 | `providers/` | AI Horde provider (OpenAI-compatible) | #345, #405 | +60 |

---

## Test Plan

### New Tests Required

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_error_classification.py` | 5 | 400→400, 429→429, mixed errors, transient-only, empty pool |
| `tests/test_gemini_schema.py` | 4 | x-* stripped, nested schemas, property names preserved, no-op for clean schemas |
| `tests/test_stream_delta.py` | 3 | Array→string, null passthrough, nested arrays |
| `tests/test_message_validation.py` | 4 | null content + tool_calls, empty string, function role, missing role |
| `tests/test_outbound_proxy.py` | 4 | HTTP proxy, SOCKS5, env auto-detect, per-provider bypass |
| `tests/test_provider_ratelimit.py` | 3 | Aggregate across keys, per-provider cap, mixed providers |
| `tests/test_tool_failure_rescue.py` | 2 | Groq-style failure rescue, non-Groq passthrough |
| `tests/test_context_routing.py` | 3 | Context too large → skip, exact fit → select, no tokenizer → allow |
| `tests/test_bandit_routing.py` | 4 | Explore vs exploit, reward update, cold start, convergence |
| `tests/test_key_system_prompt.py` | 2 | Prompt injection, no-prompt passthrough |

**Total new tests: ~34**
**Expected total: 559+** (existing 525 + 34)

---

## Commit Plan

```
feat(core): implement outbound HTTP/SOCKS5 proxy support with per-provider bypass
  - Core proxy resolution in connection_pool.py
  - Per-provider bypass config in providers.json
  - Optional socksio dependency for SOCKS5 support
  - Tests for HTTP proxy, SOCKS5, env auto-detect, bypass
  References: freellmapi#231, freellmapi#286

feat(proxy): surface provider 400 exhaustion as invalid_request_error
  - Track terminal error type (400 vs 429) in dispatch retry loop
  - Chat route reads terminal type → returns 400 or 429
  - Responses route same treatment
  - Tests for all error-type combinations
  References: freellmapi#417, freellmapi#422

fix(google): strip x-* vendor extensions from Gemini tool schemas
  - Recursive x-* key stripping in openai_compat.py
  - Preserves real property names (e.g. x-user-id)
  - Tests for x-google-enum-descriptions, nested schemas
  References: freellmapi#417, freellmapi#420

fix(proxy): normalize streaming delta.content array to string
  - Array content → concatenated text in _stream_utils.py
  - Tests for array, null, nested array cases
  References: freellmapi#166

fix(proxy): tolerate code-agent replay payloads
  - Accept null/empty assistant content with tool_calls
  - Accept function-role messages
  - Accept id-less tool calls
  - Tests for all agent replay scenarios
  References: freellmapi#165, freellmapi#200, freellmapi#217

fix(router): fail over on non-retryable provider errors (403, 410, tool failures)
  - 403/410 → skip model, continue chain
  - Groq tool_use_failed → structured rescue
  - Tests for each error type
  References: freellmapi#337, freellmapi#339, freellmapi#168, freellmapi#291

feat(routing): per-provider aggregate rate limits
  - Provider-scoped usage tracking in key_store.py
  - Aggregate check before key selection in rotator.py
  - Tests for cross-key limits
  References: freellmapi#162

feat(routing): context-aware model selection
  - Token estimation before key selection
  - Skip models with insufficient context window
  - Tests for context-based filtering
  References: freellmapi#167

fix(google): correct validateKey error taxonomy
  - Separate auth errors from quota/access errors
  - Prevent valid keys from being auto-disabled
  - Tests for error classification
  References: freellmapi#268, freellmapi#285

feat(observability): chronological fallback logging
  - Structured log for each fallback attempt
  - Log reason, provider, model, latency
  - Tests for log output format
  References: freellmapi#305, freellmapi#313

feat(routing): per-request strategy selection via model field
  - Support auto:smart, auto:fast, auto:cheap model formats
  - Strategy overriding quality tier
  - Tests for each strategy
  References: freellmapi#122

feat(routing): analytics-driven bandit routing
  - Multi-armed bandit with Thompson sampling
  - Weighted axes (speed, cost, reliability)
  - Explore/exploit balance
  - Tests for convergence and cold start
  References: freellmapi#163

feat(core): key system-prompt binding
  - Store optional system prompt per key
  - Inject before request dispatch
  - Tests for prompt injection
  References: freellmapi#388, freellmapi#411

fix(ratelimit): NULL-limit escalation via hit-count heuristic
  - Estimate provider limits from actual usage
  - Apply heuristic caps for NULL rpd/tpd providers
  - Tests for estimation accuracy
  References: freellmapi#392

docs: add freellmapi-to-llm-apipool-map.md and perfection-blueprint.md
  - Exhaustive mapping of all 288 freellmapi items
  - ADRs for each architectural decision
  This commit
```

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Regression in existing proxy behavior | Medium | High | Full test suite + manual proxy smoke test |
| Outbound proxy breaks existing connections | Low | High | Proxy resolution is opt-in; no change to default behavior |
| Bandit routing conflicts with tier-based routing | Medium | Medium | Bandit is a separate strategy; tier routing unchanged |
| AES-256-GCM authTag change breaks existing encrypted data | Low | Critical | Verify backward compatibility; migration path if needed |
| Per-provider rate limits double-count with per-key limits | Medium | Medium | Provider limits are additional check, not replacement |

---

## Post-Implementation Verification

After all changes are implemented, run:

```bash
# Full test suite
pytest -xvs --cov=llm_apipool

# Type check
mypy llm_apipool

# Lint
ruff check .
ruff format --check .

# Security scan
bandit -r llm_apipool -x tests

# Manual proxy smoke test
llm-apipool proxy --port 18000 &
curl -s http://localhost:18000/health | jq .
kill %1
```

---

**Next:** Begin Phase 2 implementation — Wave 1 (Critical Bug Fixes) first, then Wave 2 (High-Priority Features), then Wave 3 (Medium-Priority Improvements).
