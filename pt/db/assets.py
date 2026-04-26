"""Asset master CRUD — metadata per (symbol, asset_type)."""

from __future__ import annotations

import json

from pt.db.connection import get_conn

_COLS = (
    "symbol, asset_type, exchange, name, isin, wkn, currency, "
    "sector, region, metadata, updated_at"
)


def _row_to_dict(cur, row) -> dict:
    return dict(zip([d.name for d in cur.description], row))


def upsert(
    symbol: str,
    asset_type: str,
    name: str,
    currency: str,
    exchange: str | None = None,
    isin: str | None = None,
    wkn: str | None = None,
    sector: str | None = None,
    region: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Insert or update an asset master record."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO portfolio.assets
               (symbol, asset_type, exchange, name, isin, wkn, currency,
                sector, region, metadata, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
               ON CONFLICT (symbol, asset_type) DO UPDATE SET
                   exchange = EXCLUDED.exchange,
                   name     = EXCLUDED.name,
                   isin     = COALESCE(EXCLUDED.isin, portfolio.assets.isin),
                   wkn      = COALESCE(EXCLUDED.wkn,  portfolio.assets.wkn),
                   currency = EXCLUDED.currency,
                   sector   = COALESCE(EXCLUDED.sector, portfolio.assets.sector),
                   region   = COALESCE(EXCLUDED.region, portfolio.assets.region),
                   metadata = COALESCE(EXCLUDED.metadata, portfolio.assets.metadata),
                   updated_at = NOW()""",
            (
                symbol.upper(), asset_type, exchange, name, isin, wkn,
                currency.upper(), sector, region,
                json.dumps(metadata) if metadata else None,
            ),
        )
        conn.commit()


def get(symbol: str, asset_type: str) -> dict | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLS} FROM portfolio.assets WHERE symbol = %s AND asset_type = %s",
            (symbol.upper(), asset_type),
        )
        row = cur.fetchone()
        return _row_to_dict(cur, row) if row else None


def list_all(asset_type: str | None = None, search: str | None = None) -> list[dict]:
    sql = f"SELECT {_COLS} FROM portfolio.assets WHERE 1=1"
    params: list = []
    if asset_type:
        sql += " AND asset_type = %s"
        params.append(asset_type)
    if search:
        sql += " AND (symbol ILIKE %s OR name ILIKE %s OR isin = %s OR wkn = %s)"
        like = f"%{search}%"
        params += [like, like, search.upper(), search.upper()]
    sql += " ORDER BY symbol"

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_dict(cur, r) for r in cur.fetchall()]


def find_similar(query: str, limit: int = 5) -> list[dict]:
    """Fuzzy-match for 'did you mean?' UX."""
    sql = (
        f"SELECT {_COLS} FROM portfolio.assets "
        "WHERE symbol ILIKE %s OR name ILIKE %s "
        "ORDER BY symbol LIMIT %s"
    )
    like = f"%{query}%"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, (like, like, limit))
        return [_row_to_dict(cur, r) for r in cur.fetchall()]
