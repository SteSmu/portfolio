"""`pt sync` — refresh market data into the shared TimescaleDB.

Examples:
  pt sync fx                                # ECB FX rates (EUR base, all quotes)
  pt sync fx --base EUR --quote USD --quote CHF
  pt sync crypto --coin bitcoin --vs-currency usd --days 365
  pt sync stock AAPL --interval 1day --outputsize 365
  pt sync snapshots                         # today's snapshot for every active portfolio
  pt sync snapshots -p 1 --backfill 365    # rebuild last 365 days of snapshots for portfolio #1
  pt sync --json fx                         # machine-readable result

Each command is idempotent (upsert on time+symbol+interval, or on the
(portfolio_id, snapshot_date) compound key for snapshots).
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from typing import Optional

import httpx
import typer
from rich.console import Console

from pt.data import coingecko as _cg
from pt.data import frankfurter as _fx
from pt.data import store as _store
from pt.data import twelve_data as _td
from pt.jobs import snapshots as _snap

app = typer.Typer(help="Refresh market data (prices, FX) into TimescaleDB.",
                  no_args_is_help=True)
console = Console()


def _emit(json_output: bool, payload: dict, human_msg: str) -> None:
    if json_output:
        print(json.dumps(payload))
    else:
        console.print(human_msg)


def _emit_error(json_output: bool, message: str, exit_code: int = 1) -> None:
    if json_output:
        print(json.dumps({"ok": False, "error": message}), file=sys.stderr)
    else:
        console.print(f"[red]✗[/red] {message}")
    raise typer.Exit(exit_code)


@app.command("fx")
def cmd_fx(
    base: str = typer.Option("EUR", "--base", "-b", help="Base currency."),
    quote: list[str] = typer.Option([], "--quote", "-q",
                                     help="Quote currency (repeat for multiple). Empty = all ECB-supported."),
    days: int = typer.Option(0, "--days", min=0, max=3650,
                              help="If >0: backfill that many days. If 0: latest only."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Sync ECB FX rates from Frankfurter."""
    try:
        if days > 0:
            end = date.today()
            start = end - timedelta(days=days)
            payload = _fx.fetch_time_series(start, end, base=base, quotes=quote or None)
        else:
            payload = _fx.fetch_latest(base=base, quotes=quote or None)
    except httpx.HTTPError as e:
        _emit_error(json_output, f"Frankfurter request failed: {e}", exit_code=1)

    rows = _fx.to_market_meta_rows(payload)
    n = _store.insert_fx_rates(rows)
    _emit(
        json_output,
        {"ok": True, "source": "frankfurter", "base": base.upper(),
         "rows_written": n, "days": days},
        f"[green]✓[/green] Frankfurter: wrote {n} FX rate(s) (base={base.upper()}, days={days}).",
    )


@app.command("crypto")
def cmd_crypto(
    coin: str = typer.Option(..., "--coin", help="CoinGecko coin id (e.g. 'bitcoin')."),
    vs_currency: str = typer.Option("usd", "--vs-currency", "-c"),
    days: int = typer.Option(365, "--days", min=1, max=3650),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Sync OHLC candles for one crypto coin from CoinGecko."""
    try:
        candles = _cg.fetch_ohlc(coin, vs_currency, days)
    except httpx.HTTPError as e:
        _emit_error(json_output, f"CoinGecko request failed: {e}", exit_code=1)

    n = _store.insert_candles(candles)
    sym = candles[0]["symbol"] if candles else "?"
    interval = candles[0]["interval"] if candles else "?"
    _emit(
        json_output,
        {"ok": True, "source": "coingecko", "symbol": sym,
         "interval": interval, "rows_written": n, "days": days},
        f"[green]✓[/green] CoinGecko: wrote {n} {interval} candle(s) for {sym}.",
    )


@app.command("stock")
def cmd_stock(
    symbol: str = typer.Argument(..., help="Stock/ETF symbol (e.g. AAPL)."),
    interval: str = typer.Option("1day", "--interval", "-i",
                                  help="1min/5min/15min/30min/45min/1h/2h/4h/1day/1week/1month."),
    outputsize: int = typer.Option(365, "--outputsize", min=1, max=5000),
    asset_type: str = typer.Option("stock", "--asset-type", "-t",
                                    help="stock or etf."),
    exchange: Optional[str] = typer.Option(None, "--exchange", "-e"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Sync OHLCV bars for one stock/ETF from Twelve Data."""
    try:
        candles = _td.fetch_time_series(
            symbol, interval=interval, outputsize=outputsize,
            asset_type=asset_type, exchange=exchange,
        )
    except _td.TwelveDataError as e:
        _emit_error(json_output, str(e), exit_code=2)
    except httpx.HTTPError as e:
        _emit_error(json_output, f"Twelve Data request failed: {e}", exit_code=1)

    n = _store.insert_candles(candles)
    interval_norm = candles[0]["interval"] if candles else interval
    _emit(
        json_output,
        {"ok": True, "source": "twelve_data", "symbol": symbol.upper(),
         "interval": interval_norm, "rows_written": n},
        f"[green]✓[/green] Twelve Data: wrote {n} {interval_norm} bar(s) for {symbol.upper()}.",
    )


@app.command("snapshots")
def cmd_snapshots(
    portfolio_id: Optional[int] = typer.Option(
        None, "--portfolio", "-p",
        help="Snapshot only this portfolio. Omit to iterate all active portfolios."),
    backfill: int = typer.Option(
        0, "--backfill", min=0, max=3650,
        help="Rebuild the last N days of snapshots. 0 = today only."),
    end_date: Optional[str] = typer.Option(
        None, "--end-date",
        help="ISO date marking the last day to snapshot (default: today)."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Compute but don't write to the DB."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Generate portfolio_snapshots rows feeding the equity-curve / drawdown UI."""
    if portfolio_id is not None:
        targets = [portfolio_id]
    else:
        targets = list(_snap.list_active_portfolios())
        if not targets:
            _emit_error(json_output, "No active portfolios found.", exit_code=3)

    end = date.fromisoformat(end_date) if end_date else None
    summary: list[dict] = []
    total_rows = 0
    for pid in targets:
        if backfill > 0:
            rows = _snap.backfill(pid, days=backfill, end_date=end, dry_run=dry_run)
        else:
            today = end or date.today()
            row = _snap.compute_snapshot(pid, today)
            if not dry_run:
                _snap.write_snapshot(row)
            rows = [row]

        latest = rows[-1]
        summary.append({
            "portfolio_id": pid,
            "rows_written": 0 if dry_run else len(rows),
            "rows_computed": len(rows),
            "from": rows[0].snapshot_date.isoformat(),
            "to": latest.snapshot_date.isoformat(),
            "total_value": str(latest.total_value),
            "total_cost_basis": str(latest.total_cost_basis),
            "unrealized_pnl": str(latest.unrealized_pnl),
            "realized_pnl": str(latest.realized_pnl),
            "holdings_count": latest.holdings_count,
        })
        total_rows += len(rows)

    payload = {
        "ok": True,
        "dry_run": dry_run,
        "portfolios": len(targets),
        "rows": total_rows,
        "results": summary,
    }
    if json_output:
        print(json.dumps(payload, default=str))
    else:
        verb = "would write" if dry_run else "wrote"
        console.print(f"[green]✓[/green] Snapshots: {verb} {total_rows} row(s) "
                      f"across {len(targets)} portfolio(s).")
        for s in summary:
            console.print(
                f"  • portfolio #{s['portfolio_id']}: {s['rows_computed']} day(s) "
                f"[{s['from']} → {s['to']}], latest total_value={s['total_value']}, "
                f"holdings={s['holdings_count']}"
            )
