"""Shared pytest fixtures.

Re-exports synthetic OHLCV fixtures from claude-trader where possible (added
later via path-injection or symlink) so portfolio tests use the same reference
generators as claude-trader.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def make_transaction():
    """Factory for synthetic Transaction dicts (used until DB layer is wired up)."""
    from datetime import datetime, timezone
    from decimal import Decimal

    def _factory(**overrides):
        base = {
            "symbol": "AAPL",
            "asset_type": "stock",
            "action": "buy",
            "executed_at": datetime(2025, 1, 15, tzinfo=timezone.utc),
            "quantity": Decimal("10"),
            "price": Decimal("180.50"),
            "trade_currency": "USD",
            "fees": Decimal("0"),
            "fees_currency": "USD",
            "source": "manual",
        }
        base.update(overrides)
        return base

    return _factory
