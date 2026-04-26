"""Transactions CRUD — soft-delete aware, audit-trigger handles audit-log writes.

The audit trigger reads `portfolio.changed_by` GUC to attribute changes to a
user/source. Set via `with_changed_by()` context manager.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal

from pt.db.connection import get_conn

VALID_ACTIONS = frozenset({
    "buy", "sell",
    "dividend", "split", "fee",
    "transfer_in", "transfer_out",
    "deposit", "withdrawal",
})

VALID_ASSET_TYPES = frozenset({"crypto", "stock", "etf", "fx", "commodity", "bond"})

_COLS = (
    "id, portfolio_id, symbol, asset_type, action, executed_at, "
    "quantity, price, trade_currency, fees, fees_currency, fx_rate, "
    "note, source, source_doc_id, imported_at, deleted_at"
)


def _row_to_dict(cur, row) -> dict:
    return dict(zip([d.name for d in cur.description], row))


@contextmanager
def with_changed_by(actor: str):
    """Set the audit-trail attribution for the lifetime of this connection.

    Usage:
        with with_changed_by("cli:stefan"):
            insert(...)
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('portfolio.changed_by', %s, true)", (actor,))
        try:
            yield conn
        finally:
            pass


def insert(
    portfolio_id: int,
    symbol: str,
    asset_type: str,
    action: str,
    executed_at: datetime,
    quantity: Decimal,
    price: Decimal,
    trade_currency: str,
    fees: Decimal = Decimal("0"),
    fees_currency: str | None = None,
    fx_rate: Decimal | None = None,
    note: str | None = None,
    source: str = "manual",
    source_doc_id: str | None = None,
    changed_by: str | None = None,
) -> int:
    """Insert a transaction. Validates action + asset_type. Returns new id."""
    if action not in VALID_ACTIONS:
        raise ValueError(f"Invalid action {action!r}. Allowed: {sorted(VALID_ACTIONS)}")
    if asset_type not in VALID_ASSET_TYPES:
        raise ValueError(f"Invalid asset_type {asset_type!r}. Allowed: {sorted(VALID_ASSET_TYPES)}")
    if quantity <= 0 and action in {"buy", "sell"}:
        raise ValueError(f"Quantity must be > 0 for {action} (got {quantity}).")
    if fees < 0:
        raise ValueError(f"Fees must be >= 0 (got {fees}).")

    with get_conn() as conn, conn.cursor() as cur:
        if changed_by:
            cur.execute("SELECT set_config('portfolio.changed_by', %s, true)", (changed_by,))
        cur.execute(
            """INSERT INTO portfolio.transactions
               (portfolio_id, symbol, asset_type, action, executed_at,
                quantity, price, trade_currency, fees, fees_currency,
                fx_rate, note, source, source_doc_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (
                portfolio_id, symbol.upper(), asset_type, action, executed_at,
                quantity, price, trade_currency.upper(), fees, fees_currency,
                fx_rate, note, source, source_doc_id,
            ),
        )
        tx_id = cur.fetchone()[0]
        conn.commit()
        return tx_id


def get(tx_id: int) -> dict | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {_COLS} FROM portfolio.transactions WHERE id = %s", (tx_id,))
        row = cur.fetchone()
        return _row_to_dict(cur, row) if row else None


def list_for_portfolio(
    portfolio_id: int,
    symbol: str | None = None,
    action: str | None = None,
    limit: int | None = 100,
    include_deleted: bool = False,
) -> list[dict]:
    """List transactions for a portfolio, newest first."""
    sql = f"SELECT {_COLS} FROM portfolio.transactions WHERE portfolio_id = %s"
    params: list = [portfolio_id]
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    if symbol:
        sql += " AND symbol = %s"
        params.append(symbol.upper())
    if action:
        sql += " AND action = %s"
        params.append(action)
    sql += " ORDER BY executed_at DESC, id DESC"
    if limit:
        sql += " LIMIT %s"
        params.append(limit)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_dict(cur, r) for r in cur.fetchall()]


def soft_delete(tx_id: int, changed_by: str | None = None) -> bool:
    """Mark a transaction as deleted (audit-trail preserved). Returns True if deleted."""
    with get_conn() as conn, conn.cursor() as cur:
        if changed_by:
            cur.execute("SELECT set_config('portfolio.changed_by', %s, true)", (changed_by,))
        cur.execute(
            "UPDATE portfolio.transactions SET deleted_at = NOW() "
            "WHERE id = %s AND deleted_at IS NULL",
            (tx_id,),
        )
        affected = cur.rowcount
        conn.commit()
        return affected > 0


def audit_history(tx_id: int) -> list[dict]:
    """Return audit-trail entries for a transaction (oldest first)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, transaction_id, operation, old_data, new_data, "
            "       changed_at, changed_by "
            "FROM portfolio.transaction_audit "
            "WHERE transaction_id = %s ORDER BY changed_at",
            (tx_id,),
        )
        return [_row_to_dict(cur, r) for r in cur.fetchall()]
