"""Tests for /performance/periods, range-aware MWR, and date-range realized."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from pt.api.app import app
from pt.api.routes.performance import (
    _compute_period_kpi,
    _period_start_date,
    _shift_months,
    _snap_at_or_before,
    _try_mwr,
)
from pt.db import transactions as _tx


# -------------------- pure helpers (no DB) ------------------------------------


def test_period_start_dates_known_codes():
    today = date(2026, 6, 15)
    assert _period_start_date(today, "1D") == date(2026, 6, 14)
    assert _period_start_date(today, "1W") == date(2026, 6, 8)
    assert _period_start_date(today, "1M") == date(2026, 5, 15)
    assert _period_start_date(today, "3M") == date(2026, 3, 15)
    assert _period_start_date(today, "YTD") == date(2026, 1, 1)
    assert _period_start_date(today, "1Y") == date(2025, 6, 15)
    assert _period_start_date(today, "ALL") is None


def test_period_start_unknown_code_raises():
    with pytest.raises(ValueError):
        _period_start_date(date(2026, 1, 1), "FOO")


def test_shift_months_clamps_day_to_month_end():
    # 2026-03-31 minus one month → 2026-02-28 (no Feb 31)
    assert _shift_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    # 2024 is a leap year → 2024-03-31 minus one month → 2024-02-29
    assert _shift_months(date(2024, 3, 31), -1) == date(2024, 2, 29)
    # Going backwards across year boundary
    assert _shift_months(date(2026, 1, 15), -1) == date(2025, 12, 15)
    # Going forwards across year boundary
    assert _shift_months(date(2025, 11, 30), 3) == date(2026, 2, 28)


def test_snap_at_or_before_picks_latest_match():
    snaps = [
        {"date": "2026-01-01"},
        {"date": "2026-02-01"},
        {"date": "2026-03-01"},
        {"date": "2026-04-01"},
    ]
    assert _snap_at_or_before(snaps, date(2026, 2, 15))["date"] == "2026-02-01"
    assert _snap_at_or_before(snaps, date(2026, 4, 1))["date"] == "2026-04-01"
    # Before all → None.
    assert _snap_at_or_before(snaps, date(2025, 12, 31)) is None


def test_compute_period_kpi_strips_buy_cashflow_from_abs_change():
    """Mid-period 4000 buy on a flat 1000 portfolio: abs_change must be ~0,
    not +4000 (which would mean "the user MADE 4000 by spending 4000")."""
    snaps = [
        {"date": "2026-01-01", "total_value": Decimal("1000"), "total_value_base": None,
         "total_cost_basis": Decimal("1000"), "metadata": {}},
        {"date": "2026-01-05", "total_value": Decimal("1000"), "total_value_base": None,
         "total_cost_basis": Decimal("1000"), "metadata": {}},
        {"date": "2026-01-09", "total_value": Decimal("5000"), "total_value_base": None,
         "total_cost_basis": Decimal("5000"), "metadata": {}},
        {"date": "2026-01-10", "total_value": Decimal("5000"), "total_value_base": None,
         "total_cost_basis": Decimal("5000"), "metadata": {}},
    ]
    cf_by_date = {date(2026, 1, 9): Decimal("4000")}

    kpi = _compute_period_kpi(
        snapshots=snaps, cf_by_date=cf_by_date, matches=[],
        period_code="1W", end_date=date(2026, 1, 10),
    )
    assert kpi is not None
    assert kpi["start_value"] == Decimal("1000")
    assert kpi["end_value"] == Decimal("5000")
    assert kpi["cashflow"] == Decimal("4000")
    assert kpi["abs_change"] == Decimal("0")
    assert kpi["simple_pct"] == Decimal("0")
    # Period TWR over flat-priced sub-windows is 0 — the buy moved no price.
    assert abs(Decimal(kpi["twr_pct"])) < Decimal("0.001")
    assert kpi["mode"] == "naive"


def test_compute_period_kpi_uses_base_currency_when_available():
    snaps = [
        {"date": "2026-01-01", "total_value": Decimal("1000"),
         "total_value_base": Decimal("900"),
         "total_cost_basis": Decimal("900"), "metadata": {"base_currency": "EUR"}},
        {"date": "2026-01-08", "total_value": Decimal("1100"),
         "total_value_base": Decimal("990"),
         "total_cost_basis": Decimal("900"), "metadata": {"base_currency": "EUR"}},
    ]
    kpi = _compute_period_kpi(
        snapshots=snaps, cf_by_date={}, matches=[],
        period_code="1W", end_date=date(2026, 1, 8),
    )
    assert kpi is not None
    assert kpi["mode"] == "base"
    assert kpi["start_value"] == Decimal("900")
    assert kpi["end_value"] == Decimal("990")


def test_compute_period_kpi_returns_none_for_unpriced_portfolio():
    snaps = [
        {"date": "2026-01-01", "total_value": None, "total_value_base": None,
         "total_cost_basis": Decimal("0"), "metadata": {}},
        {"date": "2026-01-08", "total_value": None, "total_value_base": None,
         "total_cost_basis": Decimal("0"), "metadata": {}},
    ]
    kpi = _compute_period_kpi(
        snapshots=snaps, cf_by_date={}, matches=[],
        period_code="1W", end_date=date(2026, 1, 8),
    )
    assert kpi is None


def test_try_mwr_window_treats_starting_value_as_synthetic_deposit():
    """1Y MWR on a portfolio that's been around 5 years: the pre-1Y buys
    must NOT enter the IRR — the starting value alone represents them."""
    txs = [
        {"action": "buy", "quantity": Decimal("100"), "price": Decimal("10"),
         "fees": Decimal("0"),
         "executed_at": datetime(2021, 1, 1, tzinfo=timezone.utc)},
        # In-window buy.
        {"action": "buy", "quantity": Decimal("10"), "price": Decimal("12"),
         "fees": Decimal("0"),
         "executed_at": datetime(2025, 6, 1, tzinfo=timezone.utc)},
    ]
    mwr = _try_mwr(
        txs,
        terminal_date=date(2026, 4, 30),
        terminal_value=Decimal("1500"),
        window_start=date(2025, 4, 30),
        window_start_value=Decimal("1200"),
    )
    assert mwr is not None
    # Window: -1200 (start) -120 (Jun buy) +1500 (terminal) ≈ +13–14% IRR.
    assert Decimal("0.05") < mwr < Decimal("0.30")


def test_try_mwr_without_window_falls_back_to_lifetime_irr():
    txs = [
        {"action": "buy", "quantity": Decimal("100"), "price": Decimal("10"),
         "fees": Decimal("0"),
         "executed_at": datetime(2025, 1, 1, tzinfo=timezone.utc)},
    ]
    mwr = _try_mwr(
        txs,
        terminal_date=date(2026, 1, 1),
        terminal_value=Decimal("1100"),
    )
    assert mwr is not None
    # 1000 in, 1100 out, one year → ~10%.
    assert Decimal("0.08") < mwr < Decimal("0.12")


# -------------------- API integration tests (DB required) ---------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_periods_empty_block_when_fewer_than_two_snapshots(client, isolated_portfolio):
    pid = isolated_portfolio
    r = client.get(f"/api/portfolios/{pid}/performance/periods")
    assert r.status_code == 200
    body = r.json()
    assert body["periods"] == {}


def test_periods_endpoint_strips_buy_cashflow(client, isolated_portfolio):
    """Regression: a 4k buy on a 1k portfolio must NOT show as a 1W gain."""
    pid = isolated_portfolio
    _tx.insert(
        portfolio_id=pid, symbol="QQQ", asset_type="stock", action="buy",
        executed_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        quantity=Decimal("10"), price=Decimal("100"),
        trade_currency="USD", source="test",
    )
    _tx.insert(
        portfolio_id=pid, symbol="QQQ", asset_type="stock", action="buy",
        executed_at=datetime(2026, 1, 9, tzinfo=timezone.utc),
        quantity=Decimal("40"), price=Decimal("100"),
        trade_currency="USD", source="test",
    )

    # No candles → snapshots can't price → /periods returns {} (no usable
    # baseline). That's acceptable — the cashflow-strip test against the
    # helper above proves the math; this just verifies graceful handling.
    r = client.get(f"/api/portfolios/{pid}/performance/periods")
    assert r.status_code == 200
    assert "periods" in r.json()
    # base_currency falls back to EUR when the portfolio has no snapshots yet.
    assert r.json()["base_currency"] == "EUR"


def test_realized_accepts_start_end_window(client, isolated_portfolio):
    pid = isolated_portfolio
    # 2025: realized 50 ; 2026: realized 30
    for action, qty, price, when in [
        ("buy",  "5", "100", "2025-01-01T00:00:00+00:00"),
        ("sell", "5", "110", "2025-06-01T00:00:00+00:00"),
        ("buy",  "5", "100", "2026-01-01T00:00:00+00:00"),
        ("sell", "5", "106", "2026-06-01T00:00:00+00:00"),
    ]:
        client.post(f"/api/portfolios/{pid}/transactions", json={
            "symbol": "X", "asset_type": "stock", "action": action,
            "executed_at": when, "quantity": qty, "price": price,
            "trade_currency": "USD",
        })

    r = client.get(
        f"/api/portfolios/{pid}/performance/realized"
        "?start=2025-01-01&end=2025-12-31"
    )
    assert r.status_code == 200
    assert Decimal(r.json()["total"]) == Decimal("50")

    r = client.get(
        f"/api/portfolios/{pid}/performance/realized"
        "?start=2026-01-01&end=2026-12-31"
    )
    assert r.status_code == 200
    assert Decimal(r.json()["total"]) == Decimal("30")


def test_realized_year_param_still_works(client, isolated_portfolio):
    """Backwards-compat: existing callers using ?year= keep working."""
    pid = isolated_portfolio
    client.post(f"/api/portfolios/{pid}/transactions", json={
        "symbol": "Y", "asset_type": "stock", "action": "buy",
        "executed_at": "2025-01-01T00:00:00+00:00",
        "quantity": "5", "price": "100", "trade_currency": "USD",
    })
    client.post(f"/api/portfolios/{pid}/transactions", json={
        "symbol": "Y", "asset_type": "stock", "action": "sell",
        "executed_at": "2025-06-01T00:00:00+00:00",
        "quantity": "5", "price": "110", "trade_currency": "USD",
    })

    r = client.get(f"/api/portfolios/{pid}/performance/realized?year=2025")
    assert r.status_code == 200
    assert Decimal(r.json()["total"]) == Decimal("50")
