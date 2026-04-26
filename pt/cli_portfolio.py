"""`pt portfolio` — create / list / show / archive portfolios.

Examples:
  pt portfolio create "Real-Depot" --base-currency EUR
  pt portfolio list
  pt portfolio show 1
  pt portfolio archive 1
  pt portfolio list --json
"""

from __future__ import annotations

import json
import sys

import typer
from rich.console import Console
from rich.table import Table

from pt.db import portfolios as _portfolios

app = typer.Typer(help="Portfolio CRUD.", no_args_is_help=True)
console = Console()


@app.command("create")
def cmd_create(
    name: str = typer.Argument(..., help="Portfolio name (e.g. 'Real-Depot')."),
    base_currency: str = typer.Option("EUR", "--base-currency", "-c",
                                       help="Base currency for performance calculations."),
    user_id: str | None = typer.Option(None, "--user-id",
                                        help="Optional user identifier (multi-user-ready)."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Create a new portfolio."""
    existing = _portfolios.get_by_name(name)
    if existing:
        msg = f"Portfolio with name {name!r} already exists (id={existing['id']})."
        if json_output:
            print(json.dumps({"error": "conflict", "message": msg, "existing": existing},
                             default=str), file=sys.stderr)
        else:
            console.print(f"[red]✗[/red] {msg}")
        raise typer.Exit(5)  # 5 = conflict

    try:
        pid = _portfolios.create(name, base_currency, user_id)
    except ValueError as e:
        if json_output:
            print(json.dumps({"error": "usage", "message": str(e)}), file=sys.stderr)
        else:
            console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(2)

    if json_output:
        print(json.dumps({"ok": True, "id": pid}))
    else:
        console.print(f"[green]✓[/green] Portfolio '{name}' created (id={pid}, "
                      f"base={base_currency.upper()}).")


@app.command("list")
def cmd_list(
    include_archived: bool = typer.Option(False, "--all", "-a",
                                           help="Include archived portfolios."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List portfolios."""
    rows = _portfolios.list_all(include_archived=include_archived)
    if json_output:
        print(json.dumps(rows, default=str))
        return

    if not rows:
        console.print("[yellow]No portfolios.[/yellow] Create one with: "
                      "[cyan]pt portfolio create \"My Depot\"[/cyan]")
        return

    table = Table(title="Portfolios")
    table.add_column("ID", style="dim", justify="right")
    table.add_column("Name", style="cyan")
    table.add_column("Currency")
    table.add_column("Created")
    table.add_column("Archived")
    for r in rows:
        table.add_row(
            str(r["id"]),
            r["name"],
            r["base_currency"],
            r["created_at"].strftime("%Y-%m-%d") if r["created_at"] else "-",
            r["archived_at"].strftime("%Y-%m-%d") if r["archived_at"] else "-",
        )
    console.print(table)


@app.command("show")
def cmd_show(
    portfolio_id: int = typer.Argument(..., help="Portfolio id."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show details for one portfolio."""
    row = _portfolios.get(portfolio_id)
    if not row:
        if json_output:
            print(json.dumps({"error": "not_found",
                              "message": f"Portfolio id={portfolio_id} not found."}),
                  file=sys.stderr)
        else:
            console.print(f"[red]✗[/red] Portfolio id={portfolio_id} not found.")
        raise typer.Exit(3)

    if json_output:
        print(json.dumps(row, default=str))
        return

    for k, v in row.items():
        console.print(f"  [dim]{k}:[/dim] {v}")


@app.command("archive")
def cmd_archive(
    portfolio_id: int = typer.Argument(..., help="Portfolio id."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Archive a portfolio (soft, reversible by clearing archived_at)."""
    ok = _portfolios.archive(portfolio_id)
    if not ok:
        if json_output:
            print(json.dumps({"error": "not_found_or_archived"}), file=sys.stderr)
        else:
            console.print(f"[red]✗[/red] Portfolio id={portfolio_id} not found or already archived.")
        raise typer.Exit(3)
    if json_output:
        print(json.dumps({"ok": True, "id": portfolio_id}))
    else:
        console.print(f"[green]✓[/green] Portfolio id={portfolio_id} archived.")
