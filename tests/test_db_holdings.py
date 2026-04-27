"""Integration tests for holdings aggregation.

These tests pin the math: buy + sell + transfer aggregation must produce the
exact quantity and total_cost that performance calculations later depend on.
A regression here breaks all Performance numbers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tests.conftest import requires_db

pytestmark = requires_db


def _add(portfolio_id, symbol, action, qty, price, fees="0", when=None,
         asset_type="stock", currency="USD"):
    from pt.db import transactions

    return transactions.insert(
        portfolio_id=portfolio_id,
        symbol=symbol,
        asset_type=asset_type,
        action=action,
        executed_at=when or datetime.now(timezone.utc),
        quantity=Decimal(qty),
        price=Decimal(price),
        trade_currency=currency,
        fees=Decimal(fees),
    )


def test_empty_portfolio_has_no_holdings(isolated_portfolio):
    from pt.db import holdings

    assert holdings.list_for_portfolio(isolated_portfolio) == []


def test_single_buy_produces_one_holding(isolated_portfolio):
    from pt.db import holdings

    _add(isolated_portfolio, "AAPL", "buy", "10", "180")
    rows = holdings.list_for_portfolio(isolated_portfolio)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["quantity"] == Decimal("10")
    assert rows[0]["total_cost"] == Decimal("1800")
    assert rows[0]["avg_cost"] == Decimal("180")


def test_buy_then_partial_sell_reduces_quantity_and_cost(isolated_portfolio):
    """10 buy @ 180 (cost 1800) + 4 sell @ 200 (proceeds 800) → qty=6, total_cost=1000.

    Note: This tests the simplified average-cost aggregation. FIFO/LIFO will
    produce different cost numbers — that's covered in performance/cost_basis tests.
    """
    from pt.db import holdings

    _add(isolated_portfolio, "AAPL", "buy",  "10", "180")
    _add(isolated_portfolio, "AAPL", "sell",  "4", "200")
    rows = holdings.list_for_portfolio(isolated_portfolio)
    assert len(rows) == 1
    assert rows[0]["quantity"] == Decimal("6")
    assert rows[0]["total_cost"] == Decimal("1000")  # 1800 - 800


def test_fees_increase_cost_basis_on_buy(isolated_portfolio):
    from pt.db import holdings

    _add(isolated_portfolio, "X", "buy", "1", "100", fees="2.50")
    row = holdings.list_for_portfolio(isolated_portfolio)[0]
    assert row["total_cost"] == Decimal("102.50")  # 100 + 2.50


def test_fully_closed_position_excluded_by_default(isolated_portfolio):
    from pt.db import holdings

    _add(isolated_portfolio, "X", "buy",  "5", "100")
    _add(isolated_portfolio, "X", "sell", "5", "120")

    default = holdings.list_for_portfolio(isolated_portfolio)
    assert default == []

    incl_zero = holdings.list_for_portfolio(isolated_portfolio, include_zero=True)
    assert len(incl_zero) == 1
    assert incl_zero[0]["quantity"] == Decimal("0")


def test_dividend_does_not_change_quantity_or_cost(isolated_portfolio):
    """Cash dividends increase realized_pnl, not quantity/cost. Quantity stays the same."""
    from pt.db import holdings

    _add(isolated_portfolio, "X", "buy",      "10", "100")
    _add(isolated_portfolio, "X", "dividend",  "0", "0", fees="0")  # cash dividend logged separately

    row = holdings.list_for_portfolio(isolated_portfolio)[0]
    assert row["quantity"] == Decimal("10")
    assert row["total_cost"] == Decimal("1000")


def test_separate_symbols_produce_separate_rows(isolated_portfolio):
    from pt.db import holdings

    _add(isolated_portfolio, "AAPL", "buy", "1", "180")
    _add(isolated_portfolio, "MSFT", "buy", "2", "400")

    rows = holdings.list_for_portfolio(isolated_portfolio)
    syms = sorted(r["symbol"] for r in rows)
    assert syms == ["AAPL", "MSFT"]


def test_transfer_in_contributes_cost_basis(isolated_portfolio):
    """A pure transfer_in (e.g. PDF broker-statement import) carries cost_basis.

    Cost convention matches `pt.performance.cost_basis`: transfer_in.price is
    the cost-per-share at acquisition (broker statements expose this as
    Einstandskurs). Without this the holdings totals show 0 € for any
    portfolio populated solely via PDF import.
    """
    from pt.db import holdings

    _add(isolated_portfolio, "AAPL", "transfer_in", "10", "180", fees="0")
    rows = holdings.list_for_portfolio(isolated_portfolio)
    assert len(rows) == 1
    assert rows[0]["quantity"] == Decimal("10")
    assert rows[0]["total_cost"] == Decimal("1800")
    assert rows[0]["avg_cost"] == Decimal("180")


def test_transfer_in_with_fees_adds_to_cost(isolated_portfolio):
    from pt.db import holdings

    _add(isolated_portfolio, "AAPL", "transfer_in", "10", "180", fees="5")
    row = holdings.list_for_portfolio(isolated_portfolio)[0]
    assert row["total_cost"] == Decimal("1805")  # 1800 + 5


def test_transfer_out_reduces_cost_symmetric_to_sell(isolated_portfolio):
    from pt.db import holdings

    _add(isolated_portfolio, "AAPL", "transfer_in",  "10", "180")
    _add(isolated_portfolio, "AAPL", "transfer_out",  "4", "200")
    row = holdings.list_for_portfolio(isolated_portfolio)[0]
    assert row["quantity"] == Decimal("6")
    assert row["total_cost"] == Decimal("1000")  # 1800 - 800


def test_buy_then_transfer_in_accumulates_cost(isolated_portfolio):
    """Mixed history: bought 5 @ 100, then transferred in 5 @ 200 from another broker."""
    from pt.db import holdings

    _add(isolated_portfolio, "AAPL", "buy",          "5", "100")
    _add(isolated_portfolio, "AAPL", "transfer_in",  "5", "200")
    row = holdings.list_for_portfolio(isolated_portfolio)[0]
    assert row["quantity"] == Decimal("10")
    assert row["total_cost"] == Decimal("1500")  # 500 + 1000
    assert row["avg_cost"] == Decimal("150")


def test_get_for_symbol_returns_correct_row(isolated_portfolio):
    from pt.db import holdings

    _add(isolated_portfolio, "AAPL", "buy", "5", "180")
    row = holdings.get_for_symbol(isolated_portfolio, "AAPL", "stock")
    assert row is not None
    assert row["quantity"] == Decimal("5")

    assert holdings.get_for_symbol(isolated_portfolio, "GOOG", "stock") is None


# -- FX-aware base-currency totals on enriched holdings ------------------------


def test_with_prices_adds_base_fields_when_fx_available(isolated_portfolio):
    """Per-row USD candle + EURUSD rate ⇒ market_value_base in EUR."""
    from datetime import date as _date
    from pt.data import store
    from pt.db import holdings
    from pt.db.connection import get_conn

    sym = "FXBASEUSD"
    fx_time = datetime(2026, 4, 1, tzinfo=timezone.utc)
    candle_time = datetime(2026, 4, 1, 23, 59, 59, tzinfo=timezone.utc)

    store.insert_fx_rates([{
        "time": fx_time, "source": "frankfurter", "symbol": "EURUSD",
        "value": Decimal("1.10"), "metadata": {},
    }])
    store.insert_candles([{
        "time": candle_time, "symbol": sym, "interval": "1day",
        "open": Decimal("100"), "high": Decimal("100"), "low": Decimal("100"),
        "close": Decimal("100"), "volume": Decimal("0"),
        "asset_type": "stock", "source": "test",
    }])
    _add(isolated_portfolio, sym, "buy", "3", "90", currency="USD",
         when=datetime(2026, 3, 30, tzinfo=timezone.utc))

    try:
        rows = holdings.list_for_portfolio_with_prices(isolated_portfolio)
        row = next(r for r in rows if r["symbol"] == sym)
        assert row["market_value"] == Decimal("300")  # 3 x 100 USD
        assert row["market_value_base"] is not None
        # 300 USD / 1.10 EURUSD = 272.7272... EUR
        from pt.performance.money import quantize_money
        assert quantize_money(row["market_value_base"]) == Decimal("272.73")
        assert row["total_cost_base"] is not None
        assert row["unrealized_pnl_base"] is not None
    finally:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM public.market_meta WHERE source='frankfurter' AND symbol='EURUSD' AND time=%s", (fx_time,))
            cur.execute("DELETE FROM public.candles WHERE symbol=%s AND interval='1day'", (sym,))
            conn.commit()


def test_with_prices_base_fields_are_none_when_fx_missing(isolated_portfolio):
    """No EUR<->GBP rate path ⇒ *_base fields are None (not zero)."""
    from pt.data import store
    from pt.db import holdings
    from pt.db.connection import get_conn

    sym = "FXBASEGBP"
    candle_time = datetime(2026, 4, 1, 23, 59, 59, tzinfo=timezone.utc)

    store.insert_candles([{
        "time": candle_time, "symbol": sym, "interval": "1day",
        "open": Decimal("50"), "high": Decimal("50"), "low": Decimal("50"),
        "close": Decimal("50"), "volume": Decimal("0"),
        "asset_type": "stock", "source": "test",
    }])
    _add(isolated_portfolio, sym, "buy", "2", "40", currency="GBP",
         when=datetime(2026, 3, 30, tzinfo=timezone.utc))

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.market_meta WHERE source='frankfurter' "
                "AND symbol IN ('EURGBP','GBPEUR') AND time::date <= %s",
                (datetime(2026, 4, 1).date(),),
            )
            conn.commit()
        rows = holdings.list_for_portfolio_with_prices(isolated_portfolio)
        row = next(r for r in rows if r["symbol"] == sym)
        assert row["market_value"] == Decimal("100")  # 2 x 50 GBP
        assert row["market_value_base"] is None
        assert row["total_cost_base"] is None
        assert row["unrealized_pnl_base"] is None
    finally:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM public.candles WHERE symbol=%s AND interval='1day'", (sym,))
            conn.commit()


