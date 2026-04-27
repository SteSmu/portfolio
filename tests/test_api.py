"""FastAPI integration tests — exercise every router against the live DB.

Each test uses an isolated portfolio via the `isolated_portfolio` fixture so
parallel runs don't collide. Sync routes are NOT exercised here (they hit
real external APIs); their underlying fetchers are unit-tested elsewhere.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture
def client() -> TestClient:
    from pt.api.app import app
    return TestClient(app)


# -------------------- /api/health -----------------------------------------------

def test_health_returns_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"]["status"] == "ok"
    assert body["db"]["latency_ms"] >= 0
    assert "version" in body
    assert "now" in body
    assert "counts" in body
    # Per-request id echoed back so clients can trace
    assert "x-request-id" in {k.lower() for k in r.headers}


# -------------------- portfolios -----------------------------------------------

def test_portfolio_create_then_get_then_archive(client):
    name = f"_api_test_{uuid.uuid4().hex[:8]}"

    create = client.post("/api/portfolios",
                         json={"name": name, "base_currency": "EUR"})
    assert create.status_code == 201
    pid = create.json()["id"]

    try:
        get = client.get(f"/api/portfolios/{pid}")
        assert get.status_code == 200
        assert get.json()["name"] == name

        listing = client.get("/api/portfolios")
        assert any(p["id"] == pid for p in listing.json())

        archive = client.delete(f"/api/portfolios/{pid}")
        assert archive.status_code == 204
    finally:
        from pt.db import portfolios
        portfolios.delete_hard(pid)


def test_portfolio_create_duplicate_returns_409(client):
    from pt.db import portfolios as _p

    name = f"_api_dup_{uuid.uuid4().hex[:8]}"
    pid = _p.create(name)
    try:
        r = client.post("/api/portfolios", json={"name": name})
        assert r.status_code == 409
    finally:
        _p.delete_hard(pid)


def test_portfolio_get_404(client):
    r = client.get("/api/portfolios/99999999")
    assert r.status_code == 404


# -------------------- transactions ----------------------------------------------

def test_transaction_create_list_get_audit_delete(client, isolated_portfolio):
    pid = isolated_portfolio
    body = {
        "symbol": "AAPL", "asset_type": "stock", "action": "buy",
        "executed_at": "2026-01-15T00:00:00+00:00",
        "quantity": "10", "price": "180.50", "trade_currency": "USD",
        "fees": "1.99", "fees_currency": "USD",
    }
    create = client.post(f"/api/portfolios/{pid}/transactions", json=body)
    assert create.status_code == 201, create.text
    tx_id = create.json()["id"]
    assert create.json()["symbol"] == "AAPL"

    listing = client.get(f"/api/portfolios/{pid}/transactions")
    assert listing.status_code == 200
    assert any(t["id"] == tx_id for t in listing.json())

    get = client.get(f"/api/portfolios/{pid}/transactions/{tx_id}")
    assert get.status_code == 200

    audit = client.get(f"/api/portfolios/{pid}/transactions/{tx_id}/audit")
    assert audit.status_code == 200
    ops = [a["operation"] for a in audit.json()]
    assert "INSERT" in ops

    delete = client.delete(f"/api/portfolios/{pid}/transactions/{tx_id}")
    assert delete.status_code == 204

    # After delete, list (default) should not include it
    after = client.get(f"/api/portfolios/{pid}/transactions")
    assert tx_id not in [t["id"] for t in after.json()]


def test_transaction_invalid_action_returns_400(client, isolated_portfolio):
    body = {
        "symbol": "X", "asset_type": "stock", "action": "moonshot",
        "executed_at": "2026-01-01T00:00:00+00:00",
        "quantity": "1", "price": "1", "trade_currency": "USD",
    }
    r = client.post(f"/api/portfolios/{isolated_portfolio}/transactions", json=body)
    assert r.status_code == 400


def test_transaction_for_other_portfolio_returns_404(client, isolated_portfolio):
    """A tx belongs to portfolio A; querying it under portfolio B must 404."""
    body = {
        "symbol": "Y", "asset_type": "stock", "action": "buy",
        "executed_at": "2026-01-01T00:00:00+00:00",
        "quantity": "1", "price": "1", "trade_currency": "USD",
    }
    create = client.post(f"/api/portfolios/{isolated_portfolio}/transactions", json=body)
    tx_id = create.json()["id"]

    r = client.get(f"/api/portfolios/99999999/transactions/{tx_id}")
    assert r.status_code == 404


# -------------------- holdings --------------------------------------------------

def test_holdings_aggregate_buy_then_partial_sell(client, isolated_portfolio):
    pid = isolated_portfolio
    base = lambda action, qty, price, when: {
        "symbol": "ZZZ", "asset_type": "stock", "action": action,
        "executed_at": when, "quantity": qty, "price": price,
        "trade_currency": "USD",
    }
    client.post(f"/api/portfolios/{pid}/transactions",
                json=base("buy",  "10", "100", "2026-01-01T00:00:00+00:00"))
    client.post(f"/api/portfolios/{pid}/transactions",
                json=base("sell", "4",  "120", "2026-06-01T00:00:00+00:00"))

    r = client.get(f"/api/portfolios/{pid}/holdings")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "ZZZ"
    assert Decimal(rows[0]["quantity"]) == Decimal("6")
    assert Decimal(rows[0]["total_cost"]) == Decimal("520")  # 1000 - 480


def test_holdings_404_for_unknown_symbol(client, isolated_portfolio):
    r = client.get(f"/api/portfolios/{isolated_portfolio}/holdings/UNKNOWN/stock")
    assert r.status_code == 404


# -------------------- assets ---------------------------------------------------

def test_asset_upsert_then_get(client):
    sym = f"_TST{uuid.uuid4().hex[:6].upper()}"
    body = {"symbol": sym, "asset_type": "stock",
            "name": "Test Co", "currency": "USD"}
    try:
        r = client.post("/api/assets", json=body)
        assert r.status_code == 201
        assert r.json()["name"] == "Test Co"

        get = client.get(f"/api/assets/{sym}/stock")
        assert get.status_code == 200
        assert get.json()["currency"] == "USD"

        search = client.get(f"/api/assets/_search/{sym}")
        assert search.status_code == 200
        assert any(a["symbol"] == sym for a in search.json())
    finally:
        from pt.db.connection import get_conn
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM portfolio.assets WHERE symbol=%s AND asset_type=%s",
                        (sym, "stock"))
            conn.commit()


def test_asset_get_404(client):
    r = client.get("/api/assets/ZZZ_NONEXISTENT_ZZZ/stock")
    assert r.status_code == 404


# -------------------- performance ----------------------------------------------

def test_performance_summary_returns_open_lots_and_realized(client, isolated_portfolio):
    pid = isolated_portfolio
    base = lambda action, qty, price, when: {
        "symbol": "PPP", "asset_type": "stock", "action": action,
        "executed_at": when, "quantity": qty, "price": price,
        "trade_currency": "USD",
    }
    client.post(f"/api/portfolios/{pid}/transactions",
                json=base("buy",  "10", "100", "2026-01-01T00:00:00+00:00"))
    client.post(f"/api/portfolios/{pid}/transactions",
                json=base("sell", "4",  "150", "2026-06-01T00:00:00+00:00"))

    r = client.get(f"/api/portfolios/{pid}/performance/summary?method=fifo")
    assert r.status_code == 200
    body = r.json()
    assert body["open_lot_count"] == 1
    assert Decimal(body["open_cost_basis"]) == Decimal("600")
    assert Decimal(body["realized_pnl"]) == Decimal("200")  # 4 * (150-100)


def test_performance_realized_filters_by_year(client, isolated_portfolio):
    pid = isolated_portfolio
    # 2025: realized 50
    client.post(f"/api/portfolios/{pid}/transactions", json={
        "symbol": "A", "asset_type": "stock", "action": "buy",
        "executed_at": "2025-01-01T00:00:00+00:00",
        "quantity": "5", "price": "100", "trade_currency": "USD"})
    client.post(f"/api/portfolios/{pid}/transactions", json={
        "symbol": "A", "asset_type": "stock", "action": "sell",
        "executed_at": "2025-06-01T00:00:00+00:00",
        "quantity": "5", "price": "110", "trade_currency": "USD"})

    r = client.get(f"/api/portfolios/{pid}/performance/realized?year=2025")
    assert r.status_code == 200
    assert Decimal(r.json()["total"]) == Decimal("50")


def test_performance_invalid_method_returns_400(client, isolated_portfolio):
    r = client.get(f"/api/portfolios/{isolated_portfolio}/performance/summary?method=bogus")
    assert r.status_code == 400


# -------------------- /api/sync/stock symbol-routing guard --------------------

def test_sync_stock_routes_mapped_symbol_to_yahoo(client, monkeypatch):
    """Bare 'AIR' must NOT be sent to Twelve Data — TD returns AAR Corp (US)
    instead of Airbus (Paris) and pollutes public.candles with USD prices
    keyed as if they were EUR. Manual `pt sync stock AIR` and
    `POST /api/sync/stock?symbol=AIR` both have to route to Yahoo via
    `_YAHOO_SYMBOL_MAP[AIR] = AIR.PA`.
    """
    from pt.api.routes import sync as _sync_routes

    td_called = {"called": False}
    yahoo_called = {"called": False, "symbol": None}

    def _fake_td(*args, **kwargs):
        td_called["called"] = True
        raise AssertionError("Twelve Data must NOT be called for mapped symbols")

    def _fake_yahoo(yahoo_symbol, **kwargs):
        yahoo_called["called"] = True
        yahoo_called["symbol"] = yahoo_symbol
        return [{
            "time": datetime(2026, 4, 1, 23, 59, 59, tzinfo=timezone.utc),
            "symbol": kwargs.get("db_symbol", yahoo_symbol).upper(),
            "interval": "1d",
            "open": 170.0, "high": 172.0, "low": 168.0, "close": 171.0,
            "volume": 1.0, "source": "yahoo", "asset_type": kwargs.get("asset_type", "stock"),
            "exchange": kwargs.get("exchange"),
        }]

    def _no_write(rows):
        return len(rows)

    monkeypatch.setattr(_sync_routes._td, "fetch_time_series", _fake_td)
    monkeypatch.setattr(_sync_routes._yh, "fetch_time_series", _fake_yahoo)
    monkeypatch.setattr(_sync_routes._store, "insert_candles", _no_write)

    r = client.post("/api/sync/stock?symbol=AIR&outputsize=10")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "yahoo"
    assert body["yahoo_symbol"] == "AIR.PA"
    assert yahoo_called["called"] is True
    assert yahoo_called["symbol"] == "AIR.PA"
    assert td_called["called"] is False


def test_sync_stock_rejects_intraday_for_mapped_symbol(client):
    """Mapped symbols only get daily Yahoo bars — non-daily intervals
    return 400 rather than silently falling back to TD."""
    r = client.post("/api/sync/stock?symbol=AIR&interval=1h&outputsize=10")
    assert r.status_code == 400
    assert "Yahoo" in r.json()["detail"]


def test_sync_stock_passes_through_us_ticker_to_twelve_data(client, monkeypatch):
    """Bare US tickers (not in `_YAHOO_SYMBOL_MAP`) keep going through TD."""
    from pt.api.routes import sync as _sync_routes

    yh_called = {"called": False}

    def _fake_td(symbol, **kwargs):
        return [{
            "time": datetime(2026, 4, 1, 23, 59, 59, tzinfo=timezone.utc),
            "symbol": symbol.upper(), "interval": "1day",
            "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0,
            "volume": 1.0, "source": "twelve_data", "asset_type": "stock",
            "exchange": None,
        }]

    def _fake_yh(*args, **kwargs):
        yh_called["called"] = True
        raise AssertionError("Yahoo must NOT be called for unmapped US tickers")

    monkeypatch.setattr(_sync_routes._td, "fetch_time_series", _fake_td)
    monkeypatch.setattr(_sync_routes._yh, "fetch_time_series", _fake_yh)
    monkeypatch.setattr(_sync_routes._store, "insert_candles", lambda rows: len(rows))

    r = client.post("/api/sync/stock?symbol=AAPL&outputsize=10")
    assert r.status_code == 200
    assert r.json()["source"] == "twelve_data"
    assert yh_called["called"] is False
