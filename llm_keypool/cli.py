"""CLI entry point for llm-keypool."""

from __future__ import annotations

import os
import sys

import typer
import uvicorn

from llm_keypool.api.app import make_app

app = typer.Typer(help="LLM Keypool - Free-tier LLM gateway")


@app.command()
def proxy(
    port: int = typer.Option(8000, "--port", "-p", help="Port to run the server on"),
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    reload: bool = typer.Option(False, "--reload", help="Enable hot reload for development"),
) -> None:
    """Run the OpenAI-compatible proxy server with web dashboard."""
    # Ensure frontend is built
    web_dist = os.path.join(os.path.dirname(__file__), "..", "web", "dist")
    if not os.path.exists(web_dist):
        typer.echo("Frontend not built. Run: cd frontend && npm run build", err=True)
        raise typer.Exit(1)

    typer.echo(f"Starting LLM Keypool server on http://{host}:{port}")
    typer.echo("Dashboard: http://localhost:{port}/")
    typer.echo("API: http://localhost:{port}/v1/chat/completions")
    uvicorn.run(
        "llm_keypool.api.app:make_app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def status() -> None:
    """Show key pool status."""
    from llm_keypool.key_store import KeyStore
    store = KeyStore()
    keys = store.get_all_keys()
    active = [k for k in keys if k.get("is_active")]
    typer.echo(f"Total keys: {len(keys)}")
    typer.echo(f"Active keys: {len(active)}")


@app.command()
def sync_models(
    provider: str | None = typer.Option(None, "--provider", "-p", help="Provider to sync (default: all)"),
    key_id: int | None = typer.Option(None, "--key-id", "-k", help="Specific key ID to use for API call"),
) -> None:
    """Fetch and store models from provider /v1/models endpoints."""
    import asyncio
    import json
    from pathlib import Path

    from llm_keypool.api.app import _load_provider_configs
    from llm_keypool.core.model_ingestion import sync_all_providers, sync_provider_models
    from llm_keypool.key_store import KeyStore

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
        result = asyncio.run(sync_provider_models(store, provider, configs, key_id=key_id, tier_map=tier_map))
        typer.echo(f"Synced {provider}: {result['models_upserted']} models")
    else:
        results = asyncio.run(sync_all_providers(store, configs, tier_map=tier_map))
        total = sum(r["models_upserted"] for r in results)
        typer.echo(f"Synced {len(results)} providers, {total} total models")


if __name__ == "__main__":
    app()