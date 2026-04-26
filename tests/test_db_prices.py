"""Latest-price helpers — read public.candles by (symbol, asset_type)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture
def candle_writer():
    """Write synthetic candles, clean them up at teardown."""
    written: list[tuple[str, str]] = []

    def _write(symbol: str, asset_type: str, when: datetime, close: float):
        from pt.data import store
        store.insert_candles([{
            "time": when, "symbol": symbol.upper(), "interval": "1d",
            "open": close, "high": close, "low": close, "close": close, "volume": 0.0,
            "source": "test", "asset_type": asset_type, "exchange": "test",
        }])
        written.append((symbol.upper(), "1d"))
        return symbol.upper()

    yield _write

    if written:
        from pt.db.connection import get_conn
        with get_conn() as conn, conn.cursor() as cur:
            for sym, iv in written:
                cur.execute("DELETE FROM public.candles "
                            "WHERE symbol = %s AND interval = %s AND source = 'test'",
                            (sym, iv))
            conn.commit()


def test_latest_close_returns_most_recent(candle_writer):
    from pt.db import prices

    sym = f"_PRICE_{uuid.uuid4().hex[:6].upper()}"
    candle_writer(sym, "stock", datetime(2026, 4, 24, tzinfo=timezone.utc), 100.0)
    candle_writer(sym, "stock", datetime(2026, 4, 25, tzinfo=timezone.utc), 105.0)
    candle_writer(sym, "stock", datetime(2026, 4, 23, tzinfo=timezone.utc), 95.0)

    close, ts = prices.latest_close(sym, "stock")
    assert close == Decimal("105")
    assert ts == datetime(2026, 4, 25, tzinfo=timezone.utc)


def test_latest_close_returns_none_for_unknown_asset():
    from pt.db import prices
    close, ts = prices.latest_close("__never_existed__", "stock")
    assert close is None
    assert ts is None


def test_latest_close_many_bulk(candle_writer):
    from pt.db import prices

    a = f"_PRICE_{uuid.uuid4().hex[:6].upper()}"
    b = f"_PRICE_{uuid.uuid4().hex[:6].upper()}"
    candle_writer(a, "stock", datetime(2026, 4, 25, tzinfo=timezone.utc), 100.0)
    candle_writer(b, "crypto", datetime(2026, 4, 25, tzinfo=timezone.utc), 60_000.0)

    out = prices.latest_close_many([(a, "stock"), (b, "crypto"), ("__none__", "stock")])
    assert out[(a, "stock")][0] == Decimal("100")
    assert out[(b, "crypto")][0] == Decimal("60000")
    assert out[("__NONE__", "stock")] == (None, None)


def test_holdings_with_prices_enriches_only_when_candles_exist(
    isolated_portfolio, candle_writer,
):
    """Buy 5 @ $100 + a candle close at $110 → market_value 550, unrealized +50.
    A second buy with NO candle should yield current_price=None."""
    from pt.db import holdings, transactions

    sym = f"_PRICE_{uuid.uuid4().hex[:6].upper()}"
    candle_writer(sym, "stock", datetime(2026, 4, 25, tzinfo=timezone.utc), 110.0)

    transactions.insert(
        portfolio_id=isolated_portfolio,
        symbol=sym, asset_type="stock", action="buy",
        executed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        quantity=Decimal("5"), price=Decimal("100"), trade_currency="USD",
    )
    # An asset without a candle:
    transactions.insert(
        portfolio_id=isolated_portfolio,
        symbol="UNPRICED", asset_type="stock", action="buy",
        executed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        quantity=Decimal("2"), price=Decimal("50"), trade_currency="USD",
    )

    rows = holdings.list_for_portfolio_with_prices(isolated_portfolio)
    by_sym = {r["symbol"]: r for r in rows}

    assert by_sym[sym]["current_price"] == Decimal("110")
    assert by_sym[sym]["market_value"] == Decimal("550")
    assert by_sym[sym]["unrealized_pnl"] == Decimal("50")
    assert by_sym[sym]["unrealized_pnl_pct"] == pytest.approx(0.10)

    assert by_sym["UNPRICED"]["current_price"] is None
    assert by_sym["UNPRICED"]["market_value"] is None
    assert by_sym["UNPRICED"]["unrealized_pnl"] is None
    assert by_sym["UNPRICED"]["unrealized_pnl_pct"] is None
