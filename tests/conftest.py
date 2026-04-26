"""Shared pytest fixtures.

Integration-test fixtures spin up an isolated portfolio in the running shared
TimescaleDB and hard-delete it on teardown. Tests are skipped if the DB is
unreachable.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest


def _db_available() -> bool:
    try:
        from pt.db.connection import is_available
        return is_available()
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _db_available(),
                                  reason="TimescaleDB not reachable on PT_DB_*.")


@pytest.fixture
def make_transaction():
    """Factory for synthetic Transaction dicts."""
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


@pytest.fixture
def isolated_portfolio():
    """Create a uniquely-named portfolio for one test, hard-delete on teardown.

    Tests must NOT rely on data from other tests. All transactions written to
    the returned portfolio_id are wiped at the end.
    """
    from pt.db import portfolios as _portfolios

    name = f"_pt_test_{uuid.uuid4().hex[:12]}"
    pid = _portfolios.create(name, base_currency="EUR")
    try:
        yield pid
    finally:
        _portfolios.delete_hard(pid)
