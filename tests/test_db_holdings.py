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


def test_get_for_symbol_returns_correct_row(isolated_portfolio):
    from pt.db import holdings

    _add(isolated_portfolio, "AAPL", "buy", "5", "180")
    row = holdings.get_for_symbol(isolated_portfolio, "AAPL", "stock")
    assert row is not None
    assert row["quantity"] == Decimal("5")

    assert holdings.get_for_symbol(isolated_portfolio, "GOOG", "stock") is None
