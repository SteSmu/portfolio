"""Benchmark routes — catalog + on-demand sync graceful degradation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from pt.api.app import app
    return TestClient(app)


def test_list_benchmarks_returns_catalog(client):
    """`GET /api/benchmarks` returns the curated whitelist."""
    res = client.get("/api/benchmarks")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert len(body) >= 2

    symbols = {b["symbol"] for b in body}
    assert {"SPY", "URTH"}.issubset(symbols)

    for entry in body:
        # Every catalog entry MUST carry the keys the frontend renders.
        assert set(entry.keys()) == {"symbol", "asset_type", "display_name", "region"}
        assert entry["symbol"] == entry["symbol"].upper()
        assert entry["asset_type"] in {"stock", "etf"}


def test_list_benchmarks_order_is_stable(client):
    """Two GETs return the same order — the frontend may cache by index."""
    a = client.get("/api/benchmarks").json()
    b = client.get("/api/benchmarks").json()
    assert [x["symbol"] for x in a] == [x["symbol"] for x in b]


def test_sync_benchmark_graceful_when_no_api_key(client, monkeypatch):
    """Without a Twelve Data key + with the SPY entry preferring TD, the
    fallback chain still has Yahoo to fall through to. If both fail the
    route returns a 502 (graceful — never crash).

    To exercise the no-key branch deterministically we monkey-patch both
    fetchers to raise their typed errors. The route MUST surface a 502
    with a detail message, not a 500 stack trace.
    """
    from pt.data import twelve_data as _td
    from pt.data import yahoo as _yh

    def _td_boom(*a, **kw):
        raise _td.TwelveDataError("TWELVE_DATA_API_KEY env var not set.")

    def _yh_boom(*a, **kw):
        raise _yh.YahooFinanceError("simulated yahoo outage")

    monkeypatch.setattr(_td, "fetch_time_series", _td_boom)
    monkeypatch.setattr(_yh, "fetch_time_series", _yh_boom)

    res = client.post("/api/benchmarks/SPY/sync?days=5")
    assert res.status_code == 502
    body = res.json()
    assert "detail" in body
    detail = body["detail"].lower()
    assert "twelve_data" in detail or "yahoo" in detail


def test_sync_benchmark_unknown_symbol_still_attempts_fetch(client, monkeypatch):
    """An off-whitelist symbol is still fetchable — `ensure_history` doesn't
    require catalog membership, just persistence semantics."""
    from pt.data import twelve_data as _td
    from pt.data import yahoo as _yh

    def _td_boom(*a, **kw):
        raise _td.TwelveDataError("bogus symbol")

    def _yh_boom(*a, **kw):
        raise _yh.YahooFinanceError("bogus symbol")

    monkeypatch.setattr(_td, "fetch_time_series", _td_boom)
    monkeypatch.setattr(_yh, "fetch_time_series", _yh_boom)

    res = client.post("/api/benchmarks/NOT_A_REAL_TICKER/sync?days=5")
    assert res.status_code == 502


def test_sync_benchmark_rejects_out_of_range_days(client):
    """`days` is bounded 1..5000 by the Query validator."""
    res = client.post("/api/benchmarks/SPY/sync?days=0")
    assert res.status_code == 422
    res = client.post("/api/benchmarks/SPY/sync?days=99999")
    assert res.status_code == 422
