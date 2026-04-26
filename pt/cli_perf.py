"""`pt perf` — performance analytics on a portfolio.

Examples:
  pt perf cost-basis --portfolio 1 --method fifo
  pt perf cost-basis --portfolio 1 --method fifo --symbol AAPL --json
  pt perf realized --portfolio 1                 # realized P&L all-time
  pt perf realized --portfolio 1 --year 2026     # year-filtered
  pt perf summary  --portfolio 1                 # open lots + realized totals

TWR/MWR/risk metrics need a value+cashflow snapshot series; once
`pt sync snapshots` exists we'll wire `pt perf metrics` here too.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal

import typer
from rich.console import Console
from rich.table import Table

from pt.db import transactions as _tx
from pt.performance.cost_basis import (
    CostBasisMethod,
    compute_lots,
    realized_pnl_total,
)
from pt.performance.money import quantize_money

app = typer.Typer(help="Performance analytics (cost-basis, realized P&L, metrics).",
                  no_args_is_help=True)
console = Console()


def _load_tx(portfolio_id: int, symbol: str | None = None) -> list[dict]:
    return _tx.list_for_portfolio(
        portfolio_id=portfolio_id, symbol=symbol, limit=None,
    )


def _serialize(obj):
    """JSON serializer for Decimal / datetime."""
    if isinstance(obj, Decimal):
        return str(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Type {type(obj)} not serializable")


@app.command("cost-basis")
def cmd_cost_basis(
    portfolio_id: int = typer.Option(..., "--portfolio", "-p"),
    method: str = typer.Option("fifo", "--method", "-m",
                                help="fifo | lifo | average"),
    symbol: str | None = typer.Option(None, "--symbol", "-s",
                                       help="Filter to one symbol."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show open tax lots + matched sells for a portfolio."""
    if method not in ("fifo", "lifo", "average"):
        msg = f"method must be fifo|lifo|average, got {method!r}"
        if json_output:
            print(json.dumps({"error": "usage", "message": msg}), file=sys.stderr)
        else:
            console.print(f"[red]✗[/red] {msg}")
        raise typer.Exit(2)

    txs = _load_tx(portfolio_id, symbol=symbol)
    try:
        open_lots, matches = compute_lots(txs, method=method)  # type: ignore[arg-type]
    except ValueError as e:
        if json_output:
            print(json.dumps({"error": "compute_failed", "message": str(e)}), file=sys.stderr)
        else:
            console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)

    if json_output:
        print(json.dumps({
            "method": method,
            "open_lots": [l.__dict__ for l in open_lots],
            "matches": [m.__dict__ for m in matches],
            "realized_pnl": realized_pnl_total(matches),
        }, default=_serialize))
        return

    if not open_lots and not matches:
        console.print(f"[yellow]No transactions for portfolio {portfolio_id}.[/yellow]")
        return

    if open_lots:
        t = Table(title=f"Open lots — method={method}")
        t.add_column("TxID", style="dim", justify="right")
        t.add_column("Symbol", style="cyan")
        t.add_column("Type")
        t.add_column("Acquired")
        t.add_column("Qty (rem)", justify="right")
        t.add_column("Unit cost", justify="right")
        t.add_column("Cost basis", justify="right")
        t.add_column("Cur")
        for lot in open_lots:
            t.add_row(
                str(lot.transaction_id), lot.symbol, lot.asset_type,
                lot.executed_at.strftime("%Y-%m-%d") if lot.executed_at else "-",
                f"{lot.quantity:g}",
                f"{quantize_money(lot.price, Decimal('0.0001'))}",
                f"{quantize_money(lot.cost_basis)}",
                lot.currency,
            )
        console.print(t)

    if matches:
        m_table = Table(title="Realized matches")
        m_table.add_column("Sell→Buy", style="dim")
        m_table.add_column("Symbol", style="cyan")
        m_table.add_column("Sold qty", justify="right")
        m_table.add_column("Cost", justify="right")
        m_table.add_column("Proceeds", justify="right")
        m_table.add_column("Realized P&L", justify="right")
        m_table.add_column("Days held", justify="right")
        for m in matches:
            pnl_color = "green" if m.realized_pnl >= 0 else "red"
            m_table.add_row(
                f"{m.sell_transaction_id}→{m.lot_transaction_id}",
                m.symbol,
                f"{m.sold_quantity:g}",
                f"{quantize_money(m.cost)}",
                f"{quantize_money(m.proceeds)}",
                f"[{pnl_color}]{quantize_money(m.realized_pnl)}[/{pnl_color}]",
                str(m.holding_period_days),
            )
        console.print(m_table)

        total = realized_pnl_total(matches)
        color = "green" if total >= 0 else "red"
        console.print(f"\n[bold]Realized P&L total:[/bold] [{color}]{quantize_money(total)}[/{color}]")


@app.command("realized")
def cmd_realized(
    portfolio_id: int = typer.Option(..., "--portfolio", "-p"),
    method: str = typer.Option("fifo", "--method", "-m"),
    year: int | None = typer.Option(None, "--year",
                                     help="Filter realized P&L to this calendar year."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Realized P&L summary (suitable for tax reporting)."""
    if method not in ("fifo", "lifo", "average"):
        if json_output:
            print(json.dumps({"error": "usage", "message": f"bad method {method!r}"}),
                  file=sys.stderr)
        else:
            console.print(f"[red]✗[/red] method must be fifo|lifo|average")
        raise typer.Exit(2)

    txs = _load_tx(portfolio_id)
    try:
        _, matches = compute_lots(txs, method=method)  # type: ignore[arg-type]
    except ValueError as e:
        if json_output:
            print(json.dumps({"error": "compute_failed", "message": str(e)}), file=sys.stderr)
        else:
            console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)

    if year is not None:
        matches = [m for m in matches if m.sell_executed_at.year == year]

    by_symbol: dict[str, Decimal] = {}
    by_holding_period: dict[str, Decimal] = {"short": Decimal("0"), "long": Decimal("0")}
    total = Decimal("0")
    for m in matches:
        by_symbol[m.symbol] = by_symbol.get(m.symbol, Decimal("0")) + m.realized_pnl
        bucket = "long" if m.holding_period_days >= 365 else "short"
        by_holding_period[bucket] += m.realized_pnl
        total += m.realized_pnl

    if json_output:
        print(json.dumps({
            "year": year, "method": method,
            "total": total, "by_symbol": by_symbol,
            "by_holding_period": by_holding_period,
            "match_count": len(matches),
        }, default=_serialize))
        return

    console.print(f"[bold]Realized P&L[/bold] (method={method}"
                  + (f", year={year}" if year else ", all-time")
                  + f", matches={len(matches)})")
    if not matches:
        console.print("[yellow]No realized matches in range.[/yellow]")
        return

    t = Table(title="By symbol")
    t.add_column("Symbol", style="cyan")
    t.add_column("Realized P&L", justify="right")
    for sym, pnl in sorted(by_symbol.items()):
        color = "green" if pnl >= 0 else "red"
        t.add_row(sym, f"[{color}]{quantize_money(pnl)}[/{color}]")
    console.print(t)

    console.print(f"\nShort-term (<1y): [yellow]{quantize_money(by_holding_period['short'])}[/yellow]")
    console.print(f"Long-term (≥1y):  [cyan]{quantize_money(by_holding_period['long'])}[/cyan]")
    color = "green" if total >= 0 else "red"
    console.print(f"[bold]Total:[/bold] [{color}]{quantize_money(total)}[/{color}]")


@app.command("summary")
def cmd_summary(
    portfolio_id: int = typer.Option(..., "--portfolio", "-p"),
    method: str = typer.Option("fifo", "--method", "-m"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """High-level performance overview for a portfolio."""
    txs = _load_tx(portfolio_id)
    try:
        open_lots, matches = compute_lots(txs, method=method)  # type: ignore[arg-type]
    except ValueError as e:
        if json_output:
            print(json.dumps({"error": "compute_failed", "message": str(e)}), file=sys.stderr)
        else:
            console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)

    open_count = len(open_lots)
    open_cost_basis = sum((l.cost_basis for l in open_lots), Decimal("0"))
    realized_pnl = realized_pnl_total(matches)

    if json_output:
        print(json.dumps({
            "portfolio_id": portfolio_id,
            "method": method,
            "open_lot_count": open_count,
            "open_cost_basis": open_cost_basis,
            "realized_pnl": realized_pnl,
            "match_count": len(matches),
            "tx_count": len(txs),
        }, default=_serialize))
        return

    console.print(f"[bold]Portfolio {portfolio_id} — Summary[/bold]")
    console.print(f"  Transactions:    {len(txs)}")
    console.print(f"  Open lots:       {open_count}")
    console.print(f"  Open cost basis: {quantize_money(open_cost_basis)}")
    color = "green" if realized_pnl >= 0 else "red"
    console.print(f"  Realized P&L:    [{color}]{quantize_money(realized_pnl)}[/{color}] "
                  f"({len(matches)} matched lots, method={method})")
