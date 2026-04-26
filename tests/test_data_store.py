"""Integration tests for pt.data.store — writes to public.candles + public.market_meta.

Uses synthetic symbols prefixed `_pt_test_` so claude-trader's BTCUSDT data
stays untouched. Cleanup removes only test rows.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture
def cleanup_candles():
    written: list[tuple[str, str]] = []

    def _track(symbol: str, interval: str):
        written.append((symbol, interval))
        return symbol

    yield _track

    if written:
        from pt.db.connection import get_conn
        with get_conn() as conn, conn.cursor() as cur:
            for sym, iv in written:
                cur.execute("DELETE FROM public.candles WHERE symbol = %s AND interval = %s",
                            (sym, iv))
            conn.commit()


@pytest.fixture
def cleanup_market_meta():
    written: list[str] = []

    def _track(symbol: str):
        written.append(symbol)
        return symbol

    yield _track

    if written:
        from pt.db.connection import get_conn
        with get_conn() as conn, conn.cursor() as cur:
            for sym in written:
                cur.execute("DELETE FROM public.market_meta WHERE symbol = %s "
                            "AND source = 'frankfurter'", (sym,))
            conn.commit()


def test_insert_candles_writes_with_asset_type_and_exchange(cleanup_candles):
    from pt.data import store

    sym = f"_PT_TEST_{uuid.uuid4().hex[:8].upper()}"
    cleanup_candles(sym, "1d")
    t = datetime(2026, 4, 25, tzinfo=timezone.utc)
    candles = [{
        "time": t, "symbol": sym, "interval": "1d",
        "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 1000.0,
        "source": "twelve_data", "asset_type": "stock", "exchange": "NASDAQ",
    }]
    n = store.insert_candles(candles)
    assert n == 1

    from pt.db.connection import get_conn
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT asset_type, exchange, close FROM public.candles "
                    "WHERE symbol = %s AND interval = '1d'", (sym,))
        row = cur.fetchone()
    assert row[0] == "stock"
    assert row[1] == "NASDAQ"
    assert row[2] == 105.0


def test_insert_candles_is_idempotent_upsert(cleanup_candles):
    from pt.data import store

    sym = f"_PT_TEST_{uuid.uuid4().hex[:8].upper()}"
    cleanup_candles(sym, "1d")
    t = datetime(2026, 4, 25, tzinfo=timezone.utc)
    base = {"time": t, "symbol": sym, "interval": "1d",
            "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 1000.0,
            "source": "test", "asset_type": "stock", "exchange": "X"}
    store.insert_candles([base])
    store.insert_candles([{**base, "close": 999.0}])  # upsert

    from pt.db.connection import get_conn
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT close FROM public.candles WHERE symbol = %s", (sym,))
        rows = cur.fetchall()
    assert len(rows) == 1  # no duplicate
    assert rows[0][0] == 999.0


def test_insert_candles_empty_list_is_zero():
    from pt.data import store
    assert store.insert_candles([]) == 0


def test_latest_candle_time_returns_max(cleanup_candles):
    from pt.data import store

    sym = f"_PT_TEST_{uuid.uuid4().hex[:8].upper()}"
    cleanup_candles(sym, "1d")
    t1 = datetime(2026, 4, 24, tzinfo=timezone.utc)
    t2 = datetime(2026, 4, 25, tzinfo=timezone.utc)
    base = lambda t: {"time": t, "symbol": sym, "interval": "1d",
                      "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0.0,
                      "source": "test", "asset_type": "stock", "exchange": "X"}
    store.insert_candles([base(t1), base(t2)])

    assert store.latest_candle_time(sym, "1d", "stock") == t2
    assert store.latest_candle_time("__nonexistent__", "1d", "stock") is None


def test_insert_fx_rates_round_trip(cleanup_market_meta):
    from pt.data import store

    sym = f"_PTFX{uuid.uuid4().hex[:6].upper()}"
    cleanup_market_meta(sym)
    rows = [{
        "time": datetime(2026, 4, 25, tzinfo=timezone.utc),
        "source": "frankfurter",
        "symbol": sym,
        "value": Decimal("1.0850"),
        "metadata": {"base": "EUR", "quote": "USD"},
    }]
    n = store.insert_fx_rates(rows)
    assert n == 1

    from pt.db.connection import get_conn
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT value, metadata FROM public.market_meta WHERE symbol = %s",
                    (sym,))
        row = cur.fetchone()
    assert row[0] == 1.085
    assert row[1] == {"base": "EUR", "quote": "USD"}


def test_insert_fx_rates_upsert_replaces_value(cleanup_market_meta):
    from pt.data import store

    sym = f"_PTFX{uuid.uuid4().hex[:6].upper()}"
    cleanup_market_meta(sym)
    base = {
        "time": datetime(2026, 4, 25, tzinfo=timezone.utc),
        "source": "frankfurter", "symbol": sym, "metadata": None,
    }
    store.insert_fx_rates([{**base, "value": Decimal("1.08")}])
    store.insert_fx_rates([{**base, "value": Decimal("1.09")}])

    from pt.db.connection import get_conn
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*), MAX(value) FROM public.market_meta WHERE symbol = %s",
                    (sym,))
        cnt, val = cur.fetchone()
    assert cnt == 1
    assert val == 1.09
