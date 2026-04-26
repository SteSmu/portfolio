"""Performance routes (cost-basis, realized P&L, summary, time-series metrics)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query

from pt.db import transactions as _tx
from pt.jobs import snapshots as _snap
from pt.performance import metrics as _metrics
from pt.performance.cost_basis import compute_lots, realized_pnl_total
from pt.performance.mwr import xirr
from pt.performance.twr import Snapshot as TwrSnapshot
from pt.performance.twr import annualized_twr, twr

router = APIRouter(prefix="/portfolios/{portfolio_id}/performance", tags=["performance"])

_VALID_METHODS = {"fifo", "lifo", "average"}


def _load_tx(portfolio_id: int, symbol: str | None = None) -> list[dict]:
    return _tx.list_for_portfolio(portfolio_id=portfolio_id, symbol=symbol, limit=None)


def _validate_method(method: str) -> None:
    if method not in _VALID_METHODS:
        raise HTTPException(status_code=400,
                            detail=f"method must be one of {sorted(_VALID_METHODS)}, got {method!r}")


@router.get("/cost-basis")
def cost_basis(
    portfolio_id: int,
    method: str = Query("fifo"),
    symbol: str | None = None,
) -> dict:
    _validate_method(method)
    txs = _load_tx(portfolio_id, symbol=symbol)
    try:
        open_lots, matches = compute_lots(txs, method=method)  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "method": method,
        "open_lots": [_lot_dict(l) for l in open_lots],
        "matches": [_match_dict(m) for m in matches],
        "realized_pnl": realized_pnl_total(matches),
    }


@router.get("/realized")
def realized(
    portfolio_id: int,
    method: str = Query("fifo"),
    year: int | None = None,
) -> dict:
    _validate_method(method)
    txs = _load_tx(portfolio_id)
    try:
        _, matches = compute_lots(txs, method=method)  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if year is not None:
        matches = [m for m in matches if m.sell_executed_at.year == year]

    by_symbol: dict[str, Decimal] = {}
    by_holding: dict[str, Decimal] = {"short": Decimal("0"), "long": Decimal("0")}
    total = Decimal("0")
    for m in matches:
        by_symbol[m.symbol] = by_symbol.get(m.symbol, Decimal("0")) + m.realized_pnl
        bucket = "long" if m.holding_period_days >= 365 else "short"
        by_holding[bucket] += m.realized_pnl
        total += m.realized_pnl

    return {
        "year": year,
        "method": method,
        "total": total,
        "match_count": len(matches),
        "by_symbol": by_symbol,
        "by_holding_period": by_holding,
        "matches": [_match_dict(m) for m in matches],
    }


@router.get("/summary")
def summary(
    portfolio_id: int,
    method: str = Query("fifo"),
    start: date | None = Query(None, description="Lower bound for time-series metrics."),
    end:   date | None = Query(None, description="Upper bound for time-series metrics."),
) -> dict:
    """One-shot snapshot of the portfolio.

    Cost-basis aggregates are always present. Time-series metrics
    (TWR, MWR, drawdown, vola, Sharpe, Calmar) are filled in only when
    snapshots exist for the portfolio. The frontend can detect the null
    block and surface a "run `pt sync snapshots --backfill 365`" hint.
    """
    _validate_method(method)
    txs = _load_tx(portfolio_id)
    try:
        open_lots, matches = compute_lots(txs, method=method)  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    cost_basis_summary = {
        "tx_count": len(txs),
        "open_lot_count": len(open_lots),
        "open_cost_basis": sum((l.cost_basis for l in open_lots), Decimal("0")),
        "realized_pnl": realized_pnl_total(matches),
        "match_count": len(matches),
    }

    snapshots = _snap.list_snapshots(portfolio_id, start=start, end=end)

    timeseries: dict | None = None
    if len(snapshots) >= 2:
        twr_snaps = [
            TwrSnapshot(
                when=date.fromisoformat(s["date"]),
                value=s["total_value"],
                cash_flow=Decimal("0"),
            )
            for s in snapshots
            if s["total_value"] is not None
        ]
        try:
            twr_total = twr(twr_snaps)
            twr_ann = annualized_twr(twr_snaps)
            daily_returns = _metrics.daily_returns_from_snapshots(twr_snaps)
            vola = _metrics.volatility(daily_returns, periods_per_year=365)
            sharpe = _metrics.sharpe(daily_returns, periods_per_year=365)
            mdd = _metrics.max_drawdown(daily_returns)
            calmar = _metrics.calmar(daily_returns, periods_per_year=365)

            # MWR: cashflows from tx log + final value from latest snapshot
            mwr_value = _try_mwr(txs, terminal_date=twr_snaps[-1].when, terminal_value=twr_snaps[-1].value)

            timeseries = {
                "from": snapshots[0]["date"],
                "to":   snapshots[-1]["date"],
                "snapshot_count": len(snapshots),
                "twr_period": twr_total,
                "twr_annualized": twr_ann,
                "mwr": mwr_value,
                "max_drawdown": mdd,
                "volatility": vola,
                "sharpe": sharpe,
                "calmar": calmar,
            }
        except (ValueError, RuntimeError):
            # Bad math (e.g. all-zero portfolio) → leave timeseries null.
            timeseries = None

    return {
        "portfolio_id": portfolio_id,
        "method": method,
        **cost_basis_summary,
        "timeseries": timeseries,
    }


def _try_mwr(
    txs: list[dict],
    terminal_date: date,
    terminal_value: Decimal,
) -> Decimal | None:
    """Compute XIRR from tx log + terminal portfolio value. None on failure."""
    flows: list[tuple[date | datetime, Decimal | float]] = []
    for t in txs:
        if t.get("deleted_at") is not None:
            continue
        action = t["action"]
        qty = Decimal(t["quantity"])
        price = Decimal(t["price"])
        fees = Decimal(t.get("fees") or 0)
        when = t["executed_at"]
        if action in {"buy", "transfer_in"}:
            flows.append((when, -(qty * price + fees)))
        elif action in {"sell", "transfer_out"}:
            flows.append((when, qty * price - fees))
        elif action == "dividend":
            # dividends are cash you received — counts as positive flow if no
            # corresponding withdrawal is logged. Approx; refine when cash balance
            # tracking lands.
            flows.append((when, qty * price))
        else:
            continue
    if terminal_value > 0:
        # Use end-of-day for the terminal flow so it's strictly after the last tx.
        flows.append((datetime.combine(terminal_date, datetime.min.time(), tzinfo=timezone.utc), terminal_value))
    if len(flows) < 2:
        return None
    try:
        return xirr(flows)
    except (ValueError, RuntimeError):
        return None


def _lot_dict(lot) -> dict:
    return {
        "transaction_id": lot.transaction_id,
        "symbol": lot.symbol,
        "asset_type": lot.asset_type,
        "quantity": lot.quantity,
        "quantity_original": lot.quantity_original,
        "price": lot.price,
        "fees": lot.fees,
        "executed_at": lot.executed_at,
        "currency": lot.currency,
        "cost_basis": lot.cost_basis,
    }


def _match_dict(m) -> dict:
    return {
        "sell_transaction_id": m.sell_transaction_id,
        "lot_transaction_id": m.lot_transaction_id,
        "symbol": m.symbol,
        "asset_type": m.asset_type,
        "sold_quantity": m.sold_quantity,
        "cost_per_unit": m.cost_per_unit,
        "sell_price": m.sell_price,
        "sell_fees_allocated": m.sell_fees_allocated,
        "proceeds": m.proceeds,
        "cost": m.cost,
        "realized_pnl": m.realized_pnl,
        "holding_period_days": m.holding_period_days,
        "sell_executed_at": m.sell_executed_at,
        "buy_executed_at": m.buy_executed_at,
        "currency": m.currency,
    }
