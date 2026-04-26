"""Portfolios CRUD — single-user-ready, multi-user-prepared (user_id NULLable)."""

from __future__ import annotations

from datetime import datetime

from pt.db.connection import get_conn

_COLS = "id, user_id, name, base_currency, created_at, archived_at"


def _row_to_dict(cur, row) -> dict:
    return dict(zip([d.name for d in cur.description], row))


def create(name: str, base_currency: str = "EUR", user_id: str | None = None) -> int:
    """Create a new portfolio. Returns its id."""
    if not name.strip():
        raise ValueError("Portfolio name must not be empty.")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO portfolio.portfolios (name, base_currency, user_id) "
            "VALUES (%s, %s, %s) RETURNING id",
            (name, base_currency.upper(), user_id),
        )
        pid = cur.fetchone()[0]
        conn.commit()
        return pid


def get(portfolio_id: int) -> dict | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {_COLS} FROM portfolio.portfolios WHERE id = %s", (portfolio_id,))
        row = cur.fetchone()
        return _row_to_dict(cur, row) if row else None


def get_by_name(name: str) -> dict | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLS} FROM portfolio.portfolios "
            "WHERE name = %s AND archived_at IS NULL "
            "ORDER BY created_at DESC LIMIT 1",
            (name,),
        )
        row = cur.fetchone()
        return _row_to_dict(cur, row) if row else None


def list_all(include_archived: bool = False) -> list[dict]:
    with get_conn() as conn, conn.cursor() as cur:
        sql = f"SELECT {_COLS} FROM portfolio.portfolios"
        if not include_archived:
            sql += " WHERE archived_at IS NULL"
        sql += " ORDER BY created_at"
        cur.execute(sql)
        rows = cur.fetchall()
        return [_row_to_dict(cur, r) for r in rows]


def archive(portfolio_id: int) -> bool:
    """Soft-archive a portfolio. Returns True if archived, False if not found / already archived."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE portfolio.portfolios SET archived_at = NOW() "
            "WHERE id = %s AND archived_at IS NULL",
            (portfolio_id,),
        )
        affected = cur.rowcount
        conn.commit()
        return affected > 0


def delete_hard(portfolio_id: int) -> int:
    """Hard-delete a portfolio AND its transactions/snapshots/import_log.

    Use with care — for tests and explicit user intent only. Returns count of
    deleted transactions.
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM portfolio.import_log WHERE portfolio_id = %s", (portfolio_id,))
        cur.execute(
            "DELETE FROM portfolio.transaction_audit WHERE transaction_id IN "
            "(SELECT id FROM portfolio.transactions WHERE portfolio_id = %s)",
            (portfolio_id,),
        )
        cur.execute(
            "DELETE FROM portfolio.transactions WHERE portfolio_id = %s",
            (portfolio_id,),
        )
        tx_count = cur.rowcount
        cur.execute(
            "DELETE FROM portfolio.portfolio_snapshots WHERE portfolio_id = %s",
            (portfolio_id,),
        )
        cur.execute("DELETE FROM portfolio.portfolios WHERE id = %s", (portfolio_id,))
        conn.commit()
        return tx_count
