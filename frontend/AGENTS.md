# FRONTEND KNOWLEDGE BASE

**Stack:** React 18 + Vite + TypeScript + Tailwind CSS + Radix UI
**Purpose:** Dashboard UI for llm-keypool — key management, live testing, and proxy monitoring.

## OVERVIEW

Single-page React app that talks exclusively to the Python FastAPI backend at `http://localhost:8000`.
All LLM interaction goes through the proxy; this UI never calls external APIs directly.

## STRUCTURE

```
frontend/
├── src/
│   ├── main.tsx          # React root, mounts <App />
│   ├── KeyManager.tsx    # Key CRUD: list, import, deactivate, filter by provider
│   └── TestConsole.tsx   # Live chat console wired to /v1/chat/completions
├── index.html            # Vite entry point
├── vite.config.ts        # Proxy rule: /v1/* and /api/* → localhost:8000
├── tailwind.config.js    # Theme tokens (extend here, not inline)
└── tsconfig.json         # Strict mode enabled |
```

## WHERE TO LOOK

| Task | File | Notes |
|------|------|-------|
| Key list / import / deactivate | `KeyManager.tsx` | Axios calls to `/api/keys` |
| Live model testing | `TestConsole.tsx` | Test prompts via `/v1/chat/completions` using axios (non-streaming) |
| App shell | `main.tsx` | React root, mounts KeyManager and TestConsole components |
| Backend proxy config | `vite.config.ts` | Dev-only; production must set `VITE_API_BASE` env var |
| Shared UI primitives | Radix UI imports | Dialog, Select, Tabs — import from `@radix-ui/react-*` |
| Styling tokens | `tailwind.config.js` | Extend theme here; avoid arbitrary `[]` values in JSX |

## CONVENTIONS

- **API calls:** Axios for all REST endpoints (`/api/*` and `/v1/*`). Streaming support can be added via native `fetch` with `ReadableStream` if needed.
- **State:** Component-local `useState`/`useReducer` only — no global store. Lift state to `main.tsx` when two siblings need it.
- **Types:** Define request/response shapes inline in the component file that owns the call; no separate `types/` directory yet.
- **Tailwind:** Utility classes in JSX; extract to a `clsx()` helper call when a class list exceeds ~6 tokens. Never use `style={{}}` for values that have a Tailwind equivalent.
- **Radix UI:** Use unstyled Radix primitives and apply Tailwind classes directly — do not import Radix themes or pre-built component libraries.
- **Error handling:** Surface API errors in-component via a local `error` state string rendered near the triggering control. Do not use `alert()` or `console.error()` as the sole feedback.
- **No test files exist yet** — when adding tests, use Vitest (bundled with Vite) and React Testing Library.
- **Backend contract:** Key objects carry `provider`, `key_preview`, `capabilities[]`, and `is_active`. The proxy model alias is `LLM-Keypool` (see parent AGENTS.md).

## ANTI-PATTERNS

- Do not hardcode `http://localhost:8000` in component files — use the Vite proxy in dev and `import.meta.env.VITE_API_BASE` in production.
- Do not import from `tailwind.config.ts` at runtime — tokens are compile-time only.
- Do not add a router until there are more than three top-level views; current tab-switching via `useState` is intentional.