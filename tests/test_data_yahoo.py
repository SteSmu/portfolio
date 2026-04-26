"""Tests for the Yahoo Finance fetcher.

The fetcher wraps yfinance, which talks to Yahoo's internal endpoints. We avoid
hitting the network in CI by monkey-patching `yfinance.Ticker` with a fake whose
`history()` returns a controlled pandas DataFrame.

The single online integration test is gated on YAHOO_ONLINE=1 — flip it on
locally to confirm a real Yahoo round-trip when bumping yfinance.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest


# --- helpers -----------------------------------------------------------------

def _fake_history_df(rows):
    """Build a minimal pandas DataFrame in the shape yfinance.Ticker.history() returns."""
    import pandas as pd
    idx = pd.DatetimeIndex(
        [r["ts"] for r in rows], tz="UTC",
    )
    return pd.DataFrame(
        {
            "Open": [r["open"] for r in rows],
            "High": [r["high"] for r in rows],
            "Low": [r["low"] for r in rows],
            "Close": [r["close"] for r in rows],
            "Volume": [r.get("volume", 0) for r in rows],
        },
        index=idx,
    )


class _FakeTicker:
    def __init__(self, df):
        self._df = df

    def history(self, **kwargs):
        return self._df


# --- unit tests --------------------------------------------------------------

def test_fetch_time_series_shape_matches_twelve_data(monkeypatch):
    """Returned candle dicts must look like Twelve Data candles so
    `store.insert_candles` ingests both interchangeably."""
    from pt.data import yahoo

    df = _fake_history_df([
        {"ts": datetime(2026, 4, 22, tzinfo=timezone.utc),
         "open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5, "volume": 1234},
        {"ts": datetime(2026, 4, 23, tzinfo=timezone.utc),
         "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 2345},
    ])
    monkeypatch.setattr("yfinance.Ticker", lambda sym: _FakeTicker(df))

    candles = yahoo.fetch_time_series("NOVN.SW", days=2, db_symbol="NOVN")

    assert len(candles) == 2
    c = candles[0]
    assert c["symbol"] == "NOVN"          # db_symbol overrides the yahoo form
    assert c["interval"] == "1d"
    assert c["source"] == "yahoo"
    assert c["asset_type"] == "stock"
    assert c["close"] == 100.5
    assert c["time"].tzinfo is not None    # always UTC


def test_fetch_time_series_db_symbol_defaults_to_yahoo_symbol(monkeypatch):
    from pt.data import yahoo

    df = _fake_history_df([
        {"ts": datetime(2026, 4, 23, tzinfo=timezone.utc),
         "open": 1, "high": 1, "low": 1, "close": 1},
    ])
    monkeypatch.setattr("yfinance.Ticker", lambda sym: _FakeTicker(df))

    candles = yahoo.fetch_time_series("NVDA", days=1)
    assert candles[0]["symbol"] == "NVDA"


def test_fetch_time_series_raises_on_empty_history(monkeypatch):
    """Delisted symbols / wrong suffix → empty DataFrame → YahooFinanceError,
    never silent-empty success."""
    from pt.data import yahoo

    df = _fake_history_df([])
    monkeypatch.setattr("yfinance.Ticker", lambda sym: _FakeTicker(df))

    with pytest.raises(yahoo.YahooFinanceError, match="no data"):
        yahoo.fetch_time_series("NOPE.XX", days=5)


def test_fetch_time_series_wraps_yfinance_internal_errors(monkeypatch):
    """yfinance throws a grab bag — we wrap into YahooFinanceError so the
    sync route only catches one error type."""
    from pt.data import yahoo

    class BoomTicker:
        def history(self, **kw):
            raise RuntimeError("Yahoo internal hiccup")

    monkeypatch.setattr("yfinance.Ticker", lambda sym: BoomTicker())
    with pytest.raises(yahoo.YahooFinanceError, match="hiccup"):
        yahoo.fetch_time_series("NVDA", days=1)


def test_fetch_time_series_naive_timestamps_become_utc(monkeypatch):
    """Some Yahoo responses come back with tz-naive timestamps (rare but real).
    The fetcher must coerce to UTC, not store naive datetimes that confuse
    downstream timezone math."""
    import pandas as pd
    from pt.data import yahoo

    naive_idx = pd.DatetimeIndex([datetime(2026, 4, 23)])  # tz=None
    df = pd.DataFrame({
        "Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [0],
    }, index=naive_idx)
    monkeypatch.setattr("yfinance.Ticker", lambda sym: _FakeTicker(df))

    candles = yahoo.fetch_time_series("NVDA", days=1)
    assert candles[0]["time"].tzinfo is timezone.utc


# --- sync route fallback -----------------------------------------------------

def test_known_six_listing_skips_twelve_data_and_uses_yahoo(monkeypatch):
    """Symbols in _YAHOO_SYMBOL_MAP that map to a non-bare form are pre-routed
    to Yahoo — avoids burning a Twelve Data rate-limit slot on a call we know
    will fail. Regression-guard for the routing logic."""
    from pt.api.routes import sync as sync_route

    td_calls = []
    yh_calls = []

    def fake_td_fetch(*args, **kwargs):
        td_calls.append((args, kwargs))
        raise AssertionError("Twelve Data must NOT be called for SIX listings")

    def fake_yh_fetch(yahoo_symbol, **kw):
        yh_calls.append(yahoo_symbol)
        return [{"symbol": kw.get("db_symbol", yahoo_symbol).upper(),
                 "interval": "1d", "source": "yahoo"}]

    monkeypatch.setattr(sync_route._td, "fetch_time_series", fake_td_fetch)
    monkeypatch.setattr(sync_route._yh, "fetch_time_series", fake_yh_fetch)

    candles, src, td_err = sync_route._fetch_stock_with_fallback(
        "NOVN", days=5, asset_type="stock",
    )
    assert src == "yahoo"
    assert td_err is None
    assert yh_calls == ["NOVN.SW"]
    assert td_calls == []


def test_us_ticker_uses_twelve_data_first(monkeypatch):
    from pt.api.routes import sync as sync_route

    def fake_td_fetch(symbol, **kw):
        return [{"symbol": symbol.upper(), "source": "twelve_data"}]

    def fake_yh_fetch(*a, **kw):
        raise AssertionError("Yahoo must NOT be called when TD succeeds")

    monkeypatch.setattr(sync_route._td, "fetch_time_series", fake_td_fetch)
    monkeypatch.setattr(sync_route._yh, "fetch_time_series", fake_yh_fetch)

    candles, src, td_err = sync_route._fetch_stock_with_fallback(
        "NVDA", days=5, asset_type="stock",
    )
    assert src == "twelve_data"
    assert td_err is None


def test_twelve_data_error_falls_back_to_yahoo(monkeypatch):
    """When TD throws (rate-limit, paywall, etc.), Yahoo takes over and the
    TD error message rides along on the outcome row for UI surfacing."""
    from pt.api.routes import sync as sync_route

    def fake_td_fetch(symbol, **kw):
        raise sync_route._td.TwelveDataError("rate limit hit")

    def fake_yh_fetch(yahoo_symbol, **kw):
        return [{"symbol": kw.get("db_symbol", yahoo_symbol).upper(), "source": "yahoo"}]

    monkeypatch.setattr(sync_route._td, "fetch_time_series", fake_td_fetch)
    monkeypatch.setattr(sync_route._yh, "fetch_time_series", fake_yh_fetch)

    candles, src, td_err = sync_route._fetch_stock_with_fallback(
        "ORCL", days=5, asset_type="stock",
    )
    assert src == "yahoo"
    assert td_err == "rate limit hit"


def test_yahoo_symbol_map_us_passthrough():
    from pt.api.routes.sync import _yahoo_symbol

    assert _yahoo_symbol("NVDA") == "NVDA"
    assert _yahoo_symbol("amzn") == "AMZN"


def test_yahoo_symbol_map_known_overrides():
    from pt.api.routes.sync import _yahoo_symbol

    assert _yahoo_symbol("NOVN") == "NOVN.SW"
    assert _yahoo_symbol("ROG")  == "ROG.SW"
    assert _yahoo_symbol("SDZ")  == "SDZ.SW"
    assert _yahoo_symbol("AIR")  == "AIR.PA"


# --- optional online integration --------------------------------------------

@pytest.mark.skipif(
    os.getenv("YAHOO_ONLINE") != "1",
    reason="Set YAHOO_ONLINE=1 to hit real Yahoo (slow, network-dependent).",
)
def test_real_yahoo_fetch_for_novn_sw():
    from pt.data import yahoo

    candles = yahoo.fetch_time_series("NOVN.SW", days=5, db_symbol="NOVN")
    assert candles, "Yahoo returned no data for NOVN.SW"
    assert candles[0]["symbol"] == "NOVN"
    assert candles[0]["close"] > 0
