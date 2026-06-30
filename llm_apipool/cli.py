"""CLI entry point for llm-apipool."""

from __future__ import annotations

import os

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

console = Console()


def _parse_import_entry(line: str) -> dict[str, str] | None:
    """Parse a single import entry line.

    Supports formats:
      - raw API key (auto-detect provider from prefix)
      - provider:key
      - provider:key:model
    """
    line = line.strip()
    if not line or line.startswith("#") or line.startswith("//"):
        return None

    # NDJSON line
    if line.startswith("{"):
        import json

        try:
            obj = json.loads(line)
            provider = obj.get("provider", "")
            key = obj.get("key", obj.get("api_key", ""))
            model = obj.get("model", "")
            return {"provider": provider, "key": key, "model": model}
        except (json.JSONDecodeError, TypeError):
            return None

    # provider:key or provider:key:model
    if ":" in line and not line.startswith("sk-"):
        parts = line.split(":", 2)
        provider = parts[0]
        key = parts[1]
        model = parts[2] if len(parts) > 2 else ""
        return {"provider": provider, "key": key, "model": model}

    # raw key — try prefix-based detection
    raw_key = line.split()[0]  # take first token
    return {"provider": "", "key": raw_key, "model": ""}


app = typer.Typer(help="LLM Apipool - Free-tier LLM gateway")


@app.command()
def proxy(
    port: int = typer.Option(8000, "--port", "-p", help="Port to run the server on"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    reload: bool = typer.Option(
        False, "--reload", help="Enable hot reload for development"
    ),
) -> None:
    """Run the OpenAI-compatible proxy server with web dashboard."""
    # Ensure frontend is built
    web_dist = os.path.join(os.path.dirname(__file__), "..", "web", "dist")
    if not os.path.exists(web_dist):
        typer.echo("Frontend not built. Run: cd frontend && npm run build", err=True)
        raise typer.Exit(1)

    typer.echo(f"Starting LLM Apipool server on http://{host}:{port}")
    typer.echo(f"Dashboard: http://localhost:{port}/")
    typer.echo(f"API: http://localhost:{port}/v1/chat/completions")
    uvicorn.run(
        "llm_apipool.api.app:make_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


@app.command()
def status() -> None:
    """Show key pool status."""
    from llm_apipool.key_store import KeyStore

    store = KeyStore()
    keys = store.get_all_keys()
    active = [k for k in keys if k.get("is_active")]
    typer.echo(f"Total keys: {len(keys)}")
    typer.echo(f"Active keys: {len(active)}")


@app.command()
def sync_models(
    provider: str | None = typer.Option(
        None, "--provider", "-p", help="Provider to sync (default: all)"
    ),
    key_id: int | None = typer.Option(
        None, "--key-id", "-k", help="Specific key ID to use for API call"
    ),
) -> None:
    """Fetch and store models from provider /v1/models endpoints."""
    import asyncio
    import json
    from pathlib import Path

    from llm_apipool.api.app import _load_provider_configs
    from llm_apipool.core.model_ingestion import (
        sync_all_providers,
        sync_provider_models,
    )
    from llm_apipool.key_store import KeyStore

    store = KeyStore()
    configs = _load_provider_configs()

    # Load tier map from model_quality.json
    tier_path = Path(__file__).resolve().parent / "config" / "model_quality.json"
    tier_map: dict[str, int] = {}
    if tier_path.exists():
        try:
            quality = json.loads(tier_path.read_text())
            for tier_name, models in quality.items():
                try:
                    # Extract number from "tier1", "tier2", "tier3", "tier4"
                    tier_str = tier_name.lower().replace("tier", "").strip()
                    tier_num = int(tier_str) if tier_str.isdigit() else 4
                except (ValueError, IndexError):
                    tier_num = 4
                for m in models if isinstance(models, list) else []:
                    tier_map[m] = tier_num
        except (json.JSONDecodeError, Exception):
            pass

    if provider:
        result = asyncio.run(
            sync_provider_models(
                store, provider, configs, key_id=key_id, tier_map=tier_map
            )
        )
        typer.echo(f"Synced {provider}: {result['models_upserted']} models")
    else:
        results = asyncio.run(sync_all_providers(store, configs, tier_map=tier_map))
        total = sum(r["models_upserted"] for r in results)
        typer.echo(f"Synced {len(results)} providers, {total} total models")


@app.command()
def add(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name"),
    key: str = typer.Option(..., "--key", "-k", help="API key"),
    model: str = typer.Option("", "--model", "-m", help="Model name"),
    capabilities: str = typer.Option(
        "general_purpose", "--capabilities", "-c", help="Comma-separated capabilities"
    ),
) -> None:
    """Register a new API key."""
    from llm_apipool.key_store import KeyStore

    store = KeyStore()
    caps = [c.strip() for c in capabilities.split(",")]
    result = store.register_key(
        provider=provider,
        api_key=key,
        model=model or None,
        capabilities=caps,
    )
    if result.get("success"):
        typer.echo(result["message"])
    else:
        typer.echo(f"Error: {result['message']}", err=True)
        raise typer.Exit(1)


@app.command()
def deactivate(
    key_id: int = typer.Argument(..., help="Key ID to deactivate"),
) -> None:
    """Deactivate a key by ID (soft delete)."""
    from llm_apipool.key_store import KeyStore

    store = KeyStore()
    existing = store.get_key_by_id(key_id)
    if not existing:
        typer.echo(f"Key with ID {key_id} not found.", err=True)
        raise typer.Exit(1)
    store.deactivate_key(key_id)
    typer.echo(f"Key {key_id} ({existing.get('provider', '?')}) deactivated.")


@app.command()
def logs(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of entries"),
    subscriber: str | None = typer.Option(
        None, "--subscriber", "-s", help="Filter by subscriber ID"
    ),
) -> None:
    """Show recent audit log entries."""
    from llm_apipool.key_store import KeyStore

    store = KeyStore()
    entries = store.get_audit_log(subscriber_id=subscriber, limit=limit, days=30)

    if not entries:
        typer.echo("No audit log entries found.")
        return

    table = Table(title=f"Audit Log (last {len(entries)} entries)")
    table.add_column("ID", style="dim")
    table.add_column("Time", style="cyan")
    table.add_column("Subscriber")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Tokens")
    table.add_column("Status")

    for e in entries:
        status = "OK" if e.get("success") else "FAIL"
        tokens = (e.get("tokens_in", 0) or 0) + (e.get("tokens_out", 0) or 0)
        table.add_row(
            str(e.get("id", "")),
            str(e.get("ts", ""))[11:19],
            str(e.get("subscriber_id", "")),
            str(e.get("provider", "") or ""),
            str(e.get("model", "") or ""),
            str(tokens),
            status,
        )

    console.print(table)


@app.command(name="import")
def import_keys(
    file: str = typer.Option(..., "--file", "-f", help="Path to key file"),
    format: str = typer.Option(  # noqa: A002
        "auto", "--format", help="Format: auto, key-per-line, ndjson"
    ),
) -> None:
    """Import keys from a file."""
    from pathlib import Path

    from llm_apipool.key_store import KeyStore

    path = Path(file)
    if not path.exists():
        typer.echo(f"File not found: {file}", err=True)
        raise typer.Exit(1)

    store = KeyStore()
    lines = path.read_text().splitlines()
    imported = 0
    errors = 0

    for line in lines:
        entry = _parse_import_entry(line)
        if entry is None:
            continue
        result = store.register_key(
            provider=entry["provider"] or "unknown",
            api_key=entry["key"],
            model=entry.get("model") or None,
        )
        if result.get("success"):
            imported += 1
        else:
            errors += 1

    typer.echo(f"Imported {imported} keys ({errors} skipped).")


@app.command()
def gui() -> None:
    """Launch the interactive Textual TUI."""
    try:
        from llm_apipool.tui import LLMKeyPoolApp

        LLMKeyPoolApp().run()
    except ImportError:
        typer.echo(
            'Textual TUI not available. Install with: pip install "llm-apipool[all]"',
            err=True,
        )
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
