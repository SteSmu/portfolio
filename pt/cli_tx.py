"""`pt tx` — transaction CRUD (manual entry, list, show audit trail).

Examples:
  pt tx add --portfolio 1 --symbol AAPL --asset-type stock \\
            --action buy --qty 10 --price 180.50 --currency USD \\
            --executed-at 2026-04-15
  pt tx list --portfolio 1
  pt tx list --portfolio 1 --symbol AAPL --json
  pt tx show 42
  pt tx audit 42                # audit-trail of changes
  pt tx delete 42 --yes         # soft-delete (audit preserved)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import typer
from dateutil import parser as dateparser
from rich.console import Console
from rich.table import Table

from pt.db import transactions as _tx

app = typer.Typer(help="Transactions: manual entry, listing, audit.", no_args_is_help=True)
console = Console()


def _parse_decimal(s: str, name: str) -> Decimal:
    try:
        return Decimal(s.replace(",", ".").replace("_", ""))
    except InvalidOperation as e:
        raise typer.BadParameter(f"{name}: cannot parse {s!r} as decimal.") from e


def _parse_datetime(s: str | None) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    dt = dateparser.parse(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@app.command("add")
def cmd_add(
    portfolio_id: int = typer.Option(..., "--portfolio", "-p", help="Portfolio id."),
    symbol: str = typer.Option(..., "--symbol", "-s", help="Asset symbol (e.g. AAPL, BTC)."),
    asset_type: str = typer.Option(..., "--asset-type", "-t",
                                    help="One of: crypto, stock, etf, fx, commodity, bond."),
    action: str = typer.Option("buy", "--action", "-a",
                                help="One of: buy, sell, dividend, split, fee, transfer_in, transfer_out, deposit, withdrawal."),
    quantity: str = typer.Option(..., "--qty", "-q", help="Quantity (decimal, e.g. 10 or 0.5)."),
    price: str = typer.Option(..., "--price", help="Price per unit in trade currency."),
    trade_currency: str = typer.Option(..., "--currency", "-c", help="Trade currency (USD, EUR, BTC...)."),
    executed_at: str | None = typer.Option(None, "--executed-at",
                                            help="ISO date or datetime, default = now (UTC)."),
    fees: str = typer.Option("0", "--fees", help="Fee amount."),
    fees_currency: str | None = typer.Option(None, "--fees-currency"),
    fx_rate: str | None = typer.Option(None, "--fx-rate", help="FX rate at trade time."),
    note: str | None = typer.Option(None, "--note"),
    source: str = typer.Option("manual", "--source"),
    changed_by: str | None = typer.Option(None, "--actor", help="Audit attribution (e.g. user email)."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Add a transaction to a portfolio."""
    qty = _parse_decimal(quantity, "qty")
    px = _parse_decimal(price, "price")
    fee_amt = _parse_decimal(fees, "fees")
    fx = _parse_decimal(fx_rate, "fx-rate") if fx_rate else None
    when = _parse_datetime(executed_at)

    try:
        tx_id = _tx.insert(
            portfolio_id=portfolio_id,
            symbol=symbol,
            asset_type=asset_type,
            action=action,
            executed_at=when,
            quantity=qty,
            price=px,
            trade_currency=trade_currency,
            fees=fee_amt,
            fees_currency=fees_currency,
            fx_rate=fx,
            note=note,
            source=source,
            changed_by=changed_by,
        )
    except ValueError as e:
        if json_output:
            print(json.dumps({"error": "usage", "message": str(e)}), file=sys.stderr)
        else:
            console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(2)

    if json_output:
        print(json.dumps({"ok": True, "id": tx_id}))
    else:
        console.print(f"[green]✓[/green] Transaction id={tx_id} added: "
                      f"{action} {qty} {symbol.upper()} @ {px} {trade_currency.upper()}.")


@app.command("list")
def cmd_list(
    portfolio_id: int = typer.Option(..., "--portfolio", "-p"),
    symbol: str | None = typer.Option(None, "--symbol", "-s"),
    action: str | None = typer.Option(None, "--action", "-a"),
    limit: int = typer.Option(100, "--limit", min=1, max=10000),
    include_deleted: bool = typer.Option(False, "--include-deleted"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List transactions for a portfolio (newest first)."""
    rows = _tx.list_for_portfolio(
        portfolio_id=portfolio_id,
        symbol=symbol,
        action=action,
        limit=limit,
        include_deleted=include_deleted,
    )
    if json_output:
        print(json.dumps(rows, default=str))
        return

    if not rows:
        console.print(f"[yellow]No transactions for portfolio {portfolio_id}.[/yellow]")
        return

    table = Table(title=f"Transactions (portfolio={portfolio_id}, n={len(rows)})")
    table.add_column("ID", justify="right", style="dim")
    table.add_column("When")
    table.add_column("Action")
    table.add_column("Symbol", style="cyan")
    table.add_column("Type")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Cur")
    table.add_column("Fees", justify="right")
    for r in rows:
        marker = "[strike]" if r.get("deleted_at") else ""
        end = "[/strike]" if r.get("deleted_at") else ""
        table.add_row(
            f"{marker}{r['id']}{end}",
            r["executed_at"].strftime("%Y-%m-%d") if r["executed_at"] else "-",
            r["action"],
            r["symbol"],
            r["asset_type"],
            f"{r['quantity']:g}",
            f"{r['price']:g}",
            r["trade_currency"],
            f"{r['fees']:g}",
        )
    console.print(table)


@app.command("show")
def cmd_show(
    tx_id: int = typer.Argument(...),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show a single transaction."""
    row = _tx.get(tx_id)
    if not row:
        if json_output:
            print(json.dumps({"error": "not_found"}), file=sys.stderr)
        else:
            console.print(f"[red]✗[/red] Transaction id={tx_id} not found.")
        raise typer.Exit(3)
    if json_output:
        print(json.dumps(row, default=str))
        return
    for k, v in row.items():
        console.print(f"  [dim]{k}:[/dim] {v}")


@app.command("audit")
def cmd_audit(
    tx_id: int = typer.Argument(...),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show audit trail for a transaction."""
    rows = _tx.audit_history(tx_id)
    if json_output:
        print(json.dumps(rows, default=str))
        return
    if not rows:
        console.print(f"[yellow]No audit entries for tx={tx_id}.[/yellow]")
        return
    table = Table(title=f"Audit trail (tx={tx_id})")
    table.add_column("When")
    table.add_column("Op")
    table.add_column("Actor")
    for r in rows:
        table.add_row(
            r["changed_at"].strftime("%Y-%m-%d %H:%M:%S") if r["changed_at"] else "-",
            r["operation"],
            r.get("changed_by") or "-",
        )
    console.print(table)


@app.command("delete")
def cmd_delete(
    tx_id: int = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    changed_by: str | None = typer.Option(None, "--actor"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Soft-delete a transaction (audit-trail preserved)."""
    if not yes:
        if not sys.stdin.isatty():
            msg = "Refusing destructive op without --yes (non-interactive shell)."
            if json_output:
                print(json.dumps({"error": "needs_confirmation", "message": msg}), file=sys.stderr)
            else:
                console.print(f"[red]✗[/red] {msg}")
            raise typer.Exit(2)
        confirm = typer.confirm(f"Soft-delete transaction {tx_id}?")
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    ok = _tx.soft_delete(tx_id, changed_by=changed_by)
    if not ok:
        if json_output:
            print(json.dumps({"error": "not_found_or_already_deleted"}), file=sys.stderr)
        else:
            console.print(f"[red]✗[/red] Transaction id={tx_id} not found or already deleted.")
        raise typer.Exit(3)
    if json_output:
        print(json.dumps({"ok": True, "id": tx_id}))
    else:
        console.print(f"[green]✓[/green] Transaction id={tx_id} soft-deleted.")
