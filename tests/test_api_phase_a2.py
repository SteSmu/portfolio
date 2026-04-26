"""API tests for the Phase-A2 routes: snapshots, candles, sparklines, perf-summary timeseries."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from pt.api.app import app
from pt.db import transactions as _tx


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# -------------------- snapshots ------------------------------------------------

def test_snapshots_404_for_unknown_portfolio(client):
    r = client.get("/api/portfolios/99999999/snapshots")
    assert r.status_code == 404


def test_snapshots_empty_list_for_fresh_portfolio(client, isolated_portfolio):
    r = client.get(f"/api/portfolios/{isolated_portfolio}/snapshots")
    assert r.status_code == 200
    body = r.json()
    assert body["portfolio_id"] == isolated_portfolio
    assert body["snapshots"] == []


def test_snapshots_post_writes_and_get_returns(client, isolated_portfolio):
    pid = isolated_portfolio
    _tx.insert(
        portfolio_id=pid, symbol="QQQ", asset_type="stock", action="buy",
        executed_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        quantity=Decimal("3"), price=Decimal("400"),
        trade_currency="USD", source="test",
    )
    r = client.post(f"/api/portfolios/{pid}/snapshots")
    assert r.status_code == 200
    assert r.json()["rows_written"] == 1

    g = client.get(f"/api/portfolios/{pid}/snapshots")
    assert g.status_code == 200
    rows = g.json()["snapshots"]
    assert len(rows) == 1
    assert Decimal(rows[0]["total_cost_basis"]) == Decimal("1200")


# -------------------- candles --------------------------------------------------

def test_assets_candles_returns_empty_when_uncached(client):
    r = client.get("/api/assets/_NEVER_SEEN_/stock/candles")
    assert r.status_code == 200
    body = r.json()
    assert body["candles"] == []


def test_assets_candles_route_does_not_collide_with_search(client):
    """Route ordering: /_search/{q} BEFORE the catch-all, /candles after the
    catch-all but with longer path. Verify both still resolve."""
    r1 = client.get("/api/assets/_search/foo")
    assert r1.status_code == 200
    r2 = client.get("/api/assets/AAPL/stock/candles")
    assert r2.status_code == 200


# -------------------- sparklines -----------------------------------------------

def test_holdings_sparklines_empty_for_fresh_portfolio(client, isolated_portfolio):
    r = client.get(f"/api/portfolios/{isolated_portfolio}/holdings/sparklines")
    assert r.status_code == 200
    body = r.json()
    assert body == {"days": 30, "series": {}}


def test_holdings_sparklines_does_not_collide_with_get_holding(client, isolated_portfolio):
    """`/sparklines` must not be matched as `/{symbol}/{asset_type}`."""
    pid = isolated_portfolio
    r = client.get(f"/api/portfolios/{pid}/holdings/sparklines?days=10")
    assert r.status_code == 200
    assert r.json()["days"] == 10


# -------------------- performance summary timeseries ---------------------------

def test_performance_summary_timeseries_null_without_snapshots(client, isolated_portfolio):
    r = client.get(f"/api/portfolios/{isolated_portfolio}/performance/summary")
    assert r.status_code == 200
    assert r.json()["timeseries"] is None


def test_performance_summary_subtracts_buy_cashflows_from_twr(client, isolated_portfolio):
    """A buy injects fresh capital — TWR must NOT count it as a return.

    Regression for the case where the user added a 16k buy on top of a
    12k portfolio: without subtracting cash flows the day's "return"
    booked as +130%, then chained into a +100%+ period TWR and 248%
    annualized vola. With cash flows correctly fed in, both subperiod
    returns should be ≈ 0 (price didn't move) and the period TWR ≈ 0.
    """
    from pt.api.routes.performance import _cash_flows_by_date

    pid = isolated_portfolio
    # Day 1: small initial buy (10 @ 100 USD = 1000 cost basis).
    _tx.insert(
        portfolio_id=pid, symbol="QQQ", asset_type="stock", action="buy",
        executed_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        quantity=Decimal("10"), price=Decimal("100"),
        trade_currency="USD", source="test",
    )
    # Day 5: big buy at the same price (cost basis 1000 → 5000, value
    # also 1000 → 5000; price unchanged means true sub-period return = 0).
    _tx.insert(
        portfolio_id=pid, symbol="QQQ", asset_type="stock", action="buy",
        executed_at=datetime(2026, 1, 9, tzinfo=timezone.utc),
        quantity=Decimal("40"), price=Decimal("100"),
        trade_currency="USD", source="test",
    )

    # Per-date cashflow helper sees both buys as positive flows.
    flows = _cash_flows_by_date(_tx.list_for_portfolio(portfolio_id=pid, limit=None))
    assert flows[datetime(2026, 1, 5).date()] == Decimal("1000")
    assert flows[datetime(2026, 1, 9).date()] == Decimal("4000")
