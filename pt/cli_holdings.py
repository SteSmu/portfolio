"""`pt holdings` — aggregated view of current positions.

Holdings are computed from transactions (single source of truth). For
FIFO/LIFO-correct cost basis, see `pt perf cost-basis`.

Examples:
  pt holdings list --portfolio 1
  pt holdings show --portfolio 1 --symbol AAPL --asset-type stock
  pt holdings list --portfolio 1 --json
"""

from __future__ import annotations

import json
import sys

import typer
from rich.console import Console
from rich.table import Table

from pt.db import holdings as _holdings

app = typer.Typer(help="Aggregated holdings view (computed from transactions).",
                  no_args_is_help=True)
console = Console()


@app.command("list")
def cmd_list(
    portfolio_id: int = typer.Option(..., "--portfolio", "-p"),
    include_zero: bool = typer.Option(False, "--include-zero",
                                       help="Include closed positions (qty <= 0)."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List current holdings (one row per symbol)."""
    rows = _holdings.list_for_portfolio(portfolio_id, include_zero=include_zero)
    if json_output:
        print(json.dumps(rows, default=str))
        return

    if not rows:
        console.print(f"[yellow]No holdings for portfolio {portfolio_id}.[/yellow] "
                      "Add transactions with [cyan]pt tx add[/cyan].")
        return

    table = Table(title=f"Holdings (portfolio={portfolio_id})")
    table.add_column("Symbol", style="cyan")
    table.add_column("Type")
    table.add_column("Qty", justify="right")
    table.add_column("Avg cost", justify="right")
    table.add_column("Total cost", justify="right")
    table.add_column("Cur")
    table.add_column("First", style="dim")
    table.add_column("Last", style="dim")
    table.add_column("Tx", justify="right", style="dim")
    for r in rows:
        table.add_row(
            r["symbol"],
            r["asset_type"],
            f"{r['quantity']:g}",
            f"{r['avg_cost']:.4f}",
            f"{r['total_cost']:.2f}",
            r["currency"],
            r["first_tx_at"].strftime("%Y-%m-%d") if r["first_tx_at"] else "-",
            r["last_tx_at"].strftime("%Y-%m-%d") if r["last_tx_at"] else "-",
            str(r["tx_count"]),
        )
    console.print(table)


@app.command("show")
def cmd_show(
    portfolio_id: int = typer.Option(..., "--portfolio", "-p"),
    symbol: str = typer.Option(..., "--symbol", "-s"),
    asset_type: str = typer.Option(..., "--asset-type", "-t"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show aggregated position for one symbol."""
    row = _holdings.get_for_symbol(portfolio_id, symbol, asset_type)
    if not row:
        if json_output:
            print(json.dumps({"error": "not_found"}), file=sys.stderr)
        else:
            console.print(f"[red]✗[/red] No holding {symbol.upper()} ({asset_type}) "
                          f"in portfolio {portfolio_id}.")
        raise typer.Exit(3)
    if json_output:
        print(json.dumps(row, default=str))
        return
    for k, v in row.items():
        console.print(f"  [dim]{k}:[/dim] {v}")
