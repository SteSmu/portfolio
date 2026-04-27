"""Holdings — derived view aggregated from transactions.

Holdings are NEVER stored as a primary record; they are computed at query time
from the transactions table. This guarantees the transaction log is the single
source of truth (Sharesight-style architecture). Snapshot caching for dashboards
is handled separately by `pt sync snapshots`.

Aggregation per (portfolio_id, symbol, asset_type):
  - quantity      = SUM(buy.qty - sell.qty + transfer_in.qty - transfer_out.qty + split adjustments)
  - cost_basis    = SUM(buy.qty * buy.price + buy.fees - sell allocations) — FIFO/LIFO done in performance/cost_basis.py
  - last_buy_at, first_buy_at, last_tx_at
  - realized_pnl is intentionally NOT here (lives in performance/cost_basis.py)
"""

from __future__ import annotations

from decimal import Decimal

from pt.db.connection import get_conn


def _row_to_dict(cur, row) -> dict:
    return dict(zip([d.name for d in cur.description], row))


def list_for_portfolio(portfolio_id: int, include_zero: bool = False) -> list[dict]:
    """Aggregate transactions into current holdings.

    Returns list of dicts with: symbol, asset_type, quantity, total_cost,
    avg_cost, first_tx_at, last_tx_at, tx_count, currency.

    Note: avg_cost is a quick approximation (cost / quantity). Use
    `performance.cost_basis` for FIFO/LIFO-correct cost basis.
    """
    sql = """
    WITH movements AS (
        SELECT
            symbol,
            asset_type,
            trade_currency,
            executed_at,
            CASE
                WHEN action IN ('buy', 'transfer_in')   THEN  quantity
                WHEN action IN ('sell', 'transfer_out') THEN -quantity
                WHEN action = 'dividend'                THEN  0
                WHEN action = 'split'                   THEN  quantity
                WHEN action = 'fee'                     THEN  0
                ELSE 0
            END AS qty_delta,
            CASE
                WHEN action IN ('buy', 'transfer_in')   THEN  quantity * price + fees
                WHEN action IN ('sell', 'transfer_out') THEN -(quantity * price - fees)
                ELSE 0
            END AS cost_delta
        FROM portfolio.transactions
        WHERE portfolio_id = %s AND deleted_at IS NULL
    )
    SELECT
        symbol,
        asset_type,
        MAX(trade_currency) AS currency,
        SUM(qty_delta)      AS quantity,
        SUM(cost_delta)     AS total_cost,
        MIN(executed_at)    AS first_tx_at,
        MAX(executed_at)    AS last_tx_at,
        COUNT(*)            AS tx_count
    FROM movements
    GROUP BY symbol, asset_type
    """
    if not include_zero:
        sql += " HAVING SUM(qty_delta) > 0"
    sql += " ORDER BY symbol"

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, (portfolio_id,))
        rows = [_row_to_dict(cur, r) for r in cur.fetchall()]

    for row in rows:
        qty = row["quantity"] or Decimal("0")
        cost = row["total_cost"] or Decimal("0")
        row["avg_cost"] = (cost / qty) if qty > 0 else Decimal("0")
    return rows


def get_for_symbol(portfolio_id: int, symbol: str, asset_type: str) -> dict | None:
    """Single-symbol aggregate."""
    holdings = list_for_portfolio(portfolio_id, include_zero=True)
    for h in holdings:
        if h["symbol"] == symbol.upper() and h["asset_type"] == asset_type:
            return h
    return None


def list_for_portfolio_with_prices(
    portfolio_id: int, include_zero: bool = False,
) -> list[dict]:
    """Like list_for_portfolio() but enriched with latest market price.

    Adds per-row keys:
      - current_price        Decimal | None — latest close from public.candles
      - last_price_at        datetime | None — when that close was recorded
      - market_value         Decimal | None — quantity * current_price (native ccy)
      - unrealized_pnl       Decimal | None — market_value - total_cost (native ccy)
      - unrealized_pnl_pct   float    | None — unrealized_pnl / total_cost
      - market_value_base    Decimal | None — market_value FX-converted to the
                                              portfolio's base_currency
      - unrealized_pnl_base  Decimal | None — same conversion for P&L
      - total_cost_base      Decimal | None — same conversion for cost basis

    The `*_base` fields are None when the holding's source currency has no
    Frankfurter rate path at-or-before `last_price_at`. Frontend treats null
    as "FX gap, run `pt sync fx`" rather than zero.
    """
    from pt.db import portfolios as _portfolios
    from pt.db import prices as _prices
    from pt.performance import money as _money

    rows = list_for_portfolio(portfolio_id, include_zero=include_zero)
    if not rows:
        return rows

    portfolio = _portfolios.get(portfolio_id)
    base_ccy = (portfolio or {}).get("base_currency") or "EUR"

    keys = [(r["symbol"], r["asset_type"]) for r in rows]
    price_map = _prices.latest_close_many(keys)

    for r in rows:
        price, ts = price_map.get((r["symbol"], r["asset_type"]), (None, None))
        r["current_price"] = price
        r["last_price_at"] = ts
        if price is None or r["quantity"] is None:
            r["market_value"] = None
            r["unrealized_pnl"] = None
            r["unrealized_pnl_pct"] = None
            r["market_value_base"] = None
            r["unrealized_pnl_base"] = None
            r["total_cost_base"] = None
            continue
        market_value = r["quantity"] * price
        cost = r["total_cost"] or Decimal("0")
        unrealized = market_value - cost
        r["market_value"] = market_value
        r["unrealized_pnl"] = unrealized
        r["unrealized_pnl_pct"] = float(unrealized / cost) if cost > 0 else None

        src_ccy = (r.get("currency") or base_ccy).upper()
        on_date = ts.date() if ts is not None else None
        try:
            r["market_value_base"]   = _money.convert(market_value, src_ccy, base_ccy, on_date=on_date)
            r["unrealized_pnl_base"] = _money.convert(unrealized,   src_ccy, base_ccy, on_date=on_date)
            r["total_cost_base"]     = _money.convert(cost,         src_ccy, base_ccy, on_date=on_date)
        except (ValueError, LookupError):
            r["market_value_base"] = None
            r["unrealized_pnl_base"] = None
            r["total_cost_base"] = None
    return rows
