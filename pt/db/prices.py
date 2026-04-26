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
    as_of: datetime | None = None,
) -> dict[tuple[str, str], tuple[Decimal | None, datetime | None]]:
    """Bulk version. Returns {(symbol, asset_type): (close, time)}.

    If `as_of` is given, returns the most recent close at-or-before that
    moment per key (used by the snapshot backfill so historical days are
    valued with prices that were actually known at that date, not today's).
    """
    if not keys:
        return {}
    keys_upper = [(s.upper(), t) for s, t in keys]
    placeholders = ",".join(["(%s,%s)"] * len(keys_upper))
    flat: list = []
    for s, t in keys_upper:
        flat.extend([s, t])

    where_clauses = [f"(symbol, asset_type) IN ({placeholders})"]
    params: list = list(flat)
    if as_of is not None:
        where_clauses.append("time <= %s")
        params.append(as_of)

    sql = f"""
    SELECT DISTINCT ON (symbol, asset_type)
           symbol, asset_type, close, time
      FROM public.candles
     WHERE {' AND '.join(where_clauses)}
     ORDER BY symbol, asset_type, time DESC
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    out: dict[tuple[str, str], tuple[Decimal | None, datetime | None]] = {
        k: (None, None) for k in keys_upper
    }
    for sym, at, close, ts in rows:
        out[(sym, at)] = (Decimal(str(close)), ts)
    return out


def history(
    symbol: str,
    asset_type: str,
    start: datetime | None = None,
    end: datetime | None = None,
    interval: str | None = None,
    limit: int = 5000,
) -> list[dict]:
    """OHLCV history for one (symbol, asset_type), oldest first.

    - `interval` filters to a specific candle resolution (e.g. '1day'). When
      None, the highest-resolution daily-or-coarser bar wins per timestamp;
      the route preferring 'daily' should pass interval explicitly.
    - `limit` caps the row count to avoid blowing up the API response.
    """
    where = ["symbol = %s", "asset_type = %s"]
    params: list = [symbol.upper(), asset_type]
    if start is not None:
        where.append("time >= %s")
        params.append(start)
    if end is not None:
        where.append("time <= %s")
        params.append(end)
    if interval is not None:
        where.append("interval = %s")
        params.append(interval)

    sql = f"""
    SELECT time, open, high, low, close, volume, interval
      FROM public.candles
     WHERE {' AND '.join(where)}
     ORDER BY time ASC
     LIMIT {int(limit)}
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [
        {
            "time": r[0],
            "open": Decimal(str(r[1])) if r[1] is not None else None,
            "high": Decimal(str(r[2])) if r[2] is not None else None,
            "low":  Decimal(str(r[3])) if r[3] is not None else None,
            "close": Decimal(str(r[4])) if r[4] is not None else None,
            "volume": Decimal(str(r[5])) if r[5] is not None else None,
            "interval": r[6],
        }
        for r in rows
    ]
