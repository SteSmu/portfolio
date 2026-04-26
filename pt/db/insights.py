"""Insights storage helpers (asset_insights table)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from pt.db.connection import get_conn


def _row_to_dict(cur, row) -> dict:
    return dict(zip([d.name for d in cur.description], row))


def insert(
    symbol: str,
    asset_type: str,
    insight_type: str,
    content: str,
    model: str,
    valid_for: timedelta = timedelta(days=7),
    metadata: dict | None = None,
) -> int:
    """Persist a generated insight. Older entries of the same type are kept
    (history) but only the most recent valid one is surfaced by `latest_valid`.
    """
    valid_until = datetime.now(timezone.utc) + valid_for
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO portfolio.asset_insights
               (symbol, asset_type, insight_type, content, model,
                valid_until, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                symbol.upper(), asset_type, insight_type, content, model,
                valid_until,
                json.dumps(metadata) if metadata is not None else None,
            ),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return new_id


def latest_valid(
    symbol: str,
    asset_type: str,
    insight_type: str | None = None,
) -> dict | None:
    """Return the freshest unexpired insight for the asset (any type if not given)."""
    sql = (
        "SELECT id, symbol, asset_type, insight_type, content, model, "
        "       generated_at, valid_until, metadata "
        "FROM portfolio.asset_insights "
        "WHERE symbol = %s AND asset_type = %s AND valid_until > NOW()"
    )
    params: list = [symbol.upper(), asset_type]
    if insight_type:
        sql += " AND insight_type = %s"
        params.append(insight_type)
    sql += " ORDER BY generated_at DESC LIMIT 1"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return _row_to_dict(cur, row) if row else None


def list_for_symbol(
    symbol: str,
    asset_type: str,
    include_expired: bool = False,
    limit: int = 20,
) -> list[dict]:
    sql = (
        "SELECT id, symbol, asset_type, insight_type, content, model, "
        "       generated_at, valid_until, metadata "
        "FROM portfolio.asset_insights "
        "WHERE symbol = %s AND asset_type = %s"
    )
    if not include_expired:
        sql += " AND valid_until > NOW()"
    sql += " ORDER BY generated_at DESC LIMIT %s"
    params: list = [symbol.upper(), asset_type, limit]
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_dict(cur, r) for r in cur.fetchall()]


def delete(insight_id: int) -> bool:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM portfolio.asset_insights WHERE id = %s", (insight_id,))
        affected = cur.rowcount
        conn.commit()
        return affected > 0
