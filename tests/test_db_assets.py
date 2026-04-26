"""Integration tests for asset master."""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture
def cleanup_asset():
    created = []

    def _track(symbol, asset_type):
        created.append((symbol.upper(), asset_type))
        return symbol, asset_type

    yield _track

    from pt.db.connection import get_conn

    if created:
        with get_conn() as conn, conn.cursor() as cur:
            for sym, at in created:
                cur.execute("DELETE FROM portfolio.assets WHERE symbol=%s AND asset_type=%s",
                            (sym, at))
            conn.commit()


def test_upsert_then_get(cleanup_asset):
    from pt.db import assets

    sym = f"_TST{uuid.uuid4().hex[:6]}".upper()
    cleanup_asset(sym, "stock")
    assets.upsert(sym, "stock", name="Test Co", currency="usd",
                  exchange="nasdaq", isin="US0000000001")

    row = assets.get(sym, "stock")
    assert row is not None
    assert row["name"] == "Test Co"
    assert row["currency"] == "USD"
    assert row["isin"] == "US0000000001"


def test_upsert_is_idempotent_and_updates(cleanup_asset):
    from pt.db import assets

    sym = f"_TST{uuid.uuid4().hex[:6]}".upper()
    cleanup_asset(sym, "stock")
    assets.upsert(sym, "stock", name="Old Name", currency="USD")
    assets.upsert(sym, "stock", name="New Name", currency="USD")

    assert assets.get(sym, "stock")["name"] == "New Name"


def test_upsert_preserves_optional_fields_on_partial_update(cleanup_asset):
    """Re-upserting without ISIN should NOT clear an existing ISIN (COALESCE)."""
    from pt.db import assets

    sym = f"_TST{uuid.uuid4().hex[:6]}".upper()
    cleanup_asset(sym, "stock")
    assets.upsert(sym, "stock", name="X", currency="USD", isin="US0000000099")
    assets.upsert(sym, "stock", name="X v2", currency="USD")  # no isin
    assert assets.get(sym, "stock")["isin"] == "US0000000099"


def test_find_similar_matches_substring(cleanup_asset):
    from pt.db import assets

    sym = f"_TST{uuid.uuid4().hex[:6]}".upper()
    cleanup_asset(sym, "stock")
    assets.upsert(sym, "stock", name="UniqueNeedleCo", currency="USD")

    matches = assets.find_similar("UniqueNeedle", limit=10)
    assert any(m["symbol"] == sym for m in matches)
