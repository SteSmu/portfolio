"""Integration tests for pt.db.transactions and audit trigger."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tests.conftest import requires_db

pytestmark = requires_db


def test_insert_returns_id_and_round_trips(isolated_portfolio):
    from pt.db import transactions

    tx_id = transactions.insert(
        portfolio_id=isolated_portfolio,
        symbol="aapl",  # lower-case input
        asset_type="stock",
        action="buy",
        executed_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
        quantity=Decimal("10"),
        price=Decimal("180.50"),
        trade_currency="usd",  # lower-case input
        fees=Decimal("1.99"),
        fees_currency="USD",
    )
    row = transactions.get(tx_id)
    assert row["symbol"] == "AAPL"
    assert row["trade_currency"] == "USD"
    assert row["quantity"] == Decimal("10")
    assert row["price"] == Decimal("180.50")
    assert row["fees"] == Decimal("1.99")
    assert row["deleted_at"] is None


def test_insert_rejects_invalid_action(isolated_portfolio):
    from pt.db import transactions

    with pytest.raises(ValueError, match="Invalid action"):
        transactions.insert(
            portfolio_id=isolated_portfolio,
            symbol="AAPL", asset_type="stock", action="moonshot",
            executed_at=datetime.now(timezone.utc),
            quantity=Decimal("1"), price=Decimal("100"),
            trade_currency="USD",
        )


def test_insert_rejects_invalid_asset_type(isolated_portfolio):
    from pt.db import transactions

    with pytest.raises(ValueError, match="Invalid asset_type"):
        transactions.insert(
            portfolio_id=isolated_portfolio,
            symbol="X", asset_type="rocket", action="buy",
            executed_at=datetime.now(timezone.utc),
            quantity=Decimal("1"), price=Decimal("1"),
            trade_currency="USD",
        )


def test_insert_rejects_zero_quantity_for_buy(isolated_portfolio):
    from pt.db import transactions

    with pytest.raises(ValueError, match="Quantity must be > 0"):
        transactions.insert(
            portfolio_id=isolated_portfolio,
            symbol="A", asset_type="stock", action="buy",
            executed_at=datetime.now(timezone.utc),
            quantity=Decimal("0"), price=Decimal("100"),
            trade_currency="USD",
        )


def test_audit_trail_captures_insert(isolated_portfolio):
    from pt.db import transactions

    tx_id = transactions.insert(
        portfolio_id=isolated_portfolio, symbol="MSFT", asset_type="stock",
        action="buy", executed_at=datetime.now(timezone.utc),
        quantity=Decimal("5"), price=Decimal("400"), trade_currency="USD",
        changed_by="cli:test_user",
    )
    audit = transactions.audit_history(tx_id)
    assert len(audit) == 1
    assert audit[0]["operation"] == "INSERT"
    assert audit[0]["changed_by"] == "cli:test_user"
    assert audit[0]["new_data"]["symbol"] == "MSFT"


def test_audit_trail_captures_soft_delete(isolated_portfolio):
    from pt.db import transactions

    tx_id = transactions.insert(
        portfolio_id=isolated_portfolio, symbol="GOOG", asset_type="stock",
        action="buy", executed_at=datetime.now(timezone.utc),
        quantity=Decimal("2"), price=Decimal("150"), trade_currency="USD",
    )
    assert transactions.soft_delete(tx_id, changed_by="cli:test_user") is True

    audit = transactions.audit_history(tx_id)
    ops = [a["operation"] for a in audit]
    assert "INSERT" in ops
    assert "UPDATE" in ops  # soft-delete = UPDATE deleted_at


def test_soft_delete_excludes_from_default_list(isolated_portfolio):
    from pt.db import transactions

    tx_id = transactions.insert(
        portfolio_id=isolated_portfolio, symbol="X", asset_type="stock",
        action="buy", executed_at=datetime.now(timezone.utc),
        quantity=Decimal("1"), price=Decimal("100"), trade_currency="USD",
    )
    transactions.soft_delete(tx_id)

    default_list = transactions.list_for_portfolio(isolated_portfolio)
    assert tx_id not in [t["id"] for t in default_list]

    incl_deleted = transactions.list_for_portfolio(isolated_portfolio, include_deleted=True)
    assert tx_id in [t["id"] for t in incl_deleted]


def test_soft_delete_returns_false_for_unknown():
    from pt.db import transactions

    assert transactions.soft_delete(99_999_999) is False


def test_list_filters_by_symbol(isolated_portfolio):
    from pt.db import transactions

    transactions.insert(portfolio_id=isolated_portfolio, symbol="A",
                         asset_type="stock", action="buy",
                         executed_at=datetime.now(timezone.utc),
                         quantity=Decimal("1"), price=Decimal("1"),
                         trade_currency="USD")
    transactions.insert(portfolio_id=isolated_portfolio, symbol="B",
                         asset_type="stock", action="buy",
                         executed_at=datetime.now(timezone.utc),
                         quantity=Decimal("1"), price=Decimal("1"),
                         trade_currency="USD")

    only_a = transactions.list_for_portfolio(isolated_portfolio, symbol="A")
    assert len(only_a) == 1
    assert only_a[0]["symbol"] == "A"
