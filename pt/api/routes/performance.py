"""Performance routes (cost-basis, realized P&L, summary, time-series metrics, period KPIs)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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

# Period codes are also used by the frontend's PeriodSelector + useTimeRange hook.
# Keep the keys stable: changing them breaks the API contract.
_PERIOD_KEYS = ("1D", "1W", "1M", "3M", "YTD", "1Y", "ALL")


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
    year: int | None = Query(None,
                             description="Filter to sells whose sell_executed_at falls in this year. "
                                         "Equivalent to start=YYYY-01-01 & end=YYYY-12-31; ignored if start/end given."),
    start: date | None = Query(None, description="ISO date, inclusive lower bound on sell_executed_at."),
    end: date | None = Query(None, description="ISO date, inclusive upper bound on sell_executed_at."),
) -> dict:
    _validate_method(method)
    txs = _load_tx(portfolio_id)
    try:
        _, matches = compute_lots(txs, method=method)  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # year is shorthand for [Jan 1, Dec 31] when start/end are absent.
    if start is None and end is None and year is not None:
        start = date(year, 1, 1)
        end = date(year, 12, 31)

    if start is not None or end is not None:
        matches = [
            m for m in matches
            if (start is None or _as_date(m.sell_executed_at) >= start)
               and (end is None or _as_date(m.sell_executed_at) <= end)
        ]

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
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
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

    With start/end set, the time-series metrics are computed over the
    window. MWR clips tx-level cash-flows to the window and treats the
    starting portfolio value as a synthetic deposit at start_date — so a
    "1Y XIRR" answers "what return do I need to bridge start_value+
    period_cashflows to end_value?" rather than a lifetime IRR.
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
        cf_by_date = _cash_flows_by_date(txs)
        twr_snaps = [
            TwrSnapshot(
                when=date.fromisoformat(s["date"]),
                value=s["total_value"],
                cash_flow=cf_by_date.get(date.fromisoformat(s["date"]), Decimal("0")),
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

            # MWR over the same window. When start/end clip the snapshots,
            # the tx flows must be clipped too — otherwise a 1Y XIRR mixes
            # 5y of historical buys with 1y of mark-to-market change.
            mwr_value = _try_mwr(
                txs,
                terminal_date=twr_snaps[-1].when,
                terminal_value=twr_snaps[-1].value,
                window_start=date.fromisoformat(snapshots[0]["date"]) if start is not None else None,
                window_start_value=twr_snaps[0].value if start is not None else None,
            )

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


@router.get("/periods")
def periods(
    portfolio_id: int,
    method: str = Query("fifo"),
) -> dict:
    """Multi-period KPIs (1D / 1W / 1M / 3M / YTD / 1Y / ALL) in one call.

    Each period reports a cashflow-clean delta — i.e. a fresh 16k buy on
    a 12k portfolio is NOT booked as a +130% gain. The math reuses the
    same `_cash_flows_by_date` helper that the TWR engine consumes.

    `mode` is `'base'` when every snapshot in the window has a
    `total_value_base` (FX-converted into the portfolio's base currency)
    and `'naive'` otherwise. `start_value`/`end_value`/`abs_change` /
    `cashflow` follow that mode; `twr_pct` and `simple_pct` are
    currency-agnostic ratios.

    Empty `periods` if fewer than two snapshots are available — the UI
    surfaces a "generate snapshots" CTA in that case.
    """
    _validate_method(method)
    txs = _load_tx(portfolio_id)
    snapshots = _snap.list_snapshots(portfolio_id)

    if len(snapshots) < 2:
        return {
            "as_of": snapshots[-1]["date"] if snapshots else None,
            "base_currency": _base_currency(snapshots),
            "periods": {},
        }

    cf_by_date = _cash_flows_by_date(txs)

    try:
        _, matches = compute_lots(txs, method=method)  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    today = date.fromisoformat(snapshots[-1]["date"])
    base_ccy = _base_currency(snapshots)

    out: dict[str, dict] = {}
    for code in _PERIOD_KEYS:
        kpi = _compute_period_kpi(
            snapshots=snapshots,
            cf_by_date=cf_by_date,
            matches=matches,
            period_code=code,
            end_date=today,
        )
        if kpi is not None:
            out[code] = kpi

    return {
        "as_of": today.isoformat(),
        "base_currency": base_ccy,
        "periods": out,
    }


# -------------------- helpers --------------------------------------------------


def _as_date(d: date | datetime) -> date:
    return d.date() if isinstance(d, datetime) else d


def _base_currency(snapshots: list[dict]) -> str:
    if not snapshots:
        return "EUR"
    meta = snapshots[-1].get("metadata") or {}
    return meta.get("base_currency", "EUR")


def _period_start_date(today: date, code: str) -> date | None:
    """Return the inclusive lower bound for a Period code; None for ALL."""
    if code == "ALL":
        return None
    if code == "1D":
        return today - timedelta(days=1)
    if code == "1W":
        return today - timedelta(days=7)
    if code == "1M":
        return _shift_months(today, -1)
    if code == "3M":
        return _shift_months(today, -3)
    if code == "YTD":
        return date(today.year, 1, 1)
    if code == "1Y":
        return _shift_months(today, -12)
    raise ValueError(f"unknown period code {code!r}")


def _shift_months(d: date, months: int) -> date:
    """Calendar-month shift, clamping to month-end where the day doesn't exist
    (e.g. 2026-01-31 minus one month → 2025-12-31, not Feb 31)."""
    m = d.month + months
    y = d.year
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    # Clamp day to last valid day of the target month.
    if m == 12:
        last = 31
    else:
        last = (date(y, m + 1, 1) - timedelta(days=1)).day
    return date(y, m, min(d.day, last))


def _snap_at_or_before(snapshots: list[dict], target: date) -> dict | None:
    """Pick the latest snapshot whose date is <= target. None if none."""
    found = None
    for s in snapshots:
        if date.fromisoformat(s["date"]) <= target:
            found = s
        else:
            break
    return found


def _compute_period_kpi(
    *,
    snapshots: list[dict],
    cf_by_date: dict[date, Decimal],
    matches: list,
    period_code: str,
    end_date: date,
) -> dict | None:
    """Build one period block. Returns None when there's no usable baseline."""
    period_start = _period_start_date(end_date, period_code)
    if period_start is None:
        # ALL: anchor to the first snapshot with a real value.
        baseline = next((s for s in snapshots if s.get("total_value") is not None), None)
        if baseline is None:
            return None
    else:
        # Clamp 1D / 1W / etc. to the first snapshot if we don't have history yet.
        baseline = _snap_at_or_before(snapshots, period_start)
        if baseline is None:
            baseline = next((s for s in snapshots if s.get("total_value") is not None), None)
            if baseline is None:
                return None

    end_snap = snapshots[-1]
    if end_snap.get("total_value") is None:
        return None

    baseline_d = date.fromisoformat(baseline["date"])
    end_d = date.fromisoformat(end_snap["date"])
    if baseline_d == end_d:
        return None

    use_base = (
        baseline.get("total_value_base") is not None
        and end_snap.get("total_value_base") is not None
    )

    sv = Decimal(baseline["total_value_base"] if use_base else baseline["total_value"])
    ev = Decimal(end_snap["total_value_base"] if use_base else end_snap["total_value"])
    if sv <= 0:
        return None

    # Cashflows in (baseline_d, end_d] — strictly after baseline so the
    # baseline value still represents the period's opening level.
    cashflow = Decimal("0")
    for d, amt in cf_by_date.items():
        if baseline_d < d <= end_d:
            cashflow += amt

    abs_change = ev - sv - cashflow
    simple_pct = abs_change / sv if sv > 0 else Decimal("0")

    # TWR over the window — uses FX-naive total_value to stay consistent
    # with cashflows (which are in source currencies). Mixed-currency
    # portfolios get a slightly different mode-vs-percent presentation
    # in the UI; until a base-currency cashflow flow exists, this is the
    # best we can do without quietly overstating returns.
    window_snaps = [
        s for s in snapshots
        if baseline_d <= date.fromisoformat(s["date"]) <= end_d
        and s.get("total_value") is not None
    ]
    twr_snaps = [
        TwrSnapshot(
            when=date.fromisoformat(s["date"]),
            value=Decimal(s["total_value"]),
            cash_flow=cf_by_date.get(date.fromisoformat(s["date"]), Decimal("0")),
        )
        for s in window_snaps
    ]
    twr_pct: Decimal | None
    try:
        twr_pct = twr(twr_snaps) if len(twr_snaps) >= 2 else Decimal("0")
    except (ValueError, RuntimeError):
        twr_pct = None

    realized_in_period = sum(
        (m.realized_pnl for m in matches
         if baseline_d < _as_date(m.sell_executed_at) <= end_d),
        Decimal("0"),
    )

    return {
        "from": baseline_d.isoformat(),
        "to": end_d.isoformat(),
        "start_value": sv,
        "end_value": ev,
        "abs_change": abs_change,
        "simple_pct": simple_pct,
        "twr_pct": twr_pct,
        "cashflow": cashflow,
        "realized": realized_in_period,
        "mode": "base" if use_base else "naive",
    }


def _cash_flows_by_date(txs: list[dict]) -> dict[date, Decimal]:
    """Bucket external cash-flows per execution date.

    Convention used by `pt.performance.twr.Snapshot.cash_flow`: positive =
    money entering the portfolio (buy / transfer_in), negative = leaving
    (sell / transfer_out). This tracker has no cash position, so every
    buy is fresh capital — see the call-site comment for why feeding 0
    here breaks TWR.

    Skips deleted rows. Dividends count as inflows (cash credit you received,
    no corresponding sell), matching the MWR convention in `_try_mwr`.
    """
    out: dict[date, Decimal] = {}
    for t in txs:
        if t.get("deleted_at") is not None:
            continue
        action = t.get("action")
        try:
            qty = Decimal(t["quantity"])
            price = Decimal(t["price"])
            fees = Decimal(t.get("fees") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        when = t["executed_at"]
        # Snapshots are bucketed by date (UTC), so flatten datetimes.
        if isinstance(when, datetime):
            d = when.date()
        elif isinstance(when, date):
            d = when
        else:
            d = date.fromisoformat(str(when)[:10])
        if action in {"buy", "transfer_in"}:
            cf = qty * price + fees
        elif action in {"sell", "transfer_out"}:
            cf = -(qty * price - fees)
        elif action == "dividend":
            cf = qty * price
        else:
            continue
        out[d] = out.get(d, Decimal("0")) + cf
    return out


def _try_mwr(
    txs: list[dict],
    terminal_date: date,
    terminal_value: Decimal,
    *,
    window_start: date | None = None,
    window_start_value: Decimal | None = None,
) -> Decimal | None:
    """Compute XIRR from tx log + terminal portfolio value. None on failure.

    Window-aware: when ``window_start`` and ``window_start_value`` are
    both provided, tx-cashflows BEFORE the window are dropped and the
    window's starting value is treated as a synthetic deposit at
    ``window_start``. The result is "the IRR you'd need to bridge the
    starting value plus in-window cashflows up to the terminal value".
    """
    flows: list[tuple[date | datetime, Decimal | float]] = []

    if window_start is not None and window_start_value is not None and window_start_value > 0:
        flows.append((
            datetime.combine(window_start, datetime.min.time(), tzinfo=timezone.utc),
            -Decimal(window_start_value),
        ))

    for t in txs:
        if t.get("deleted_at") is not None:
            continue
        action = t["action"]
        qty = Decimal(t["quantity"])
        price = Decimal(t["price"])
        fees = Decimal(t.get("fees") or 0)
        when = t["executed_at"]
        when_d = _as_date(when)
        if window_start is not None and when_d <= window_start:
            # Pre-window flows are absorbed into the synthetic starting-value
            # deposit above; including them here would double-count.
            continue
        if when_d > terminal_date:
            continue
        if action in {"buy", "transfer_in"}:
            flows.append((when, -(qty * price + fees)))
        elif action in {"sell", "transfer_out"}:
            flows.append((when, qty * price - fees))
        elif action == "dividend":
            flows.append((when, qty * price))
        else:
            continue

    if terminal_value > 0:
        flows.append((
            datetime.combine(terminal_date, datetime.min.time(), tzinfo=timezone.utc),
            terminal_value,
        ))

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
