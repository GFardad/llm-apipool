"""Textual TUI for llm-keypool."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from llm_keypool.key_checker import detect_provider_sync
from llm_keypool.key_store import KeyStore

_CONFIG_PATH = Path(__file__).parent / "config" / "providers.json"

KNOWN_CAPABILITIES = [
    "general_purpose",
    "agentic",
    "fast",
    "code",
    "vision",
    "large_context",
]


def _load_providers() -> dict[str, Any]:
    try:
        with _CONFIG_PATH.open() as f:
            return json.load(f)["providers"]  # type: ignore[no-any-return]
    except FileNotFoundError:
        msg = f"Provider config not found: {_CONFIG_PATH}"
        raise RuntimeError(msg) from None
    except (json.JSONDecodeError, KeyError) as e:
        msg = f"Invalid provider config: {e}"
        raise RuntimeError(msg) from e


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


MIN_KEY_LENGTH = 4
MASK_KEY_MIN_LENGTH = 8

KEY_PREFIX_MAP: dict[str, str] = {
    "gsk_": "groq",
    "sk-": "openai",
    "cs_": "cerebras",
    "mi_": "mistral",
    "AIza": "google",
    "hf_": "huggingface_router",
    "or_": "openrouter",
    "cohere_": "cohere",
    "cf-": "cloudflare",
}


def _mask_key_display(api_key: str) -> str:
    """Mask an API key for safe display: show first 4 and last 4 chars."""
    if len(api_key) <= MASK_KEY_MIN_LENGTH:
        return "****"
    return api_key[:4] + "****" + api_key[-4:]


def _detect_provider_from_key(api_key: str) -> str | None:
    """Detect provider from API key prefix using the prefix map."""
    for prefix, provider in KEY_PREFIX_MAP.items():
        if api_key.startswith(prefix):
            return provider
    return None


def _normalize_import_capabilities(caps: Any) -> list[str]:
    if caps is None or not isinstance(caps, (str, list)):
        return ["general_purpose"]
    if isinstance(caps, str):
        return [c.strip() for c in caps.split(",") if c.strip()]
    return [str(c) for c in caps]


def _resolve_provider_by_checking(
    key: str,
    timeout: float,
    max_concurrent: int,
) -> tuple[str, bool, str, int]:
    results = detect_provider_sync(key, timeout=timeout, max_concurrent=max_concurrent)
    for provider, success, detail in results:
        if success:
            return provider, True, detail, len(results)
    return "", False, "; ".join(f"{p}: {d}" for p, _, d in results[:3]), len(results)


async def _resolve_provider_by_checking_async(
    key: str,
    timeout: float,
    max_concurrent: int,
) -> tuple[str, bool, str, int]:
    results = await asyncio.to_thread(
        detect_provider_sync,
        key,
        None,
        timeout,
        max_concurrent,
    )
    for provider, success, detail in results:
        if success:
            return provider, True, detail, len(results)
    return "", False, "; ".join(f"{p}: {d}" for p, _, d in results[:3]), len(results)


async def _detect_unknown_provider_overrides(
    lines: list[str],
    configs: dict[str, Any],
    timeout: float,
    max_concurrent: int,
) -> tuple[dict[str, str], dict[str, str]]:
    overrides: dict[str, str] = {}
    errors: dict[str, str] = {}

    for raw_line in lines:
        parsed = _parse_import_entry(raw_line, configs)
        if parsed is None or "_error" in parsed:
            continue

        key = str(parsed["key"])
        provider: str | None = parsed.get("provider")
        if not provider:
            provider = _detect_provider_from_key(key)
        if provider or not key or len(key) < MIN_KEY_LENGTH:
            continue

        detected, success, detail, checked = await _resolve_provider_by_checking_async(
            key,
            timeout,
            max_concurrent,
        )
        if success:
            overrides[key] = detected
        else:
            errors[key] = (
                f"Cannot detect provider after checking {checked} provider(s): {detail}"
            )

    return overrides, errors


def _parse_import_entry(line: str, configs: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a single line from an import file into an entry dict.

    Returns None for empty lines, comments, and block separators.
    Returns a dict with ``_error`` on parse failure.
    Returns a normalised entry dict on success.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped == "---":
        return None

    # NDJSON format (each line is a JSON object)
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as e:
            return {"_error": f"Invalid JSON: {e}"}
        if "key" not in data:
            return {"_error": "NDJSON entry missing 'key' field"}
        return {
            "key": str(data["key"]),
            "provider": data.get("provider"),
            "capabilities": data.get("capabilities"),
            "model": data.get("model"),
            "base_url": data.get("base_url"),
        }

    # provider:key format (e.g. "groq:gsk_...")
    if ":" in stripped:
        provider_candidate, _, rest = stripped.partition(":")
        provider_candidate = provider_candidate.strip().lower()
        if provider_candidate in configs:
            return {
                "key": rest.strip(),
                "provider": provider_candidate,
                "capabilities": None,
                "model": None,
                "base_url": None,
            }

    # Key-per-line format (fallback)
    return {
        "key": stripped,
        "provider": None,
        "capabilities": None,
        "model": None,
        "base_url": None,
    }


def _resolve_import_entries(
    lines: list[str],
    configs: dict[str, Any],
    check_providers: bool = False,  # noqa: FBT001
    check_timeout: float = 8.0,
    check_concurrency: int = 6,
    provider_overrides: dict[str, str] | None = None,
    provider_check_errors: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Parse all lines and resolve providers.

    Returns (entries, errors) where entries are valid parsed entries
    and errors are (context, reason) tuples for skipped lines.
    """
    entries: list[dict[str, Any]] = []
    errors: list[tuple[str, str]] = []

    for i, raw_line in enumerate(lines, 1):
        parsed = _parse_import_entry(raw_line, configs)
        if parsed is None:
            continue
        if "_error" in parsed:
            errors.append((f"Line {i}", parsed["_error"]))
            continue

        key: str = parsed["key"]

        provider: str | None = parsed.get("provider")
        if not provider:
            provider = _detect_provider_from_key(key)

        if not provider:
            if provider_overrides and key in provider_overrides:
                provider = provider_overrides[key]
            elif provider_check_errors and key in provider_check_errors:
                errors.append((_mask_key_display(key), provider_check_errors[key]))
                continue
            elif check_providers:
                detected, success, detail, checked = _resolve_provider_by_checking(
                    key,
                    check_timeout,
                    check_concurrency,
                )
                if success:
                    provider = detected
                else:
                    errors.append(
                        (
                            _mask_key_display(key),
                            f"Cannot detect provider after checking {checked} provider(s): {detail}",
                        ),
                    )
                    continue
            else:
                errors.append((_mask_key_display(key), "Cannot detect provider from key prefix"))
                continue

        if provider not in configs:
            errors.append((_mask_key_display(key), f"Unknown provider '{provider}'"))
            continue

        if not key or len(key) < MIN_KEY_LENGTH:
            errors.append((_mask_key_display(key), f"Key too short (min {MIN_KEY_LENGTH} chars)"))
            continue

        caps = _normalize_import_capabilities(parsed.get("capabilities"))

        entries.append({
            "key": key,
            "provider": provider,
            "capabilities": caps,
            "model": parsed.get("model") or None,
            "base_url": parsed.get("base_url") or None,
        })

    return entries, errors


def _build_dry_run_text(entries: list[dict[str, Any]], errors: list[tuple[str, str]]) -> str:
    """Build dry-run output text showing what would be imported."""
    lines_out: list[str] = []
    if errors:
        lines_out.append(f"[yellow]Issues found ({len(errors)}):[/yellow]")
        for ctx, reason in errors:
            lines_out.append(f"  [yellow]⚠[/yellow] {ctx}: {reason}")

    if not entries:
        lines_out.append("[yellow]No valid keys to import.[/yellow]")
    else:
        lines_out.append(f"[bold]Dry-run:[/bold] {len(entries)} key(s) would be imported")
        for ent in entries:
            masked = _mask_key_display(ent["key"])
            caps_str = ", ".join(ent["capabilities"])
            lines_out.append(
                f"  [cyan]{ent['provider']:<14}[/cyan] {masked}  "
                f"[dim]{caps_str}[/dim]",
            )
    return "\n".join(lines_out)


def _build_warn_lines(errors: list[tuple[str, str]]) -> list[str]:
    """Build warning lines for skipped keys."""
    return [f"[yellow]Warning:[/yellow] {ctx}: {reason} - skipping" for ctx, reason in errors]


def _build_summary_text(
    entries: list[dict[str, Any]],
    parse_errors: list[tuple[str, str]],
    succeeded: int,
    failed: list[tuple[str, str, str]],
    warn_lines: list[str],
) -> str:
    """Build the import summary text."""
    total = len(entries) + len(parse_errors)
    summary_lines = [
        *warn_lines,
        "",
        "[bold]Import Summary:[/bold]",
        f"  Total parsed:  {total}",
        f"  [green]Registered: {succeeded}[/green]",
        f"  [yellow]Skipped:    {len(parse_errors)}[/yellow]",
        f"  [red]Failed:     {len(failed)}[/red]",
    ]

    if failed:
        summary_lines.append("")
        summary_lines.append("[yellow]Failed keys:[/yellow]")
        for masked, prov, reason in failed:
            summary_lines.append(f"  [red]✗[/red] {masked} ({prov}): {reason}")

    if parse_errors:
        summary_lines.append("")
        summary_lines.append("[yellow]Skipped keys (could not resolve):[/yellow]")
        for ctx, reason in parse_errors:
            summary_lines.append(f"  [yellow]⚠[/yellow] {ctx}: {reason}")

    return "\n".join(summary_lines)


CSS = """
Screen {
    overflow: hidden hidden;
    layout: vertical;
}

AppBanner {
    height: 8;
    background: $surface;
    color: $accent;
    text-align: center;
    overflow: hidden hidden;
    padding: 0 1;
}

TabbedContent {
    height: 1fr;
}

DataTable {
    height: 1fr;
}

#add-form {
    padding: 1 2;
    height: auto;
}

.form-row {
    height: 3;
    margin-bottom: 1;
}

.cap-row {
    height: auto;
    margin-bottom: 1;
}

.form-label {
    width: 20;
    padding: 1 0;
    color: $text-muted;
}

.form-input {
    width: 1fr;
}

.cap-checkboxes {
    layout: horizontal;
    height: auto;
    width: 1fr;
    padding: 0 1;
}

.cap-checkboxes Checkbox {
    margin-right: 2;
}

#status-msg {
    height: 1;
    margin: 1 0;
}

Button {
    margin-top: 1;
}

#import-form {
    padding: 1 2;
    height: auto;
}

#import-form Checkbox {
    margin: 1 0;
}

#import-status {
    height: auto;
    max-height: 15;
    overflow-y: auto;
    margin: 1 0;
    border: round $accent;
    padding: 1 2;
}

ConfirmScreen {
    align: center middle;
}

ConfirmScreen > Container {
    width: 50;
    height: 9;
    border: round $accent;
    background: $surface;
    padding: 1 2;
}

ConfirmScreen Label {
    margin-bottom: 1;
}

ConfirmScreen Horizontal {
    height: auto;
    align: center middle;
}

ConfirmScreen Button {
    margin: 0 1;
}

#audit-controls {
    height: 3;
    padding: 0 2;
}

#audit-table {
    height: 1fr;
}
"""

BANNER = (
    "██╗     ██╗     ███╗   ███╗   ██╗  ██╗███████╗██╗   ██╗██████╗  ██████╗  ██████╗ ██╗     \n"
    "██║     ██║     ████╗ ████║   ██║ ██╔╝██╔════╝╚██╗ ██╔╝██╔══██╗██╔═══██╗██╔═══██╗██║     \n"
    "██║     ██║     ██╔████╔██║   █████╔╝ █████╗   ╚████╔╝ ██████╔╝██║   ██║██║   ██║██║     \n"
    "██║     ██║     ██║╚██╔╝██║   ██╔═██╗ ██╔══╝    ╚██╔╝  ██╔═══╝ ██║   ██║██║   ██║██║     \n"
    "███████╗███████╗██║ ╚═╝ ██║   ██║  ██╗███████╗   ██║   ██║     ╚██████╔╝╚██████╔╝███████╗\n"
    "╚══════╝╚══════╝╚═╝     ╚═╝   ╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝      ╚═════╝  ╚═════╝ ╚══════╝\n"
    "Free-tier API key pool - rotate, cool down, keep going"
)


class AppBanner(Static):
    """Banner widget displayed at the top of the TUI."""


class ConfirmScreen(ModalScreen[bool]):
    """Modal screen for confirming destructive actions."""

    def __init__(self, message: str) -> None:
        """Initialize the confirm screen."""
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        """Create child widgets for the confirm screen."""
        with Container():
            yield Label(self._message)
            with Horizontal():
                yield Button("Confirm", variant="error", id="confirm")
                yield Button("Cancel", variant="default", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dismiss the screen with True if confirm was pressed."""
        self.dismiss(event.button.id == "confirm")


class LLMKeyPoolApp(App[None]):
    """Main TUI application for llm-keypool."""

    CSS = CSS
    TITLE = "llm-keypool"
    BINDINGS = [  # noqa: RUF012
        Binding("d", "deactivate_key", "Deactivate", show=True),
        Binding("c", "clear_cooldown", "Clear Cooldown", show=True),
        Binding("r", "refresh_keys",   "Refresh",        show=True),
        Binding("a", "refresh_audit",  "Refresh Audit",  show=True),
        Binding("q", "quit",           "Quit",           show=True),
    ]

    def __init__(self) -> None:
        """Initialize the TUI app."""
        super().__init__()
        self._store = KeyStore()
        self._providers = _load_providers()

    def compose(self) -> ComposeResult:
        """Create child widgets for the main app."""
        yield AppBanner(BANNER)
        with TabbedContent():
            with TabPane("Keys", id="tab-keys"):
                yield DataTable(id="keys-table", cursor_type="row")
            with TabPane("Add Key", id="tab-add"), Vertical(id="add-form"):
                with Horizontal(classes="form-row"):
                    yield Label("Provider", classes="form-label")
                    yield Select(
                        [(name, name) for name in sorted(self._providers.keys())],
                        id="inp-provider",
                        classes="form-input",
                        prompt="Select provider...",
                    )
                with Horizontal(classes="form-row"):
                    yield Label("API Key", classes="form-label")
                    yield Input(
                        placeholder="gsk_...",
                        id="inp-key",
                        classes="form-input",
                        password=True,
                    )
                with Horizontal(classes="cap-row"):
                    yield Label("Capabilities", classes="form-label")
                    with Horizontal(classes="cap-checkboxes"):
                        for cap in KNOWN_CAPABILITIES:
                            yield Checkbox(
                                cap,
                                value=(cap == "general_purpose"),
                                id=f"cap-{cap}",
                            )
                with Horizontal(classes="form-row"):
                    yield Label("Model (optional)", classes="form-label")
                    yield Input(
                        placeholder="leave blank for provider default",
                        id="inp-model",
                        classes="form-input",
                    )
                with Horizontal(classes="form-row"):
                    yield Label("Base URL (Override)", classes="form-label")
                    yield Input(
                        placeholder="leave blank to use provider default",
                        id="inp-base-url",
                        classes="form-input",
                    )
                yield Static("", id="status-msg")
                yield Button("Add Key", variant="success", id="btn-add")
            with TabPane("Audit", id="tab-audit"):
                with Horizontal(id="audit-controls"):
                    yield Label("Subscriber filter: ", id="audit-filter-label")
                    yield Input(placeholder="all subscribers", id="inp-audit-filter", classes="form-input")
                    yield Button("Refresh", variant="default", id="btn-audit-refresh")
                yield DataTable(id="audit-table", cursor_type="row")
            with TabPane("Import Keys", id="tab-import"), Vertical(id="import-form"):
                with Horizontal(classes="form-row"):
                    yield Label("Filename", classes="form-label")
                    yield Input(
                        placeholder="path/to/keys.txt",
                        id="inp-import-file",
                        classes="form-input",
                    )
                yield Checkbox(
                    "Dry run (show what would be imported)",
                    id="chk-import-dry-run",
                )
                yield Checkbox(
                    "Force import (continue on errors)",
                    id="chk-import-force",
                )
                yield Checkbox(
                    "Check unknown providers",
                    id="chk-import-check-providers",
                )
                yield Button("Import", variant="primary", id="btn-import-start")
                yield Static("", id="import-status")
        yield Footer()

    def on_mount(self) -> None:
        """Set up tables and load data after the app is mounted."""
        # keys table
        kt = self.query_one("#keys-table", DataTable)
        kt.add_columns("ID", "Provider", "Capabilities", "Model", "Active", "Req Today", "Cooldown Until")
        self._load_keys()
        # audit table
        at = self.query_one("#audit-table", DataTable)
        at.add_columns("Time", "Subscriber", "Provider", "Model", "Tok In", "Tok Out", "ms", "OK")
        self._load_audit()

    def _load_keys(self) -> None:
        table = self.query_one("#keys-table", DataTable)
        table.clear()
        now = _now_iso()
        for k in self._store.get_all_keys():
            in_cooldown = bool(k["cooldown_until"] and k["cooldown_until"] > now)
            caps = ", ".join(self._store.parse_capabilities(k))
            table.add_row(
                str(k["id"]),
                k["provider"],
                caps,
                k["model"] or "default",
                "yes" if k["is_active"] else "no",
                str(k["requests_today"]),
                k["cooldown_until"][:19] if in_cooldown else "-",
                key=str(k["id"]),
            )

    def _load_audit(self) -> None:
        table = self.query_one("#audit-table", DataTable)
        table.clear()
        try:
            filter_inp = self.query_one("#inp-audit-filter", Input)
            sub = filter_inp.value.strip() or None
        except Exception:  # noqa: BLE001
            # Widget might not be mounted yet during init
            sub = None
        rows = self._store.get_audit_log(subscriber_id=sub, days=7, limit=200)
        for r in rows:
            ok = "y" if r["success"] else "n"
            table.add_row(
                (r["ts"] or "")[:19],
                r["subscriber_id"] or "",
                r["provider"] or "",
                r["model"] or "",
                str(r["tokens_in"] or 0),
                str(r["tokens_out"] or 0),
                str(r["latency_ms"] or 0),
                ok,
            )

    def _selected_key_id(self) -> int | None:
        table = self.query_one("#keys-table", DataTable)
        if table.cursor_row < 0 or table.row_count == 0:
            return None
        row = table.get_row_at(table.cursor_row)
        try:
            return int(row[0])
        except (IndexError, ValueError):
            return None

    def action_refresh_keys(self) -> None:
        """Refresh the keys table."""
        self._load_keys()

    def action_refresh_audit(self) -> None:
        """Refresh the audit log table."""
        self._load_audit()

    def action_deactivate_key(self) -> None:
        """Prompt then deactivate the selected key."""
        key_id = self._selected_key_id()
        if key_id is None:
            return
        key = self._store.get_key_by_id(key_id)
        if not key:
            return

        def _handle(confirmed: bool | None) -> None:
            if confirmed:
                self._store.deactivate_key(key_id)
                self._load_keys()

        self.push_screen(
            ConfirmScreen(f"Deactivate key {key_id} ({key['provider']})?"),
            _handle,
        )

    def action_clear_cooldown(self) -> None:
        """Clear cooldown for the selected key."""
        key_id = self._selected_key_id()
        if key_id is None:
            return
        key = self._store.get_key_by_id(key_id)
        if not key:
            return
        self._store.clear_cooldown(key_id)
        self._load_keys()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "btn-add":
            self._submit_add_key()
        elif event.button.id == "btn-audit-refresh":
            self._load_audit()
        elif event.button.id == "btn-import-start":
            self._import_from_file()

    def _submit_add_key(self) -> None:
        status  = self.query_one("#status-msg", Static)
        prov    = self.query_one("#inp-provider", Select)
        key_inp = self.query_one("#inp-key", Input)
        model   = self.query_one("#inp-model", Input)
        base_url_inp = self.query_one("#inp-base-url", Input)

        provider = str(prov.value) if prov.value and str(prov.value) != "Select.BLANK" else ""
        api_key  = key_inp.value.strip()
        model_v  = model.value.strip() or None
        base_url_v = base_url_inp.value.strip() or None

        # collect checked capabilities
        caps = [
            cap for cap in KNOWN_CAPABILITIES
            if self.query_one(f"#cap-{cap}", Checkbox).value
        ]
        if not caps:
            caps = ["general_purpose"]

        if not provider:
            status.update("[red]Select a provider[/red]")
            return
        if not api_key:
            status.update("[red]API key required[/red]")
            return

        result = self._store.register_key(
            provider=provider,
            api_key=api_key,
            capabilities=caps,
            model=model_v,
            base_url_override=base_url_v,
        )

        if result["success"]:
            status.update(f"[green]✓ {result['message']}[/green]")
            key_inp.value = ""
            model.value   = ""
            base_url_inp.value = ""
            self._load_keys()
        else:
            status.update(f"[red]✗ {result['message']}[/red]")

    def _import_from_file(self) -> None:
        self.run_worker(self._import_from_file_async(), name="import-file", exit_on_error=False)

    async def _import_from_file_async(self) -> None:
        """Import API keys from a file with automatic provider detection."""
        status = self.query_one("#import-status", Static)
        file_inp = self.query_one("#inp-import-file", Input)
        dry_run = self.query_one("#chk-import-dry-run", Checkbox).value
        force = self.query_one("#chk-import-force", Checkbox).value
        check_providers = self.query_one("#chk-import-check-providers", Checkbox).value

        filename = file_inp.value.strip()
        if not filename:
            status.update("[red]Please enter a filename[/red]")
            return

        try:
            text = Path(filename).read_text(encoding="utf-8")
        except OSError as e:
            status.update(f"[red]Error reading file: {e}[/red]")
            return

        lines = text.splitlines()
        if not lines:
            status.update("[yellow]File is empty.[/yellow]")
            return

        provider_overrides: dict[str, str] = {}
        provider_check_errors: dict[str, str] = {}
        if check_providers:
            status.update("[bold]Checking unknown providers...[/bold]")
            provider_overrides, provider_check_errors = await _detect_unknown_provider_overrides(
                lines,
                self._providers,
                8.0,
                6,
            )

        entries, parse_errors = _resolve_import_entries(
            lines,
            self._providers,
            check_providers=check_providers,
            provider_overrides=provider_overrides,
            provider_check_errors=provider_check_errors,
        )

        if not entries and not parse_errors:
            status.update("[yellow]No keys found in file.[/yellow]")
            return

        if dry_run:
            text_out = _build_dry_run_text(entries, parse_errors)
            status.update(text_out)
            return

        if not force and parse_errors:
            ctx, reason = parse_errors[0]
            status.update(
                f"[red]Error:[/red] {ctx}: {reason}\n"
                "[red]Aborting. Use --force to skip problematic keys.[/red]",
            )
            return

        warn_lines = _build_warn_lines(parse_errors)

        succeeded, failed = self._execute_tui_import(entries, force, warn_lines, status)

        text_out = _build_summary_text(entries, parse_errors, succeeded, failed, warn_lines)
        status.update(text_out)

        if succeeded > 0:
            self._load_keys()

        file_inp.value = ""

    def _execute_tui_import(
        self,
        entries: list[dict[str, Any]],
        force: bool,  # noqa: FBT001
        warn_lines: list[str],
        status: Static,
    ) -> tuple[int, list[tuple[str, str, str]]]:
        """Register entries with progress display. Returns (succeeded, failed)."""
        succeeded = 0
        failed: list[tuple[str, str, str]] = []

        for idx, entry in enumerate(entries, 1):
            status.update(
                f"[bold]Importing {len(entries)} key(s)...[/bold]\n"
                f"Processing {idx}/{len(entries)}...",
            )

            result = self._store.register_key(
                provider=entry["provider"],
                api_key=entry["key"],
                capabilities=entry["capabilities"],
                model=entry["model"],
                base_url_override=entry["base_url"],
            )

            if result["success"]:
                succeeded += 1
            else:
                masked = _mask_key_display(entry["key"])
                failed.append((masked, entry["provider"], result["message"]))
                if not force:
                    error_lines = [
                        *warn_lines,
                        "",
                        f"[red]✗[/red] {masked} ({entry['provider']}): {result['message']}",
                        "[red]Aborting due to registration error. Use --force to skip.[/red]",
                    ]
                    status.update("\n".join(error_lines))
                    return succeeded, failed

        return succeeded, failed


def run() -> None:
    """Launch the TUI application."""
    LLMKeyPoolApp().run()
