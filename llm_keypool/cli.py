"""CLI interface for llm-keypool."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from llm_keypool.key_checker import auto_detect_provider, detect_provider_sync
from llm_keypool.key_store import KeyStore

app = typer.Typer(
    help="llm-keypool - free-tier API key pool manager",
    no_args_is_help=True,
)
console = Console()

MIN_KEY_LENGTH = 4
MASK_KEY_MIN_LENGTH = 8

# All known capabilities
KNOWN_CAPABILITIES = [
    "general_purpose",
    "agentic",
    "fast",
    "code",
    "vision",
    "large_context",
]


def _load_provider_configs() -> dict[str, Any]:
    config_path = Path(__file__).parent / "config" / "providers.json"
    if not config_path.exists():
        console.print(f"[red]Config file not found: {config_path}[/red]")
        raise typer.Exit(1)
    with config_path.open() as f:
        try:
            return json.load(f)["providers"]  # type: ignore[no-any-return]
        except (json.JSONDecodeError, KeyError) as e:
            console.print(f"[red]Invalid config file: {e}[/red]")
            raise typer.Exit(1) from None


@app.command()
def status() -> None:
    """Show all registered keys and their current status."""
    store = KeyStore()
    keys = store.get_all_keys()
    now = datetime.now(UTC).isoformat()

    if not keys:
        console.print("[yellow]No keys registered.[/yellow]")
        console.print("Run: [cyan]llm-keypool add --provider groq --key gsk_...[/cyan]")
        return

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("ID",           style="dim",  width=4)
    table.add_column("Provider",     min_width=14)
    table.add_column("Capabilities", min_width=22)
    table.add_column("Model",        min_width=22)
    table.add_column("Active",       width=7)
    table.add_column("Req Today",    width=10, justify="right")
    table.add_column("Cooldown Until", min_width=22)

    for k in keys:
        in_cooldown  = bool(k["cooldown_until"] and k["cooldown_until"] > now)
        active_str   = "[green]yes[/green]" if k["is_active"] else "[red]no[/red]"
        cooldown_str = (
            f"[yellow]{k['cooldown_until'][:19]}[/yellow]"
            if in_cooldown else "[dim]-[/dim]"
        )
        caps = ", ".join(store.parse_capabilities(k))
        table.add_row(
            str(k["id"]),
            k["provider"],
            caps,
            k["model"] or "[dim]default[/dim]",
            active_str,
            str(k["requests_today"]),
            cooldown_str,
            style="" if k["is_active"] else "dim",
        )

    console.print(table)
    console.print(f"[dim]{len(keys)} key(s) total[/dim]")


@app.command()
def add(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name (groq, cerebras, mistral, google, ...)"),
    key: str = typer.Option(..., "--key", "-k", help="API key string"),
    capabilities: str = typer.Option(
        "general_purpose",
        "--capabilities", "--cap",
        help="Comma-separated capabilities: general_purpose, agentic, fast, code, vision, large_context",
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Model name (uses provider default if omitted)"),
    base_url: str | None = typer.Option(
        None, "--base-url",
        help="Override the provider's default Base URL (e.g., for local proxies or custom endpoints)",
    ),
) -> None:
    """Register a new API key for a provider."""
    configs = _load_provider_configs()
    provider = provider.lower().strip()
    if not provider:
        console.print("[red]Provider name cannot be empty[/red]")
        raise typer.Exit(1)

    if provider not in configs:
        console.print(f"[red]Unknown provider '{provider}'[/red]")
        console.print(f"Supported: {', '.join(sorted(configs.keys()))}")
        raise typer.Exit(1)

    # Basic key validation (length check)
    if not key or len(key) < MIN_KEY_LENGTH:
        console.print("[red]API key too short or empty[/red]")
        raise typer.Exit(1)

    # parse capabilities
    caps = [c.strip() for c in capabilities.split(",") if c.strip()]

    unknown = [c for c in caps if c not in KNOWN_CAPABILITIES]
    if unknown:
        console.print(f"[yellow]Warning: unknown capabilities: {', '.join(unknown)}[/yellow]")
        console.print(f"Known: {', '.join(KNOWN_CAPABILITIES)}")

    store = KeyStore()
    result = store.register_key(
        provider=provider,
        api_key=key,
        capabilities=caps,
        model=model or None,
        base_url_override=base_url,
    )

    if result["success"]:
        console.print(f"[green]✓[/green] {result['message']}")
    else:
        console.print(f"[red]✗[/red] {result['message']}")
        raise typer.Exit(1)


@app.command()
def deactivate(
    key_id: int = typer.Option(..., "--id", help="Key ID from 'llm-keypool status'"),
) -> None:
    """Deactivate a key (revoked or expired). Does not delete it."""
    store = KeyStore()
    key = store.get_key_by_id(key_id)
    if not key:
        console.print(f"[red]Key ID {key_id} not found[/red]")
        raise typer.Exit(1)

    if not key["is_active"]:
        console.print(f"[yellow]Key {key_id} ({key['provider']}) already inactive[/yellow]")
        return

    store.deactivate_key(key_id)
    console.print(f"[green]✓[/green] Key {key_id} ({key['provider']}) deactivated")


@app.command(name="clear-cooldown")
def clear_cooldown(
    key_id: int = typer.Option(..., "--id", help="Key ID from 'llm-keypool status'"),
) -> None:
    """Clear a key's cooldown (e.g. after quota reset confirmed)."""
    store = KeyStore()
    key = store.get_key_by_id(key_id)
    if not key:
        console.print(f"[red]Key ID {key_id} not found[/red]")
        raise typer.Exit(1)

    store.clear_cooldown(key_id)
    console.print(f"[green]✓[/green] Cooldown cleared for key {key_id} ({key['provider']})")


@app.command()
def providers() -> None:
    """List all supported providers and their capabilities."""
    configs = _load_provider_configs()

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Provider",      min_width=14)
    table.add_column("Capabilities",  min_width=30)
    table.add_column("Default Model", min_width=26)
    table.add_column("OpenAI Compat", width=14, justify="center")

    for name, cfg in sorted(configs.items()):
        caps    = ", ".join(cfg.get("capabilities", []))
        default = cfg.get("default_model", "-")
        compat  = "[green]yes[/green]" if cfg.get("openai_compatible") else "[dim]no[/dim]"
        table.add_row(name, caps, default or "[dim]-[/dim]", compat)

    console.print(table)


@app.command()
def audit(
    subscriber: str | None = typer.Option(None, "--subscriber", "-s", help="Filter by subscriber ID"),
    days: int = typer.Option(7, "--days", "-d", help="Number of days to look back"),
    summary: bool = typer.Option(False, "--summary", help="Show aggregate summary instead of raw rows"),  # noqa: FBT001, FBT003
) -> None:
    """Show audit log of LLM calls by subscriber."""
    store = KeyStore()

    if summary:
        rows = store.get_audit_summary(days=days)
        if not rows:
            console.print(f"[yellow]No audit data in last {days} days.[/yellow]")
            return
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("Subscriber",    min_width=22)
        table.add_column("Requests",      width=10, justify="right")
        table.add_column("Tokens In",     width=12, justify="right")
        table.add_column("Tokens Out",    width=12, justify="right")
        table.add_column("Total Tokens",  width=14, justify="right")
        table.add_column("Errors",        width=8,  justify="right")
        for r in rows:
            table.add_row(
                r["subscriber_id"],
                str(r["requests"]),
                str(r["tokens_in"] or 0),
                str(r["tokens_out"] or 0),
                str(r["tokens_total"] or 0),
                str(r["errors"] or 0),
            )
        console.print(table)
        console.print(f"[dim]Last {days} days[/dim]")
        return

    rows = store.get_audit_log(subscriber_id=subscriber, days=days)
    if not rows:
        msg = "[yellow]No audit entries"
        if subscriber:
            msg += f" for subscriber '{subscriber}'"
        msg += f" in last {days} days.[/yellow]"
        console.print(msg)
        return

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Time",         min_width=19)
    table.add_column("Subscriber",   min_width=20)
    table.add_column("Provider",     min_width=12)
    table.add_column("Model",        min_width=22)
    table.add_column("Tok In",       width=8,  justify="right")
    table.add_column("Tok Out",      width=8,  justify="right")
    table.add_column("ms",           width=6,  justify="right")
    table.add_column("OK",           width=5,  justify="center")

    for r in rows:
        ok = "[green]y[/green]" if r["success"] else "[red]n[/red]"
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

    console.print(table)
    console.print(f"[dim]{len(rows)} entries, last {days} days[/dim]")


@app.command(name="check-key")
def check_key(
    key: str = typer.Argument(..., help="API key to test against providers"),
    providers: str | None = typer.Option(
        None,
        "--providers",
        help="Comma-separated provider list. Defaults to all testable providers.",
    ),
    timeout: float = typer.Option(8.0, "--timeout", help="Per-provider timeout in seconds"),
    max_concurrent: int = typer.Option(6, "--max-concurrent", min=1, help="Max concurrent provider checks"),
) -> None:
    candidates = [p.strip() for p in providers.split(",") if p.strip()] if providers else None

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Provider", min_width=16)
    table.add_column("Status", width=12, justify="center")
    table.add_column("Detail", min_width=40)

    results = asyncio.run(auto_detect_provider(key, candidates, timeout, max_concurrent))
    for provider, success, detail in results:
        status = "[green]match[/green]" if success else "[dim]no match[/dim]"
        table.add_row(provider, status, detail)

    console.print(table)
    if any(success for _, success, _ in results):
        console.print("[green]Provider detected.[/green]")
    else:
        console.print("[yellow]No provider accepted this key.[/yellow]")


@app.command()
def gui() -> None:
    """Launch the Textual TUI."""
    try:
        from llm_keypool.tui import run  # noqa: PLC0415
    except ImportError:
        console.print("[red]Textual not installed.[/red] Run: pip install 'llm-keypool[gui]'")
        raise typer.Exit(1) from None
    run()


@app.command()
def proxy(  # noqa: PLR0913
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    capabilities: str = typer.Option(
        "general_purpose",
        "--capabilities", "--cap",
        help="Comma-separated capabilities filter (default: general_purpose)",
    ),
    rotate_every: int = typer.Option(5, "--rotate-every", help="Requests per key before rotating"),
    quality_tier: int = typer.Option(
        1, "--quality-tier",
        help="Preferred model quality tier (1=best). Lower tiers exhausted before falling back.",
        min=1, max=4,
    ),
    max_fallback_tier: int = typer.Option(
        4, "--max-fallback-tier",
        help="Worst quality tier to accept (inclusive). Never uses tiers worse than this.",
        min=1, max=4,
    ),
) -> None:
    """Start OpenAI-compatible proxy at http://localhost:8000/v1 with model quality routing."""
    try:
        import uvicorn  # noqa: PLC0415

        from llm_keypool.proxy import make_app  # noqa: PLC0415
    except ImportError:
        console.print("[red]Proxy deps missing.[/red] Run: pip install 'llm-keypool[proxy]'")
        raise typer.Exit(1) from None

    caps = [c.strip() for c in capabilities.split(",") if c.strip()]

    if quality_tier > max_fallback_tier:
        console.print(
            "[red]--quality-tier must be <= --max-fallback-tier[/red]",
        )
        raise typer.Exit(1)

    console.print(
        f"[green]llm-keypool proxy[/green] listening on [cyan]http://{host}:{port}/v1[/cyan]",
    )
    console.print(
        f"Capabilities: [cyan]{', '.join(caps)}[/cyan] | "
        f"Rotate every: [cyan]{rotate_every}[/cyan] requests | "
        f"Quality tier: [cyan]{quality_tier}[/cyan] → [cyan]{max_fallback_tier}[/cyan]",
    )
    uvicorn.run(
        make_app(
            capabilities=caps,
            rotate_every=rotate_every,
            quality_tier=quality_tier,
            max_fallback_tier=max_fallback_tier,
        ),
        host=host,
        port=port,
    )


# ---------------------------------------------------------------------------
# import command - batch import API keys from a file
# ---------------------------------------------------------------------------

# Key prefix → provider auto-detection mapping
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
    configs: dict[str, Any],
    timeout: float,
    max_concurrent: int,
) -> tuple[str, bool, str, int]:
    results = detect_provider_sync(key, timeout=timeout, max_concurrent=max_concurrent)
    for provider, success, detail in results:
        if success:
            return provider, True, detail, len(results)
    return "", False, "; ".join(f"{p}: {d}" for p, _, d in results[:3]), len(results)


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
            if check_providers:
                detected, success, detail, checked = _resolve_provider_by_checking(
                    key,
                    configs,
                    check_timeout,
                    check_concurrency,
                )
                if success:
                    provider = detected
                    console.print(
                        f"[green]Detected {_mask_key_display(key)} as {provider} after checking {checked} provider(s).[/green]",
                    )
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


def _show_dry_run(entries: list[dict[str, Any]], errors: list[tuple[str, str]]) -> None:
    """Display what would be imported in dry-run mode."""
    if errors:
        console.print(f"\n[yellow]Issues found ({len(errors)}):[/yellow]")
        for ctx, reason in errors:
            console.print(f"  [yellow]⚠[/yellow] {ctx}: {reason}")
        console.print()

    if not entries:
        console.print("[yellow]No valid keys to import.[/yellow]")
        return

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Provider", min_width=16)
    table.add_column("Key", min_width=28)
    table.add_column("Capabilities", min_width=24)
    table.add_column("Model", min_width=24)
    table.add_column("Base URL", min_width=24)

    for r in entries:
        masked = _mask_key_display(r["key"])
        caps_str = ", ".join(r["capabilities"])
        table.add_row(
            r["provider"],
            masked,
            caps_str,
            r["model"] or "[dim]default[/dim]",
            r["base_url"] or "[dim]default[/dim]",
        )

    console.print(f"\n[bold]Dry-run:[/bold] {len(entries)} key(s) would be imported")
    console.print(table)


def _execute_import(
    entries: list[dict[str, Any]],
    store: KeyStore,
    force: bool,  # noqa: FBT001
) -> tuple[int, list[tuple[str, str, str]]]:
    """Register all entries, printing progress. Returns (succeeded, failed)."""
    succeeded = 0
    failed: list[tuple[str, str, str]] = []

    for entry in entries:
        result = store.register_key(
            provider=entry["provider"],
            api_key=entry["key"],
            capabilities=entry["capabilities"],
            model=entry["model"],
            base_url_override=entry["base_url"],
        )

        if result["success"]:
            console.print(f"  [green]✓[/green] {result['message']}")
            succeeded += 1
        else:
            masked = _mask_key_display(entry["key"])
            console.print(f"  [red]✗[/red] {masked} ({entry['provider']}): {result['message']}")
            failed.append((masked, entry["provider"], result["message"]))
            if not force:
                console.print("[red]Aborting due to registration error. Use --force to skip.[/red]")
                raise typer.Exit(1)

    return succeeded, failed


def _show_summary(
    succeeded: int,
    failed: list[tuple[str, str, str]],
    errors: list[tuple[str, str]],
    entries: list[dict[str, Any]],
) -> None:
    """Display the import summary."""
    total = len(entries) + len(errors)
    console.print("\n[bold]Import Summary:[/bold]")
    console.print(f"  Total parsed:  {total}")
    console.print(f"  [green]Registered: {succeeded}[/green]")
    console.print(f"  [yellow]Skipped:    {len(errors)}[/yellow]")
    console.print(f"  [red]Failed:     {len(failed)}[/red]")

    if failed:
        console.print("\n[yellow]Failed keys:[/yellow]")
        for masked, prov, reason in failed:
            console.print(f"  [red]✗[/red] {masked} ({prov}): {reason}")

    if errors:
        console.print("\n[yellow]Skipped keys (could not resolve):[/yellow]")
        for ctx, reason in errors:
            console.print(f"  [yellow]⚠[/yellow] {ctx}: {reason}")

    if succeeded == 0 and (failed or errors):
        console.print("[red]No keys were imported successfully.[/red]")
        raise typer.Exit(1)


@app.command(name="import")
def import_keys(
    filename: str = typer.Argument(
        ...,
        help="File to import API keys from (key-per-line, provider:key, NDJSON, or block-separated)",
    ),
    dry_run: bool = typer.Option(  # noqa: FBT001
        False,  # noqa: FBT003
        "--dry-run",
        help="Parse the file and show what would be imported without registering",
    ),
    force: bool = typer.Option(  # noqa: FBT001
        False,  # noqa: FBT003
        "--force",
        help="Continue importing even if some keys fail or can't be detected",
    ),
    check_providers: bool = typer.Option(  # noqa: FBT001
        False,  # noqa: FBT003
        "--check-providers",
        help="For unresolved keys, try providers and import only keys that get a successful response",
    ),
    check_timeout: float = typer.Option(
        8.0,
        "--check-timeout",
        help="Per-provider timeout for --check-providers",
    ),
    check_concurrency: int = typer.Option(
        6,
        "--check-concurrency",
        help="Max concurrent provider checks for --check-providers",
        min=1,
    ),
) -> None:
    r"""Import API keys from a file with automatic provider detection.

    Supports 4 file formats:

    \b
    \b
    1. Key-per-line:  one API key per line
    2. provider:key:  provider name, colon, then key (e.g. groq:gsk_...)
    3. NDJSON:        each line is a JSON object with at least a "key" field
                      (optional: provider, capabilities, model, base_url)
    4. Multi-line blocks: blocks separated by lines containing exactly "---"

    Provider auto-detection from key prefixes:
    \b
      gsk_    → groq
      sk-     → openai
      cs_     → cerebras
      mi_     → mistral
      AIza    → google
      hf_     → huggingface_router
      or_     → openrouter
      cohere_ → cohere
      cf-     → cloudflare

    Use --check-providers to test unresolved keys against supported providers.
    Only successful provider responses are imported.
    """
    configs = _load_provider_configs()

    try:
        file_path = Path(filename)
        text = file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        console.print(f"[red]File not found: {filename}[/red]")
        raise typer.Exit(1) from None
    except OSError as e:
        console.print(f"[red]Error reading file: {e}[/red]")
        raise typer.Exit(1) from None

    lines = text.splitlines()
    if not lines:
        console.print("[yellow]File is empty.[/yellow]")
        return

    entries, errors = _resolve_import_entries(
        lines,
        configs,
        check_providers=check_providers,
        check_timeout=check_timeout,
        check_concurrency=check_concurrency,
    )

    if not entries and not errors:
        console.print("[yellow]No keys found in file.[/yellow]")
        return

    if dry_run:
        _show_dry_run(entries, errors)
        return

    if not force and errors:
        ctx, reason = errors[0]
        console.print(f"[red]Error:[/red] {ctx}: {reason}")
        console.print("[red]Aborting. Use --force to skip problematic keys.[/red]")
        raise typer.Exit(1)

    for ctx, reason in errors:
        console.print(f"[yellow]Warning:[/yellow] {ctx}: {reason} - skipping")

    store = KeyStore()
    console.print(f"Importing {len(entries)} key(s) ...")
    succeeded, failed = _execute_import(entries, store, force)
    _show_summary(succeeded, failed, errors, entries)
