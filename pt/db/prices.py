"""Latest-price helpers — read public.candles to value live holdings.

We don't compute anything fancy here: just the most recent close per
(symbol, asset_type), regardless of interval. Price freshness comes from
`as_of` on each row so the UI can warn when data is stale.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pt.db.connection import get_conn


def latest_close(symbol: str, asset_type: str) -> tuple[Decimal | None, datetime | None]:
    """Most recent (close, time) for one asset across any interval. None if no data."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT close, time
               FROM public.candles
               WHERE symbol = %s AND asset_type = %s
               ORDER BY time DESC
               LIMIT 1""",
            (symbol.upper(), asset_type),
        )
        row = cur.fetchone()
    if row is None:
        return None, None
    return Decimal(str(row[0])), row[1]


def latest_close_many(
    keys: list[tuple[str, str]],
) -> dict[tuple[str, str], tuple[Decimal | None, datetime | None]]:
    """Bulk version. Returns {(symbol, asset_type): (close, time)}."""
    if not keys:
        return {}
    keys_upper = [(s.upper(), t) for s, t in keys]
    placeholders = ",".join(["(%s,%s)"] * len(keys_upper))
    flat: list = []
    for s, t in keys_upper:
        flat.extend([s, t])

    sql = f"""
    SELECT DISTINCT ON (symbol, asset_type)
           symbol, asset_type, close, time
      FROM public.candles
     WHERE (symbol, asset_type) IN ({placeholders})
     ORDER BY symbol, asset_type, time DESC
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, flat)
        rows = cur.fetchall()

    out: dict[tuple[str, str], tuple[Decimal | None, datetime | None]] = {
        k: (None, None) for k in keys_upper
    }
    for sym, at, close, ts in rows:
        out[(sym, at)] = (Decimal(str(close)), ts)
    return out
