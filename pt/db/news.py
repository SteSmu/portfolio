"""News storage helpers (asset_news table)."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from pt.db.connection import get_conn


def _row_to_dict(cur, row) -> dict:
    return dict(zip([d.name for d in cur.description], row))


def upsert_many(items: list[dict]) -> int:
    """Insert/upsert news rows. Returns number processed.

    Each item: {time, source, symbol, asset_type, title, summary, url, sentiment, metadata}.
    Idempotent on (source, url) — re-runs replace title/summary/sentiment.
    """
    if not items:
        return 0
    rows = [
        (
            it["time"],
            it["source"],
            it["symbol"],
            it["asset_type"],
            it["title"],
            it.get("summary"),
            it["url"],
            float(it["sentiment"]) if isinstance(it.get("sentiment"), Decimal) else it.get("sentiment"),
            json.dumps(it.get("metadata")) if it.get("metadata") is not None else None,
        )
        for it in items
        if it.get("url")
    ]
    if not rows:
        return 0
    sql = """
    INSERT INTO portfolio.asset_news
        (time, published_at, source, symbol, asset_type, title, summary,
         url, sentiment, metadata)
    VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (source, url) DO UPDATE SET
        title = EXCLUDED.title,
        summary = EXCLUDED.summary,
        sentiment = EXCLUDED.sentiment,
        metadata = EXCLUDED.metadata
    """
    # Note: schema uses `time` for fetched_at via DEFAULT NOW() but we store
    # the article's published_at. Re-check schema column names below.
    sql_corrected = """
    INSERT INTO portfolio.asset_news
        (published_at, source, symbol, asset_type, title, summary,
         url, sentiment, metadata, fetched_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    ON CONFLICT (source, url) DO UPDATE SET
        title = EXCLUDED.title,
        summary = EXCLUDED.summary,
        sentiment = EXCLUDED.sentiment,
        metadata = EXCLUDED.metadata,
        fetched_at = NOW()
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.executemany(sql_corrected, rows)
        conn.commit()
    return len(rows)


def list_for_symbol(
    symbol: str,
    asset_type: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Latest news for one symbol (newest first)."""
    sql = (
        "SELECT id, symbol, asset_type, published_at, source, title, summary, "
        "       url, sentiment, metadata, fetched_at "
        "FROM portfolio.asset_news WHERE symbol = %s"
    )
    params: list = [symbol.upper()]
    if asset_type:
        sql += " AND asset_type = %s"
        params.append(asset_type)
    sql += " ORDER BY published_at DESC LIMIT %s"
    params.append(limit)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_dict(cur, r) for r in cur.fetchall()]


def latest_fetched_at(symbol: str, asset_type: str) -> datetime | None:
    """When did we last refresh news for this asset?"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(fetched_at) FROM portfolio.asset_news "
            "WHERE symbol = %s AND asset_type = %s",
            (symbol.upper(), asset_type),
        )
        row = cur.fetchone()
    return row[0] if row else None


def avg_sentiment(symbol: str, asset_type: str, lookback_days: int = 14) -> Decimal | None:
    """Mean sentiment across recent news for this asset (None if no rated items)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT AVG(sentiment) FROM portfolio.asset_news "
            "WHERE symbol = %s AND asset_type = %s "
            "  AND sentiment IS NOT NULL "
            "  AND published_at > NOW() - INTERVAL '%s days'",
            (symbol.upper(), asset_type, lookback_days),
        )
        row = cur.fetchone()
    return Decimal(str(row[0])) if row and row[0] is not None else None
