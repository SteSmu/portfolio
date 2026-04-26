"""Reference-case tests for FIFO/LIFO/Average cost-basis math.

These are the regression gates for "correct numbers". Every case has been
hand-verified against expected behavior. A break here breaks every Performance
calculation downstream.

Convention: use simple integer prices (100, 200) with round-number quantities so
the expected values are obvious at a glance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from pt.performance.cost_basis import (
    Lot,
    LotMatch,
    compute_lots,
    realized_pnl_total,
    unrealized_pnl,
)


def _tx(id_, action, qty, price, when, fees="0", symbol="AAPL", asset_type="stock", currency="USD"):
    return {
        "id": id_,
        "symbol": symbol,
        "asset_type": asset_type,
        "action": action,
        "executed_at": when,
        "quantity": Decimal(qty),
        "price": Decimal(price),
        "trade_currency": currency,
        "fees": Decimal(fees),
    }


def _t(year, month, day):
    return datetime(year, month, day, tzinfo=timezone.utc)


# -------------------- Empty / no-op cases ---------------------------------------

def test_empty_input_yields_empty_pools_and_matches():
    open_lots, matches = compute_lots([])
    assert open_lots == []
    assert matches == []


def test_dividend_does_not_create_lot():
    txs = [
        _tx(1, "buy",      "10", "100", _t(2026, 1, 1)),
        _tx(2, "dividend",  "0",   "0", _t(2026, 2, 1)),  # cash dividend, no lot impact
    ]
    open_lots, matches = compute_lots(txs)
    assert len(open_lots) == 1
    assert open_lots[0].quantity == Decimal("10")
    assert matches == []


# -------------------- Single buy with fees folded into cost ---------------------

def test_single_buy_fees_fold_into_unit_cost():
    """10 @ $100 + $1 fees → unit_cost = 100.10, cost_basis = 1001."""
    open_lots, _ = compute_lots([_tx(1, "buy", "10", "100", _t(2026, 1, 1), fees="1")])
    assert len(open_lots) == 1
    assert open_lots[0].price == Decimal("100.10")
    assert open_lots[0].cost_basis == Decimal("1001.00")


# -------------------- Full sell --------------------------------------------------

def test_full_sell_realizes_pnl_and_empties_pool():
    txs = [
        _tx(1, "buy",  "10", "100", _t(2026, 1, 1), fees="1"),  # cost 1001
        _tx(2, "sell", "10", "120", _t(2026, 6, 1), fees="2"),  # proceeds 1198
    ]
    open_lots, matches = compute_lots(txs)
    assert open_lots == []
    assert len(matches) == 1
    m = matches[0]
    assert m.cost == Decimal("1001.00")
    assert m.proceeds == Decimal("1198")
    assert m.realized_pnl == Decimal("197.00")


# -------------------- Partial sell ----------------------------------------------

def test_partial_sell_reduces_lot_and_realizes_proportional_pnl():
    """10 @ $100 buy, 4 @ $120 sell → 6 left, realized = 4*(120-100) = 80."""
    txs = [
        _tx(1, "buy",  "10", "100", _t(2026, 1, 1)),
        _tx(2, "sell",  "4", "120", _t(2026, 6, 1)),
    ]
    open_lots, matches = compute_lots(txs)
    assert open_lots[0].quantity == Decimal("6")
    assert matches[0].realized_pnl == Decimal("80")


# -------------------- FIFO vs LIFO with multiple lots ---------------------------

@pytest.fixture
def two_lots():
    return [
        _tx(1, "buy", "10", "100", _t(2026, 1, 1)),  # Jan: cheaper
        _tx(2, "buy", "10", "150", _t(2026, 2, 1)),  # Feb: pricier
    ]


def test_fifo_matches_oldest_lot_first(two_lots):
    """5 sell @ 200 (FIFO) → matches Jan lot (price 100), realized = 5*(200-100)=500."""
    txs = two_lots + [_tx(3, "sell", "5", "200", _t(2026, 3, 1))]
    open_lots, matches = compute_lots(txs, method="fifo")

    assert len(matches) == 1
    assert matches[0].cost_per_unit == Decimal("100")
    assert matches[0].realized_pnl == Decimal("500")

    # Jan lot now 5, Feb lot still 10
    qty_by_id = {l.transaction_id: l.quantity for l in open_lots}
    assert qty_by_id[1] == Decimal("5")
    assert qty_by_id[2] == Decimal("10")


def test_lifo_matches_newest_lot_first(two_lots):
    """5 sell @ 200 (LIFO) → matches Feb lot (price 150), realized = 5*(200-150)=250."""
    txs = two_lots + [_tx(3, "sell", "5", "200", _t(2026, 3, 1))]
    open_lots, matches = compute_lots(txs, method="lifo")

    assert matches[0].cost_per_unit == Decimal("150")
    assert matches[0].realized_pnl == Decimal("250")

    qty_by_id = {l.transaction_id: l.quantity for l in open_lots}
    assert qty_by_id[1] == Decimal("10")
    assert qty_by_id[2] == Decimal("5")


def test_average_uses_weighted_mean_price(two_lots):
    """10@100 + 10@200 → avg=150. Sell 5@250 → realized = 5*(250-150)=500."""
    txs = [
        _tx(1, "buy", "10", "100", _t(2026, 1, 1)),
        _tx(2, "buy", "10", "200", _t(2026, 2, 1)),
        _tx(3, "sell", "5", "250", _t(2026, 3, 1)),
    ]
    open_lots, matches = compute_lots(txs, method="average")
    assert matches[0].cost_per_unit == Decimal("150")
    assert matches[0].realized_pnl == Decimal("500")
    assert sum((l.quantity for l in open_lots), Decimal("0")) == Decimal("15")


# -------------------- Sell spans multiple lots ----------------------------------

def test_fifo_sell_consumes_first_lot_fully_then_partial_second(two_lots):
    """12 sell @ 200 (FIFO): all 10 of Jan + 2 of Feb."""
    txs = two_lots + [_tx(3, "sell", "12", "200", _t(2026, 3, 1))]
    open_lots, matches = compute_lots(txs, method="fifo")

    assert len(matches) == 2
    # First match: Jan lot fully (10 @ 100)
    assert matches[0].lot_transaction_id == 1
    assert matches[0].sold_quantity == Decimal("10")
    assert matches[0].realized_pnl == Decimal("1000")
    # Second match: Feb lot partial (2 @ 150)
    assert matches[1].lot_transaction_id == 2
    assert matches[1].sold_quantity == Decimal("2")
    assert matches[1].realized_pnl == Decimal("100")

    assert realized_pnl_total(matches) == Decimal("1100")
    # Feb lot has 8 remaining
    assert open_lots[0].transaction_id == 2
    assert open_lots[0].quantity == Decimal("8")


# -------------------- Error paths ----------------------------------------------

def test_sell_exceeding_holdings_raises():
    txs = [
        _tx(1, "buy",  "10", "100", _t(2026, 1, 1)),
        _tx(2, "sell", "11", "100", _t(2026, 2, 1)),
    ]
    with pytest.raises(ValueError, match="exceeds holdings"):
        compute_lots(txs)


def test_unknown_method_raises():
    with pytest.raises(ValueError, match="Unknown method"):
        compute_lots([], method="hifo")  # type: ignore[arg-type]


def test_buy_with_zero_quantity_raises():
    with pytest.raises(ValueError, match="quantity must be > 0"):
        compute_lots([_tx(1, "buy", "0", "100", _t(2026, 1, 1))])


# -------------------- Holding period --------------------------------------------

def test_holding_period_days_recorded():
    txs = [
        _tx(1, "buy",  "1", "100", _t(2026, 1,  1)),
        _tx(2, "sell", "1", "120", _t(2026, 4, 15)),
    ]
    _, matches = compute_lots(txs)
    assert matches[0].holding_period_days == 104  # Jan 1 → Apr 15 = 104


# -------------------- Multi-symbol pools are independent ------------------------

def test_separate_symbols_use_independent_pools():
    txs = [
        _tx(1, "buy", "10", "100", _t(2026, 1, 1), symbol="AAPL"),
        _tx(2, "buy",  "1", "60000", _t(2026, 1, 2), symbol="BTC", asset_type="crypto"),
    ]
    open_lots, _ = compute_lots(txs)
    assert {(l.symbol, l.asset_type) for l in open_lots} == {("AAPL", "stock"), ("BTC", "crypto")}


# -------------------- Sell fees allocated pro-rata across matched lots ----------

def test_sell_fees_allocated_pro_rata_across_matched_lots():
    """Sell 10 @ $200 with $10 fees, FIFO matches 6 from lot1 + 4 from lot2.

    Allocation: lot1 gets 10 * (6/10) = $6, lot2 gets 10 * (4/10) = $4.
    Proceeds lot1 = 6*200 - 6 = 1194. Proceeds lot2 = 4*200 - 4 = 796.
    """
    txs = [
        _tx(1, "buy", "6", "100", _t(2026, 1, 1)),
        _tx(2, "buy", "4", "150", _t(2026, 2, 1)),
        _tx(3, "sell", "10", "200", _t(2026, 3, 1), fees="10"),
    ]
    _, matches = compute_lots(txs, method="fifo")

    assert matches[0].sold_quantity == Decimal("6")
    assert matches[0].sell_fees_allocated == Decimal("6")
    assert matches[0].proceeds == Decimal("1194")

    assert matches[1].sold_quantity == Decimal("4")
    assert matches[1].sell_fees_allocated == Decimal("4")
    assert matches[1].proceeds == Decimal("796")


# -------------------- Unrealized PnL --------------------------------------------

def test_unrealized_pnl_uses_current_prices_per_lot():
    open_lots = [
        Lot(transaction_id=1, symbol="AAPL", asset_type="stock",
            quantity=Decimal("5"), quantity_original=Decimal("5"),
            price=Decimal("100"), fees=Decimal("0"),
            executed_at=_t(2026, 1, 1)),
        Lot(transaction_id=2, symbol="BTC", asset_type="crypto",
            quantity=Decimal("0.5"), quantity_original=Decimal("0.5"),
            price=Decimal("60000"), fees=Decimal("0"),
            executed_at=_t(2026, 1, 1)),
    ]
    prices = {("AAPL", "stock"): Decimal("110"),
              ("BTC", "crypto"): Decimal("70000")}
    # AAPL: 5 * (110 - 100) = 50; BTC: 0.5 * 10000 = 5000
    assert unrealized_pnl(open_lots, prices) == Decimal("5050")


def test_unrealized_pnl_skips_lots_without_price():
    open_lots = [
        Lot(transaction_id=1, symbol="X", asset_type="stock",
            quantity=Decimal("1"), quantity_original=Decimal("1"),
            price=Decimal("100"), fees=Decimal("0"),
            executed_at=_t(2026, 1, 1)),
    ]
    assert unrealized_pnl(open_lots, current_prices={}) == Decimal("0")
