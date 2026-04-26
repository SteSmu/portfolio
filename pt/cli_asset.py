"""`pt asset` — asset master CRUD (metadata per symbol).

Examples:
  pt asset add AAPL stock --name "Apple Inc." --currency USD --exchange nasdaq --isin US0378331005
  pt asset list --type stock
  pt asset show AAPL stock
  pt asset find apple
"""

from __future__ import annotations

import json
import sys

import typer
from rich.console import Console
from rich.table import Table

from pt.db import assets as _assets

app = typer.Typer(help="Asset master CRUD.", no_args_is_help=True)
console = Console()


@app.command("add")
def cmd_add(
    symbol: str = typer.Argument(..., help="Symbol (e.g. AAPL, BTC)."),
    asset_type: str = typer.Argument(..., help="crypto / stock / etf / fx / commodity / bond."),
    name: str = typer.Option(..., "--name", "-n"),
    currency: str = typer.Option(..., "--currency", "-c"),
    exchange: str | None = typer.Option(None, "--exchange", "-e"),
    isin: str | None = typer.Option(None, "--isin"),
    wkn: str | None = typer.Option(None, "--wkn"),
    sector: str | None = typer.Option(None, "--sector"),
    region: str | None = typer.Option(None, "--region"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Add or update an asset master record (idempotent upsert)."""
    _assets.upsert(
        symbol=symbol, asset_type=asset_type, name=name, currency=currency,
        exchange=exchange, isin=isin, wkn=wkn, sector=sector, region=region,
    )
    if json_output:
        print(json.dumps({"ok": True, "symbol": symbol.upper(), "asset_type": asset_type}))
    else:
        console.print(f"[green]✓[/green] Asset {symbol.upper()} ({asset_type}) upserted.")


@app.command("list")
def cmd_list(
    asset_type: str | None = typer.Option(None, "--type", "-t"),
    search: str | None = typer.Option(None, "--search", "-s"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List asset master entries."""
    rows = _assets.list_all(asset_type=asset_type, search=search)
    if json_output:
        print(json.dumps(rows, default=str))
        return
    if not rows:
        console.print("[yellow]No assets found.[/yellow]")
        return
    table = Table(title=f"Assets (n={len(rows)})")
    table.add_column("Symbol", style="cyan")
    table.add_column("Type")
    table.add_column("Name")
    table.add_column("Cur")
    table.add_column("Exchange")
    table.add_column("ISIN", style="dim")
    for r in rows:
        table.add_row(
            r["symbol"], r["asset_type"], r["name"], r["currency"],
            r.get("exchange") or "-", r.get("isin") or "-",
        )
    console.print(table)


@app.command("show")
def cmd_show(
    symbol: str = typer.Argument(...),
    asset_type: str = typer.Argument(...),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show one asset master entry."""
    row = _assets.get(symbol, asset_type)
    if not row:
        if json_output:
            print(json.dumps({"error": "not_found"}), file=sys.stderr)
        else:
            console.print(f"[red]✗[/red] Asset {symbol.upper()} ({asset_type}) not found.")
            sims = _assets.find_similar(symbol, limit=5)
            if sims:
                console.print("Did you mean:")
                for s in sims:
                    console.print(f"  • {s['symbol']} ({s['asset_type']}) — {s['name']}")
        raise typer.Exit(3)
    if json_output:
        print(json.dumps(row, default=str))
        return
    for k, v in row.items():
        console.print(f"  [dim]{k}:[/dim] {v}")


@app.command("find")
def cmd_find(
    query: str = typer.Argument(..., help="Symbol, name, ISIN, or WKN substring."),
    limit: int = typer.Option(10, "--limit", min=1, max=100),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Fuzzy-search the asset master."""
    rows = _assets.find_similar(query, limit=limit)
    if json_output:
        print(json.dumps(rows, default=str))
        return
    if not rows:
        console.print(f"[yellow]No matches for '{query}'.[/yellow]")
        return
    for r in rows:
        console.print(f"  • [cyan]{r['symbol']}[/cyan] ({r['asset_type']}) — {r['name']}")
