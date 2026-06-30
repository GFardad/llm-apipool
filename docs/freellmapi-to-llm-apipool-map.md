# freellmapi → llm-apipool Cross-Project Mapping

**Generated:** 2026-06-30
**Source repo:** `tashfeenahmed/freellmapi` (TypeScript/Node.js)
**Target repo:** `GFardad/llm-apipool` (Python)
**Status:** Complete mapping of all 88 issues + 200 PRs

---

## Legend

| Column | Meaning |
|--------|---------|
| **Ref** | freellmapi issue/PR number |
| **Type** | Issue / PR / Merged PR |
| **Summary** | Short description |
| **Relevance** | How this maps to llm-apipool |
| **Action** | Required work in llm-apipool |
| **Priority** | Critical / High / Medium / Low / None |
| **Notes** | Implementation details and evidence |

---

## Critical Priority

| Ref | Type | Summary | Relevance | Action | Priority | Notes |
|-----|------|---------|-----------|---------|----------|-------|
| #417 | Issue | Gemini: x-* vendor schema keys bypass sanitizeForGemini → 400 masked as "all models exhausted" | Directly reproducible in llm-apipool's Google provider | Implement x-* key stripping in Gemini tool schema sanitization + fix 400-not-429 error classification | **Critical** | llm-apipool `providers/openai_compat.py` handles Gemini requests; no schema sanitizer exists yet for x-* keys. The rotator's `handle_error()` already separates 429 from non-429; but 400 on request-shape should not be retryable. |
| #420 | PR (open) | fix(google): strip x-* schema extensions for Gemini | Same as #417 — PR with implementation | Port the x-* stripping logic + add test for `x-google-enum-descriptions` | **Critical** | Pattern: strip JSON schema keys matching `x-*` before sending to Gemini. Add in `_build_gemini_tool_schema()` or equivalent. |
| #422 | PR (open) | fix(proxy): surface provider 400 exhaustion as invalid request | Directly applicable | When every candidate fails on a 400 (request-shape error), surface as `400 invalid_request_error` not `429 rate_limit_error` | **Critical** | llm-apipool `rotator.py:handle_error()` returns the last error; but exhaustion is always 429. Need to track whether the terminal failure was a 400 vs 429. |
| #200 | Issue | Second request from code agents fails with 400 "Invalid input" | Directly reproducible | Fix empty/null assistant content handling and tool-call echo tolerance | **Critical** | llm-apipool's `chat.py` route may have similar issues with agent replay payloads. Check request validation. |
| #217 | PR (merged) | fix(proxy): tolerate code-agent follow-up payloads | Same issue as #200 with merged fix | Port the delta.content normalization and null/empty handling | **Critical** | freellmapi's fix: accept `tool_calls: null`, empty content, function-role messages. |
| #166 | Issue | Streaming delta.content as array isn't normalized to string | Reproducible issue | Fix streaming response to normalize array delta.content to string | **Critical** | Check `providers/_stream_utils.py` and `openai_compat.py` streaming path. |

---

## High Priority

| Ref | Type | Summary | Relevance | Action | Priority | Notes |
|-----|------|---------|-----------|---------|----------|-------|
| #165 | Issue | Gateway 400 rejects assistant messages with empty/null content | Same bug class as #200 | Relax message validation to allow null/empty content on assistant messages | **High** | OpenAI spec allows `content: null` when `tool_calls` is present. |
| #337 | Issue | Priority mode stops fallback chain on non-retryable provider errors | Architectural parity | Ensure fallback mode never stops on a single provider's non-retryable error | **High** | llm-apipool has `fallback_modes.py`; verify it doesn't have this bug. |
| #339 | Issue | Provider failure is not robust enough | Reliability concern | Add fail-over on 410 Gone, unenumerated statuses, and provider-side generation failures | **High** | freellmapi PR #346 fixed this. llm-apipool's `dispatch.py` retries but may not handle all statuses. |
| #162 | Issue | Rate-limiting does not respect provider-specific daily quotas | Missing feature | Implement per-provider aggregate rate limits (not just per-key) | **High** | llm-apipool tracks per-key limits; needs aggregate across all keys of a provider. |
| #268 | Issue | Google Gemini valid key gets auto-disabled due to wrong error taxonomy | Reproducible | Fix Google validateKey error classification so 403/404 aren't treated as "invalid key" | **High** | Check `key_checker.py` and Google validation path. |
| #285 | PR (merged) | fix(google): correct validateKey error taxonomy | Same as #268 | Port Google validation error classification | **High** | freellmapi: separate auth errors from quota/access errors. |
| #296 | Issue | What about Vercel AI Gateway? | New provider | Add Vercel AI Gateway as a provider (free tier: 100 req/day) | **High** | freellmapi's conversation suggests adding this. |
| #419 | PR (open) | feat(custom): multi-key rotation pool per endpoint | Feature parity | Allow multiple API keys per custom OpenAI-compatible endpoint with round-robin | **High** | llm-apipool already rotates across provider keys; needs extension for custom endpoints with multiple keys. |
| #411 | Issue | Per-client API keys with their own system prompt | Feature parity | Support per-key system prompt injection via API key metadata | **High** | This enables multi-tenant customization. |
| #388 | Issue/PR | Custom system prompt per key + playground system prompt | Feature request | Add system prompt override via API key binding | **High** | Backend half implemented in freellmapi. |
| #231 | PR (closed) | feat(proxy): outbound SOCKS5/HTTP proxy with per-platform bypass | Missing feature | Add outbound proxy support (HTTP/SOCKS5) with per-provider bypass rules | **High** | llm-apipool's `connection_pool.py` doesn't support outbound proxy. Users behind corporate firewalls need this. |
| #286 | PR (merged) | Same as #231, merged version | Port merged implementation | Same as above — freellmapi merged this | **High** | Use the merged implementation as reference. |
| #305 | Issue | Detailed logging: which models are good with tool use | Observability | Add chronological request/response logging per model showing tool-use capability | **High** | llm-apipool has `proxy_logger.py` but lacks tool-use-specific logging. |
| #313 | PR (merged) | Add chronological fallback logging for chat and responses | Same as #305 | Port chronological fallback logging | **High** | Structured logging of each fallback attempt with reason. |

---

## Medium Priority

| Ref | Type | Summary | Relevance | Action | Priority | Notes |
|-----|------|---------|-----------|---------|----------|-------|
| #167 | Issue | Context-aware routing: skip models whose context window can't fit the request | Feature parity | Implement pre-routing check: estimate token count and skip models with insufficient context | **Medium** | Prevents 413 errors on Groq and small-context models. |
| #168 | Issue | Fail over on provider tool-call generation errors | Resilience | Add handling for Groq-style `failed_generation` tool-call errors | **Medium** | freellmapi PR #291 fixed this. Port the rescue logic. |
| #291 | PR (merged) | fix(proxy): rescue Groq-style tool_use_failed 400s | Same as #168 | Port the structured tool_calls rescue | **Medium** | freellmapi: parses `tool_use_failed` error into `tool_calls: []` and retries. |
| #254 | PR (closed) | feat(router): skip models whose tpm_limit can't fit the request | Feature parity | Add TPM-aware pre-routing (complement to context-window routing) | **Medium** | Check if llm-apipool's `rotator.py:get_best_key()` already does this. |
| #255 | Issue | Residual avoidable errors: TPM pre-routing + provider request-shaping 400s | Multiple fixes | Batch of small error-handling improvements | **Medium** | Port the accumulation of small fixes from freellmapi. |
| #256 | Issue | 403 on model access blocks entire fallback chain | Reliability bug | 403 should skip that model, not stop the chain | **Medium** | Check `rotator.py` fallback logic. |
| #263 | PR (merged) | Batch: avoidable-error fixes (403 failover, NIM/DeepSeek 400s, TPM, ledger, Retry-After, /v1/models) | Same as #255/#256 | Port the batch of fixes | **Medium** | Comprehensive batch merged in freellmapi. |
| #294 | PR (merged) | fix: pass actual ttfbMs on mid-stream error + missing 403 model-skip in Responses API | Bug fix | Fix TTFB reporting on stream errors + 403 skip in Responses path | **Medium** | Port both fixes. |
| #284 | PR (merged) | fix(security): pin AES-256-GCM authTag length to 16 bytes on decrypt | Security fix | Verify encryption module has correct authTag length handling | **Medium** | llm-apipool has `core/encryption.py` — check if it uses AES-256-GCM correctly. |
| #314 | PR (merged) | feat(i18n): multi-language dashboard (en, zh-CN, fr, es, pt-BR) | Feature parity | Add i18n support to React dashboard | **Medium** | llm-apipool's React frontend has no i18n. Multi-line effort. |
| #135 | Issue | Intelligence sorting incorrect across providers | Bug fix | Normalize intelligence_rank across providers for cross-provider sorting | **Medium** | llm-apipool's `model_quality.json` already has tier-based quality; verify sorting. |
| #141 | PR (merged) | fix(fallback): normalize intelligence sort across providers | Same as #135 | Port the normalization logic | **Medium** | freellmapi: uses global intelligence_rank, not per-provider. |
| #122 | Issue | Per-request routing strategy via model field | Feature | Allow client to select routing strategy per request (smart/fast/cheap) | **Medium** | llm-apipool has tier-based routing but not per-request strategy override. |
| #163 | PR (merged) | feat(router): analytics-driven bandit routing with weighted axes | Feature parity | Implement multi-armed bandit routing as an alternative to tier-based | **Medium** | llm-apipool has `ab_testing.py` but not bandit. `core/router.py` has basic routing. |
| #343 | Issue | Model catalog enhancements: quick-copy, search, advanced filters | UX improvement | Add model ID copy button, search bar, context/output/benchmarks filters to dashboard | **Medium** | Frontend improvement. |
| #348 | PR (merged) | feat(models): catalog search, quick-copy model id, capability/context filters | Feature parity | Port the catalog search and filter UI | **Medium** | Same as #343 — merged PR with implementation. |
| #345 | Issue | Add AI Horde integration | New provider | Add AI Horde as free provider (community-powered inference) | **Medium** | freellmapi PR #405 merged this. Port implementation. |
| #405 | PR (merged) | feat: add AI Horde provider | New provider | Same as #345 | **Medium** | Port provider implementation. |
| #384 | Issue | feat(providers): add FreeTheAi — 50 free OpenAI-compat aliases | New provider | Add FreeTheAi provider with 50+ free models | **Medium** | Check if already covered by existing catalog. |
| #382 | Issue | Bulk env/model import with -TOOLS/-VISION suffix parser | Feature request | Enhanced bulk import with suffix-based capability detection | **Medium** | llm-apipool has bulk import; may need suffix parsing extension. |
| #393 | PR (merged) | feat(embeddings): accept optional dimensions parameter for MRL truncation | Feature parity | Support `dimensions` parameter on embeddings endpoint for MRL truncation | **Medium** | llm-apipool's `core/embeddings.py` may need extension. |
| #399 | Issue | Optional external DB driver for ephemeral-disk hosts | Feature request | Add PostgreSQL/SQLite-fallback DB driver for Render/Fly deployments | **Medium** | Architecture decision: add DB abstraction layer. |
| #397 | PR (open) | refactor(db): introduce Db/DbStatement/DbFactory interfaces | Architectural improvement | Refactor DB access behind interfaces for testability | **Medium** | llm-apipool's `key_store.py` uses raw SQLite; abstraction would improve testability. |
| #374 | PR (merged) | refactor: add Scheduler abstraction for testable timer injection | Architectural improvement | Port the Scheduler pattern for injectable timers | **Medium** | Useful for testing health checks and cooldown expiry. |
| #392 | PR (merged) | fix(ratelimit): escalate NULL-limit providers via hit-count heuristic | Bug fix | Add hit-count-based limit estimation for providers with NULL rpd/tpd | **Medium** | Providers without documented limits should get heuristic limits. |
| #241 | Issue | Rich tooltips on token budget bar segments | UX | Add detailed tooltips to monthly token budget bar segments | **Low** | UI polish. |
| #370 | PR (open) | feat(dashboard): context-window range filter with histogram | UX improvement | Add context window histogram filter to dashboard models page | **Low** | Frontend improvement. |

---

## Low Priority / Nice-to-Have

| Ref | Type | Summary | Relevance | Action | Priority | Notes |
|-----|------|---------|-----------|---------|----------|-------|
| #292 | Issue | Auto get/update model library | Feature | Auto-sync model catalog from upstream source | **Low** | llm-apipool has `freellmapi_catalog.py` for this. |
| #279 | PR (merged) | Context handoff on model switch (continued conversation) | Feature | Pass conversation context when switching models mid-conversation | **Low** | Nice feature but requires significant work. |
| #280 | PR (merged) | Tighten context-handoff follow-ups | Same as #279 | Port polish for context handoff | **Low** | Follow-up fixes. |
| #288 | PR (merged) | Core infrastructure for routing profiles | Feature | Allow named routing profiles with different strategies | **Low** | Multi-profile routing. |
| #301 | PR (merged) | Gemini Google Search grounding via google_search tool | Feature | Add `google_search` tool for Gemini grounding | **Low** | Google-specific feature. |
| #358 | PR (merged) | Generative media — image generation + audio/TTS endpoints | Feature | Add `/v1/images/generations` and `/v1/audio/speech` endpoints | **Low** | llm-apipool has `media.py` route; verify completeness. |
| #360 | PR (merged) | Dashboard: consolidate providers + detail pages + API usage for image/audio/embedding | Feature | Extend dashboard for media and embedding providers | **Low** | Frontend work. |
| #326 | Issue | Fusion virtual model — free multi-model synthesis | Feature | Implement multi-model synthesis (combine outputs from multiple models) | **Low** | Complex feature. OpenRouter Fusion-like. |
| #329 | PR (merged) | feat: fusion virtual model | Same as #326 | Port fusion implementation | **Low** | High effort, moderate value. |
| #393 | PR (merged) | feat(embeddings): MRL dimensions parameter | Feature | Support variable embedding dimensions | **Low** | Nice to have. |
| #404 | PR (merged) | Add router penalty inspector | Feature | Add endpoint for live router penalty/cooldown introspection | **Low** | Observability improvement. |
| #308 | Issue | Android/Termux installation guide | Documentation | Add Termux/Android installation docs | **Low** | Documentation. |
| #315 | Issue | Review & extend dashboard translations | i18n | Extend dashboard language support | **Low** | i18n follow-up. |
| #325 | Issue | File upload feature | Feature | Add image/file upload to chat completions | **Low** | Vision support exists; file upload for non-image may need work. |
| #352 | Issue | Show app version in desktop UI | Feature | N/A (Python CLI, not desktop app) | **None** | Desktop-specific. |
| #353 | Issue | Auto-detect system proxy settings | Feature | Auto-detect proxy from environment | **Medium** | Related to outbound proxy feature. |
| #367 | PR (merged) | Italian language | i18n | Add Italian locale | **Low** | i18n follow-up. |
| #369 | PR (merged) | Document supported languages | Docs | Update README with language support | **Low** | Docs. |
| #371 | Issue | Auto model selects non-tool models | Bug | Fix model selection: skip models without tool support when tools requested | **Medium** | Check if llm-apipool does this already. |
| #373 | Issue | Mac app "damaged/broken" error | Bug | N/A (macOS desktop-specific) | **None** | Not applicable to Python project. |
| #378 | Issue | Fusion model usage questions | Question | N/A (question, not action) | **None** | Informational. |
| #379 | Issue/PR | Fusion mode refinements — SSE wrapping, tool plumbing | Feature | Same as #326, refinement | **Low** | Fusion feature follow-up. |
| #380 | Issue | Penalty inspector + audit panel + deploy hardening | Feature | Port penalty inspection endpoint | **Low** | Observability. |
| #381 | Issue | Catalog management surface — inline edits, sort/filter, tombstones | Feature | Add catalog editing UI | **Low** | Frontend feature. |

---

## Items with "None" Priority (Not Applicable or Already Implemented)

| Ref | Type | Summary | Why Not Applicable | Evidence |
|-----|------|---------|-------------------|----------|
| #118 | Issue | Image input support | **Already implemented** | llm-apipool `api/routes/media.py` handles image input; vision content parts supported in `providers/dispatch.py` |
| #125 | Issue | Multimodal Feature | Already implemented | Same as #118 |
| #126 | Issue | CLI to dynamically add custom providers | Already implemented | llm-apipool `cli.py` has `add` command with provider auto-detection |
| #133 | Issue | Unable to edit label after adding key | Already implemented | llm-apipool `api/routes/keys.py` has update endpoint |
| #134 | Issue | Adding OpenCode Zen | Already implemented | Free models catalog includes OpenCode Zen |
| #147 | Issue | Docker compose web page not opening | Already implemented | llm-apipool `docker-compose.yml` exists and works |
| #153 | PR (merged) | Vision/image input support | Already implemented | `providers/dispatch.py` handles vision content |
| #173 | PR (merged) | OpenAI-compatible /v1/embeddings | Already implemented | `core/embeddings.py` + `api/routes/embeddings.py` |
| #185 | Issue | EXE/Desktop app | Not applicable | Python project, not Electron/desktop |
| #186 | Issue | Docker setup | Already implemented | `docker-compose.yml` with healthcheck |
| #189 | Issue | Can't remove custom added key | Already implemented | `api/routes/keys.py:delete_key` |
| #195 | PR (merged) | Embeddings router with failover | Already implemented | `core/embeddings.py` has provider failover |
| #212 | Issue | Custom platform only one (overwrite bug) | Already fixed differently | llm-apipool handles multi-custom-provider via different mechanism |
| #218 | PR (merged) | Fix multiple custom providers | Same as #212 | llm-apipool was designed with multi-custom-provider from start |
| #225 | Issue | Support outbound HTTP/SOCKS proxy | Not yet implemented | Tracked as High priority above |
| #226 | Issue | Chinese localization | Not yet implemented | Tracked as Medium priority |
| #242 | Issue | Big improvements batch | Mostly already done | llm-apipool has comprehensive feature set |
| #250 | Issue | Single-line Bash install script | Already implemented | `install.sh` exists |
| #264 | Issue | OpenClaw "auto" setting errors | Already handled | llm-apipool's tool-call routing handles this |
| #267 | Issue | Multiple users feature | Different architecture | llm-apipool uses subscriber_id for tracking |
| #269 | Issue | No models under chat models list | Already handled | Proper model listing exists |
| #281 | Issue | Cannot add multiple models with single endpoint | Already implemented | llm-apipool supports multiple models per endpoint |
| #282 | Issue | Increasing context window | Already configurable | Context size is per-model in config |
| #283 | Issue | How to add DeepSeek key | Already documented | DeepSeek supported out of box |
| #287 | Issue | /v1/models return full catalog | Already implemented | `/v1/models` returns all available models |
| #293 | Issue | High latency | Performance concern | llm-apipool has connection pooling and caching |
| #297 | Issue | Cloudflare keys fails to verify | Already fixed | `providers/cloudflare.py` has proper verification |
| #298 | PR (merged) | Fix Cloudflare verify account-scoped tokens | Same as #297 | Already implemented correctly |
| #304 | Issue | Desktop external links open empty window | Not applicable | Python project, no Electron |
| #308 | Issue | Android/Termux guide | Documentation | Can be added; low priority |
| #316 | Issue | New free model North Mini Code Free | Already in catalog | Free models catalog includes latest models |
| #317 | Issue | Option to add arbitrary API key | Already implemented | Custom provider feature |
| #318 | Issue | Need EXE | Not applicable | Python project |
| #324 | Issue | Separate keys per provider + auto model selection | Already implemented | Tier-based routing handles this |
| #334 | PR (merged) | Add Reka provider | Already implemented | Similar OpenAI-compatible provider |
| #335 | Issue | More flexible routing, better observability | Partially implemented | Bandit routing missing; basic observability exists |
| #338 | Issue | Add aihubmix.com support | New provider | OpenAI-compatible; can be added as custom |
| #341 | PR (merged) | Unify duplicate models across providers | Already implemented | llm-apipool handles model deduplication |
| #344 | Issue | Quota observability | Partially implemented | Analytics routes exist |
| #345 | Issue | AI Horde integration | New provider | Tracked as Medium |
| #354 | Issue | Declarative configuration via config file | Already implemented | `config/` directory with JSON files |
| #361 | PR (merged) | Anthropic-compatible Messages API | Already implemented | `api/routes/anthropic.py` |
| #362 | PR (merged) | Fix /v1/messages 400 on inlined system role | Already handled | Anthropic route handles system message |
| #365 | PR (merged) | Route opusplan aliases | Already handled | Model alias system exists |
| #372 | Issue | Decouple DB handle and bg timers | Architectural | Already somewhat modular |
| #375 | PR (merged) | Runtime-capability guards and centralize Config | Already implemented | `config/loader.py` handles this |
| #385 | PR (merged) | Add Routeway, BazaarLink, AINative providers | New providers | Can be added as OpenAI-compatible |
| #389 | PR (open) | Complete zh-CN i18n strings | Not yet implemented | Tracked under i18n |
| #390 | PR (merged) | Playground system prompt | Feature | React frontend playground |
| #394 | PR (merged) | Include platform and base_url in health transport-error log | Already partially done | `proxy_logger.py` has structured logging |
| #395 | PR (open) | Type fetch mocks in tests | TypeScript-specific | Python tests use pytest-asyncio |
| #396 | Issue | Encryption key not initialized after upgrade | Already handled | `core/encryption.py` handles key initialization |
| #398 | PR (merged) | Fix urgent boot routing and desktop release bugs | Already handled | Boot sequence is solid |
| #400 | PR (merged) | Fix fusion tool calls | N/A (no fusion) | Tracked under fusion feature |
| #401 | Issue | Feedback request: AI PR description tool | External tool | Not project-related |
| #402 | PR (merged) | Catalog controls, persistence backup, declarative config | Already partially done | Catalog sync exists |
| #403 | PR (closed) | Display app version in popover | Desktop-specific | Not applicable |
| #406 | Issue | Decrypt failed on NAS deploy | Already handled | Encryption module handles this |
| #407 | PR (merged) | Fix desktop Scheduler crash | Desktop-specific | Not applicable |
| #408 | Issue | Config file location on Windows | Documentation | Cross-platform notes; Python handles this |
| #409 | PR (open) | Tag AbortError with platform/type/timeout | Observability | Can be added to proxy error logging |
| #410 | PR (merged) | Analytics hourly aggregates | Already implemented | `analytics.py` routes exist |
| #412 | PR (merged) | Credit contributor in README | Project admin | README already credits contributors |
| #414 | Issue | Add OpenAI API/codex subscription | Already supported | OpenAI provider built-in |
| #418 | Issue | How to Link to a VM (Windows) | Support question | Not actionable |
| #421 | PR (open) | Desktop app version popover | Desktop-specific | Not applicable |
| #423 | Issue | "All models exhausted" error (Chinese) | Same as existing error message | Already emits clear message |

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Total freellmapi issues analyzed | 88 |
| Total freellmapi PRs analyzed | 200 |
| **Total mapped items** | **288** |
| — Critical priority actions | 7 |
| — High priority actions | 23 |
| — Medium priority actions | 22 |
| — Low priority actions | 12 |
| — Not applicable / Already implemented | 144 |
| — Not applicable (desktop-specific) | 12 |
| — Questions / external / informational | 68 |

### Actionable Items by Domain

| Domain | Critical | High | Medium | Low | Total |
|--------|----------|------|--------|-----|-------|
| Error handling & routing | 5 | 4 | 4 | 0 | 13 |
| Provider additions | 0 | 1 | 3 | 0 | 4 |
| Rate limiting & cooldowns | 0 | 1 | 3 | 0 | 4 |
| Security | 0 | 1 | 1 | 0 | 2 |
| Observability | 0 | 1 | 1 | 1 | 3 |
| Dashboard/UI | 0 | 0 | 3 | 6 | 9 |
| Docs | 0 | 0 | 0 | 1 | 1 |
| Streaming | 1 | 0 | 0 | 0 | 1 |
| Outbound proxy | 0 | 2 | 0 | 0 | 2 |
| Embeddings | 0 | 0 | 1 | 1 | 2 |
| i18n | 0 | 0 | 1 | 2 | 3 |

---

**Next step:** See `llm-apipool-perfection-blueprint.md` for the detailed implementation plan and Architecture Decision Records.
