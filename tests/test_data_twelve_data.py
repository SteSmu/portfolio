"""Twelve Data fetcher tests."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from pt.data import twelve_data as td


def _transport(handler):
    return httpx.MockTransport(handler)


def test_missing_api_key_raises_actionable_error(monkeypatch):
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    with pytest.raises(td.TwelveDataError, match="TWELVE_DATA_API_KEY"):
        td.fetch_quote("AAPL", transport=_transport(lambda r: httpx.Response(200, json={})))


def test_explicit_api_key_bypasses_env_check(monkeypatch):
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    transport = _transport(lambda r: httpx.Response(200, json={"symbol": "AAPL", "close": "180.5"}))
    out = td.fetch_quote("AAPL", api_key="x", transport=transport)
    assert out["symbol"] == "AAPL"


def test_api_error_payload_raises(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "x")
    transport = _transport(lambda r: httpx.Response(200, json={"status": "error", "message": "Invalid symbol"}))
    with pytest.raises(td.TwelveDataError, match="Invalid symbol"):
        td.fetch_quote("BAD", transport=transport)


def test_fetch_time_series_maps_values_to_candles(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "x")
    payload = {
        "meta": {"symbol": "AAPL", "interval": "1day", "exchange": "NASDAQ"},
        "values": [
            {"datetime": "2026-04-25", "open": "180.5", "high": "182.0",
             "low": "179.5", "close": "181.2", "volume": "5000000"},
            {"datetime": "2026-04-24", "open": "179.0", "high": "181.0",
             "low": "178.5", "close": "180.5", "volume": "4500000"},
        ],
    }
    transport = _transport(lambda r: httpx.Response(200, json=payload))
    candles = td.fetch_time_series("AAPL", interval="1day", outputsize=2, transport=transport)
    assert len(candles) == 2

    c = candles[0]
    assert c["symbol"] == "AAPL"
    assert c["interval"] == "1d"  # normalized
    assert c["open"]  == 180.5
    assert c["high"]  == 182.0
    assert c["low"]   == 179.5
    assert c["close"] == 181.2
    assert c["volume"] == 5_000_000.0
    assert c["source"] == "twelve_data"
    assert c["asset_type"] == "stock"
    assert c["exchange"] == "NASDAQ"
    assert c["time"] == datetime(2026, 4, 25, tzinfo=timezone.utc)


def test_fetch_time_series_handles_intraday_datetime_format(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "x")
    payload = {
        "meta": {"interval": "5min"},
        "values": [{"datetime": "2026-04-25 14:35:00", "open": "1", "high": "1.1",
                    "low": "0.9", "close": "1.05", "volume": "100"}],
    }
    transport = _transport(lambda r: httpx.Response(200, json=payload))
    candles = td.fetch_time_series("X", interval="5min", outputsize=1, transport=transport)
    assert candles[0]["interval"] == "5m"
    assert candles[0]["time"] == datetime(2026, 4, 25, 14, 35, tzinfo=timezone.utc)


def test_fetch_time_series_outputsize_bounds(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "x")
    transport = _transport(lambda r: httpx.Response(200, json={"values": []}))
    with pytest.raises(ValueError, match="1..5000"):
        td.fetch_time_series("AAPL", outputsize=0, transport=transport)
    with pytest.raises(ValueError, match="1..5000"):
        td.fetch_time_series("AAPL", outputsize=5001, transport=transport)


def test_search_symbol_returns_data_field(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "x")
    payload = {"data": [
        {"symbol": "AAPL", "instrument_name": "Apple Inc",
         "exchange": "NASDAQ", "country": "United States"},
    ]}
    transport = _transport(lambda r: httpx.Response(200, json=payload))
    out = td.search_symbol("apple", transport=transport)
    assert out[0]["symbol"] == "AAPL"
