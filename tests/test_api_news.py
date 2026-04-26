"""News routes — minimal coverage. Sync routes are exercised in unit tests
for the underlying fetchers (test_data_*). Here we just verify wiring."""

from __future__ import annotations

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


def test_list_news_empty(client):
    """Empty cache returns shape with empty items."""
    body = client.get("/api/news/__NONE__/stock").json()
    assert body["symbol"] == "__NONE__"
    assert body["items"] == []
    assert body["last_fetched_at"] is None


def test_list_news_returns_persisted_items(client):
    """A row inserted via the DB helper shows up via the API."""
    from pt.db import news as _news
    from pt.db.connection import get_conn

    sym = "_TEST_NEWS_API_"
    _news.upsert_many([{
        "time": datetime.now(timezone.utc),
        "source": "test",
        "symbol": sym,
        "asset_type": "stock",
        "title": "Hello world",
        "summary": "Lorem ipsum",
        "url": f"https://example.com/{sym}/1",
        "sentiment": Decimal("0.42"),
        "metadata": {"k": "v"},
    }])
    try:
        body = client.get(f"/api/news/{sym}/stock").json()
        assert body["symbol"] == sym
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["title"] == "Hello world"
        assert item["source"] == "test"
        # sentiment serialized as string from Decimal
        assert Decimal(item["sentiment"]) == Decimal("0.420")
    finally:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM portfolio.asset_news WHERE symbol = %s", (sym,))
            conn.commit()


def test_sync_news_unknown_source_returns_400(client):
    res = client.post("/api/news/sync", json={
        "symbol": "AAPL", "asset_type": "stock", "sources": ["invalid"],
    })
    assert res.status_code == 400


def test_sync_news_returns_per_source_breakdown_with_missing_keys(client, monkeypatch):
    """Without provider API keys configured, sync still returns 200 with
    per-source error reporting (graceful degradation)."""
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("MARKETAUX_API_KEY", raising=False)

    res = client.post("/api/news/sync", json={
        "symbol": "AAPL", "asset_type": "stock",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["rows_written"] == 0
    # Both providers should be present and report ok=false
    for src in ("finnhub", "marketaux"):
        assert src in body["sources"]
        assert body["sources"][src]["ok"] is False
        assert "API_KEY" in body["sources"][src]["error"]
