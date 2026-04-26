"""Persistence helpers for fetched market data.

Writes go to the public.candles hypertable (shared with claude-trader, with the
new asset_type/exchange columns) and the public.market_meta hypertable (used for
FX rates, fear & greed, etc.).

All inserts are upsert-style — same time/symbol/interval re-runs replace.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pt.db.connection import get_conn

_INSERT_CANDLE = """
INSERT INTO public.candles
    (time, symbol, interval, open, high, low, close, volume, trades,
     source, asset_type, exchange)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (time, symbol, interval) DO UPDATE SET
    open = EXCLUDED.open,
    high = EXCLUDED.high,
    low  = EXCLUDED.low,
    close = EXCLUDED.close,
    volume = EXCLUDED.volume,
    trades = EXCLUDED.trades,
    source = EXCLUDED.source,
    asset_type = EXCLUDED.asset_type,
    exchange = EXCLUDED.exchange
"""

_CANDLE_COLS = ("time", "symbol", "interval", "open", "high", "low", "close",
                "volume", "trades", "source", "asset_type", "exchange")


def _candle_to_tuple(c: dict) -> tuple:
    return tuple(c.get(k) for k in _CANDLE_COLS)


def insert_candles(candles: list[dict]) -> int:
    """Insert/upsert a batch of candle dicts. Returns the row count requested.

    Each dict needs at minimum: time, symbol, interval, open, high, low, close,
    volume. Optional: trades, source (default 'unknown'), asset_type
    (default 'crypto'), exchange.
    """
    if not candles:
        return 0
    rows = []
    for c in candles:
        c.setdefault("trades", None)
        c.setdefault("source", "unknown")
        c.setdefault("asset_type", "crypto")
        c.setdefault("exchange", None)
        rows.append(_candle_to_tuple(c))

    with get_conn() as conn, conn.cursor() as cur:
        cur.executemany(_INSERT_CANDLE, rows)
        conn.commit()
    return len(rows)


_INSERT_FX = """
INSERT INTO public.market_meta (time, source, symbol, value, metadata)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (time, source, symbol) DO UPDATE SET
    value = EXCLUDED.value,
    metadata = EXCLUDED.metadata
"""


def insert_fx_rates(rates: list[dict]) -> int:
    """Insert/upsert FX rates into market_meta.

    Each dict: time (datetime/date), source, symbol (e.g. 'EURUSD'),
    value (Decimal/float), metadata (dict|None).
    """
    if not rates:
        return 0
    import json as _json

    rows = [
        (
            r["time"],
            r["source"],
            r["symbol"],
            float(r["value"]) if isinstance(r["value"], Decimal) else r["value"],
            _json.dumps(r["metadata"]) if r.get("metadata") else None,
        )
        for r in rates
    ]
    with get_conn() as conn, conn.cursor() as cur:
        cur.executemany(_INSERT_FX, rows)
        conn.commit()
    return len(rows)


def latest_candle_time(symbol: str, interval: str, asset_type: str) -> datetime | None:
    """Latest candle timestamp for incremental backfill."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(time) FROM public.candles "
            "WHERE symbol = %s AND interval = %s AND asset_type = %s",
            (symbol, interval, asset_type),
        )
        row = cur.fetchone()
        return row[0] if row else None
