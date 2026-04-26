"""Yahoo Finance fetcher via yfinance — fallback when Twelve Data can't serve.

Free, no API key. yfinance scrapes Yahoo Finance internal endpoints, so this
is unofficial — we keep it as a fallback rather than the primary stock source
because Yahoo can change response shape any day.

Primary use: SIX Swiss listings (NOVN.SW, ROG.SW, SDZ.SW) which Twelve Data
Free Tier doesn't carry. Yahoo handles the bulk of European exchanges via
suffixes (.SW Switzerland, .PA Paris, .DE Xetra, .L London, .AS Amsterdam,
.MI Milan, ...). US tickers also work bare on Yahoo, so this is a viable
universal fallback.

The shape of returned candle dicts matches `pt.data.twelve_data.fetch_time_series`
so `pt.data.store.insert_candles` can ingest both interchangeably.
"""

from __future__ import annotations

from datetime import datetime, timezone


class YahooFinanceError(RuntimeError):
    pass


def fetch_time_series(
    yahoo_symbol: str,
    *,
    days: int = 30,
    asset_type: str = "stock",
    db_symbol: str | None = None,
    exchange: str | None = None,
) -> list[dict]:
    """Daily OHLCV candles for one Yahoo symbol.

    Args:
        yahoo_symbol: Yahoo Finance form, e.g. ``NOVN.SW`` for Novartis SIX
            or ``AAPL`` for US listings.
        days: number of trailing trading days to fetch.
        asset_type: stored on each candle row for the holdings join.
        db_symbol: the symbol that should be persisted in our `candles` table
            (so the holdings lookup keyed off `(symbol, asset_type)` matches
            our transaction.symbol). Defaults to ``yahoo_symbol`` uppercased.
        exchange: stored as the candle's ``exchange`` column for traceability.

    Raises:
        YahooFinanceError: if Yahoo returns no data for the symbol (delisted,
            wrong suffix, geo-blocked, …) or yfinance is missing.
    """
    if days < 1:
        raise ValueError("days must be >= 1")
    try:
        import yfinance as yf  # local import: not all environments install it
    except ImportError as e:
        raise YahooFinanceError(
            "yfinance not installed. `pip install yfinance` (already in pyproject)."
        ) from e

    ticker = yf.Ticker(yahoo_symbol)
    # Use period= rather than start/end to let Yahoo round to its own
    # trading-day calendar — avoids weekend/holiday off-by-ones.
    period = f"{max(days, 1)}d"
    try:
        hist = ticker.history(period=period, interval="1d", auto_adjust=False)
    except Exception as e:  # yfinance raises a grab bag of HTTP/parse errors
        raise YahooFinanceError(f"yfinance fetch failed for {yahoo_symbol!r}: {e}") from e

    if hist is None or hist.empty:
        raise YahooFinanceError(
            f"no data for {yahoo_symbol!r} — delisted, wrong suffix, or rate-limited?"
        )

    stored = (db_symbol or yahoo_symbol).upper()
    out: list[dict] = []
    for ts, row in hist.iterrows():
        # pandas Timestamp may be tz-aware (Yahoo emits exchange-local) or naive.
        py_ts = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        if py_ts.tzinfo is None:
            py_ts = py_ts.replace(tzinfo=timezone.utc)
        else:
            py_ts = py_ts.astimezone(timezone.utc)
        out.append({
            "time": py_ts,
            "symbol": stored,
            "interval": "1d",
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row.get("Volume") or 0),
            "source": "yahoo",
            "asset_type": asset_type,
            "exchange": exchange,
        })
    return out
