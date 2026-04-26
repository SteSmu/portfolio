"""Frankfurter fetcher tests — uses httpx.MockTransport, no real HTTP."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import pytest

from pt.data import frankfurter as fr


def _make_transport(payloads_by_path: dict[str, dict]) -> httpx.MockTransport:
    """Return a mock transport that maps URL path → JSON payload."""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in payloads_by_path:
            return httpx.Response(200, json=payloads_by_path[path])
        return httpx.Response(404, json={"error": f"no mock for {path}"})
    return httpx.MockTransport(handler)


def test_fetch_latest_returns_payload():
    payload = {"date": "2026-04-25", "base": "EUR",
               "rates": {"USD": 1.085, "CHF": 0.95}}
    transport = _make_transport({"/v1/latest": payload})

    out = fr.fetch_latest(base="EUR", quotes=["USD", "CHF"], transport=transport)
    assert out == payload


def test_to_market_meta_rows_single_day():
    payload = {"date": "2026-04-25", "base": "EUR",
               "rates": {"USD": 1.085, "CHF": 0.95}}
    rows = fr.to_market_meta_rows(payload)
    assert len(rows) == 2

    by_sym = {r["symbol"]: r for r in rows}
    assert by_sym["EURUSD"]["value"] == Decimal("1.085")
    assert by_sym["EURCHF"]["value"] == Decimal("0.95")
    assert all(r["source"] == "frankfurter" for r in rows)
    assert all(r["time"] == datetime(2026, 4, 25, tzinfo=timezone.utc) for r in rows)


def test_to_market_meta_rows_time_series():
    payload = {
        "start_date": "2026-04-24", "end_date": "2026-04-25", "base": "EUR",
        "rates": {
            "2026-04-24": {"USD": 1.080},
            "2026-04-25": {"USD": 1.085},
        },
    }
    rows = fr.to_market_meta_rows(payload)
    assert len(rows) == 2
    by_time = {r["time"].date(): r for r in rows}
    assert by_time[date(2026, 4, 24)]["value"] == Decimal("1.080")
    assert by_time[date(2026, 4, 25)]["value"] == Decimal("1.085")


def test_to_market_meta_rows_empty_payload_yields_empty_list():
    assert fr.to_market_meta_rows({}) == []
    assert fr.to_market_meta_rows({"base": "EUR"}) == []


def test_fetch_time_series_rejects_inverted_range():
    with pytest.raises(ValueError, match="must be <="):
        fr.fetch_time_series(date(2026, 4, 25), date(2026, 4, 24), transport=_make_transport({}))


def test_fetch_historical_uses_path_with_iso_date():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={"date": "2025-12-31", "base": "EUR",
                                          "rates": {"USD": 1.10}})
    transport = httpx.MockTransport(handler)

    fr.fetch_historical(date(2025, 12, 31), base="EUR", quotes=["USD"], transport=transport)
    assert captured["path"] == "/v1/2025-12-31"
