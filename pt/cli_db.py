"""`pt db` — schema migration and DB introspection.

Examples:
  pt db migrate              # apply schema_portfolio.sql (idempotent)
  pt db status               # show tables + connectivity
  pt db status --json        # machine-readable
"""

from __future__ import annotations

import json
import sys

import typer
from rich.console import Console
from rich.table import Table

from pt.db import migrate as _migrate
from pt.db.connection import is_available

app = typer.Typer(help="Database schema + introspection.", no_args_is_help=True)
console = Console()


@app.command("migrate")
def cmd_migrate(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON result on stdout."),
) -> None:
    """Apply the portfolio schema (idempotent — safe to re-run)."""
    try:
        _migrate.apply_schema()
    except Exception as e:
        if json_output:
            print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        else:
            console.print(f"[red]Migration failed:[/red] {e}", style="bold")
        raise typer.Exit(1)

    tables = _migrate.list_tables()
    candles_ok = _migrate.candles_has_asset_type()
    if json_output:
        print(json.dumps({
            "ok": True,
            "schema": "portfolio",
            "tables": tables,
            "candles_extended": candles_ok,
        }))
    else:
        console.print(f"[green]✓[/green] Schema applied. {len(tables)} tables in [cyan]portfolio[/cyan].")
        if candles_ok:
            console.print("[green]✓[/green] public.candles extended with asset_type / exchange.")


@app.command("status")
def cmd_status(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON result on stdout."),
) -> None:
    """Show DB connectivity + portfolio schema state."""
    db_ok = is_available()
    tables = _migrate.list_tables() if db_ok else []
    candles_ok = _migrate.candles_has_asset_type() if db_ok else False

    if json_output:
        print(json.dumps({
            "db": "ok" if db_ok else "unavailable",
            "tables": tables,
            "candles_extended": candles_ok,
        }))
        return

    if not db_ok:
        console.print("[red]✗[/red] DB unavailable. Check PT_DB_* env vars.")
        raise typer.Exit(1)

    table = Table(title="portfolio schema")
    table.add_column("Table", style="cyan")
    for t in tables:
        table.add_row(t)
    console.print(table)
    candles_marker = "[green]✓[/green]" if candles_ok else "[red]✗[/red]"
    console.print(f"{candles_marker} public.candles asset_type column")
