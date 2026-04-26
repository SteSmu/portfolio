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
                WHEN action = 'buy'  THEN  quantity * price + fees
                WHEN action = 'sell' THEN -(quantity * price - fees)
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
