"""Daily portfolio-snapshot generator.

Writes one row per (portfolio_id, snapshot_date) into
`portfolio.portfolio_snapshots`. The frontend reads this back as a
time-series for the equity curve, drawdown view, and TWR sub-period
chaining.

Conventions:
  - Snapshots are computed at end-of-day (23:59:59.999999 UTC) so
    intraday transactions on `snapshot_date` are included.
  - Position values use the latest close at-or-before that moment from
    `public.candles` (FX-naive — all values stay in their source currency
    for now; cross-currency totals are flagged in the per-asset_type
    metadata breakdown so the frontend can render warnings).
  - Cost basis follows the FIFO method (matches the default of the
    performance routes).
  - Realized P&L is the running total of all sells whose
    `sell_executed_at <= snapshot_date_end`.
  - Unrealized P&L = total_value - open_cost_basis.
  - Idempotent: the upsert overwrites any prior row for the same
    (portfolio_id, snapshot_date), so re-running a backfill is safe.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from pt.db import portfolios as _portfolios
from pt.db import prices as _prices
from pt.db import transactions as _tx
from pt.db.connection import get_conn
from pt.performance import money as _money
from pt.performance.cost_basis import compute_lots, realized_pnl_total


# Single-tenant DB → minute-granularity not needed; date-based snapshots are enough.
_DAY_END = time(hour=23, minute=59, second=59, microsecond=999_999, tzinfo=timezone.utc)


@dataclass
class SnapshotRow:
    portfolio_id: int
    snapshot_date: date
    # `total_value` is None when the portfolio has open holdings on
    # `snapshot_date` but NONE could be priced (no candle at-or-before).
    # Storing 0 there is a lie — it would draw the equity curve down to
    # zero on every history-less day. Empty portfolios still get 0.
    total_value: Decimal | None
    total_cost_basis: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal | None
    cash: Decimal
    holdings_count: int
    metadata: dict
    # FX-aware total in the portfolio's base_currency. None when at least
    # one source-currency bucket has no Frankfurter rate path at-or-before
    # snapshot_date — callers must treat None as "FX rate gap, run
    # `pt sync fx`" rather than zero.
    total_value_base: Decimal | None = None


def _filter_at_or_before(txs: list[dict], end: datetime) -> list[dict]:
    """Drop any transaction executed strictly after `end`."""
    return [t for t in txs if t["executed_at"] <= end and t.get("deleted_at") is None]


def compute_snapshot(portfolio_id: int, snapshot_date: date) -> SnapshotRow:
    """Build a single snapshot for `snapshot_date` without writing it to the DB."""
    end = datetime.combine(snapshot_date, _DAY_END.replace(tzinfo=None), tzinfo=timezone.utc)

    # 1. All transactions up to and including snapshot_date.
    all_txs = _tx.list_for_portfolio(portfolio_id, limit=None)
    txs = _filter_at_or_before(all_txs, end)

    # 2. Cost-basis as-of `end` → open lots + realized matches.
    open_lots, matches = compute_lots(txs, method="fifo")
    realized = realized_pnl_total(matches)

    # 3. Quantity per symbol from the open lots (already deduped by symbol+lot).
    qty_per: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    cost_per: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    currency_per: dict[tuple[str, str], str] = {}
    for lot in open_lots:
        key = (lot.symbol, lot.asset_type)
        qty_per[key] += lot.quantity
        cost_per[key] += lot.cost_basis
        currency_per[key] = lot.currency

    # 4. Latest close at-or-before `end` for every key.
    keys = list(qty_per.keys())
    price_map = _prices.latest_close_many(keys, as_of=end) if keys else {}

    total_value_naive = Decimal("0")
    by_asset_type: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_currency: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    priced_count = 0
    open_holding_count = sum(1 for q in qty_per.values() if q > 0)
    for (sym, at), qty in qty_per.items():
        price, _ts = price_map.get((sym, at), (None, None))
        if price is None or qty <= 0:
            continue
        market_value = qty * price
        total_value_naive += market_value
        by_asset_type[at] += market_value
        ccy = currency_per.get((sym, at), "USD")
        by_currency[ccy] += market_value
        priced_count += 1

    # If we hold positions but priced none of them, the snapshot can't say
    # "the portfolio is worth 0" — it has to say "I don't know". Empty
    # portfolios (no open holdings) legitimately value at 0.
    if open_holding_count > 0 and priced_count == 0:
        total_value: Decimal | None = None
    else:
        total_value = total_value_naive

    open_cost = sum(cost_per.values(), Decimal("0"))
    if total_value is None:
        unrealized: Decimal | None = None
    else:
        unrealized = total_value - open_cost if total_value > 0 else Decimal("0")

    # FX-aware base-currency total: walk each source-currency bucket through
    # `money.convert(...)` and sum. If any single bucket has no rate path
    # the whole base-total is None — partial sums would be misleading
    # ("looks low" instead of "incomplete"). When `total_value` is None
    # (couldn't price ANY holding) the base total is None too — there's
    # nothing to convert.
    portfolio = _portfolios.get(portfolio_id)
    base_ccy = (portfolio or {}).get("base_currency") or "EUR"
    total_value_base: Decimal | None
    if total_value is None:
        total_value_base = None
    else:
        total_value_base = Decimal("0")
        for ccy, sub in by_currency.items():
            if total_value_base is None:
                break
            try:
                total_value_base += _money.convert(
                    sub, ccy, base_ccy, on_date=snapshot_date,
                )
            except (ValueError, LookupError):
                total_value_base = None
    # Empty portfolios still get base=0 (matches total_value=0).

    metadata = {
        "by_asset_type": {k: str(v) for k, v in by_asset_type.items()},
        "by_currency":   {k: str(v) for k, v in by_currency.items()},
        "priced_holdings": priced_count,
        "open_holdings": len(qty_per),
        "tx_total": len(txs),
        "base_currency": base_ccy,
    }

    return SnapshotRow(
        portfolio_id=portfolio_id,
        snapshot_date=snapshot_date,
        total_value=total_value,
        total_cost_basis=open_cost,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        # Cash isn't tracked yet (no deposit/withdrawal flow). Reserved for later.
        cash=Decimal("0"),
        holdings_count=len([k for k, q in qty_per.items() if q > 0]),
        metadata=metadata,
        total_value_base=total_value_base,
    )


def write_snapshot(row: SnapshotRow) -> None:
    """Upsert one snapshot row."""
    sql = """
    INSERT INTO portfolio.portfolio_snapshots
      (portfolio_id, snapshot_date, total_value, total_cost_basis,
       realized_pnl, unrealized_pnl, cash, holdings_count, metadata,
       total_value_base)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
    ON CONFLICT (portfolio_id, snapshot_date) DO UPDATE SET
      total_value      = EXCLUDED.total_value,
      total_cost_basis = EXCLUDED.total_cost_basis,
      realized_pnl     = EXCLUDED.realized_pnl,
      unrealized_pnl   = EXCLUDED.unrealized_pnl,
      cash             = EXCLUDED.cash,
      holdings_count   = EXCLUDED.holdings_count,
      metadata         = EXCLUDED.metadata,
      total_value_base = EXCLUDED.total_value_base
    """
    import json as _json
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, (
            row.portfolio_id, row.snapshot_date,
            row.total_value, row.total_cost_basis,
            row.realized_pnl, row.unrealized_pnl,
            row.cash, row.holdings_count,
            _json.dumps(row.metadata, default=str),
            row.total_value_base,
        ))
        conn.commit()


def write_today(portfolio_id: int) -> SnapshotRow:
    """Compute and persist today's snapshot. Idempotent (upsert)."""
    row = compute_snapshot(portfolio_id, date.today())
    write_snapshot(row)
    return row


def backfill(
    portfolio_id: int,
    days: int,
    end_date: date | None = None,
    dry_run: bool = False,
) -> list[SnapshotRow]:
    """Compute (and optionally persist) one snapshot per day for the last `days` days.

    The window is `[end_date - days + 1, end_date]` inclusive. Defaults to
    today. Returns the rows in chronological order.
    """
    end_date = end_date or date.today()
    rows: list[SnapshotRow] = []
    for offset in range(days):
        d = end_date - timedelta(days=days - 1 - offset)
        row = compute_snapshot(portfolio_id, d)
        if not dry_run:
            write_snapshot(row)
        rows.append(row)
    return rows


def list_snapshots(
    portfolio_id: int,
    start: date | None = None,
    end: date | None = None,
) -> list[dict]:
    """Read snapshots back as plain dicts, ordered chronologically."""
    where = ["portfolio_id = %s"]
    params: list = [portfolio_id]
    if start is not None:
        where.append("snapshot_date >= %s")
        params.append(start)
    if end is not None:
        where.append("snapshot_date <= %s")
        params.append(end)
    sql = f"""
    SELECT snapshot_date, total_value, total_cost_basis,
           realized_pnl, unrealized_pnl, cash, holdings_count, metadata,
           total_value_base
      FROM portfolio.portfolio_snapshots
     WHERE {' AND '.join(where)}
     ORDER BY snapshot_date ASC
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [
        {
            "date": r[0].isoformat(),
            "total_value": r[1],
            "total_cost_basis": r[2],
            "realized_pnl": r[3],
            "unrealized_pnl": r[4],
            "cash": r[5],
            "holdings_count": r[6],
            "metadata": r[7],
            "total_value_base": r[8],
        }
        for r in rows
    ]


def list_active_portfolios() -> Iterable[int]:
    """All non-archived portfolio ids — the cron path iterates these."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM portfolio.portfolios "
            "WHERE archived_at IS NULL ORDER BY id"
        )
        return [r[0] for r in cur.fetchall()]
