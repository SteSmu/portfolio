"""CoinGecko fetcher tests — httpx.MockTransport based."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

from pt.data import coingecko as cg


def _transport(handler):
    return httpx.MockTransport(handler)


def test_fetch_spot_prices_returns_decimal_per_currency():
    def h(req):
        assert req.url.path == "/api/v3/simple/price"
        return httpx.Response(200, json={
            "bitcoin":  {"usd": 65000.5, "eur": 60100.25},
            "ethereum": {"usd": 3200.1, "eur": 2960.5},
        })
    out = cg.fetch_spot_prices(["bitcoin", "ethereum"], ["usd", "eur"],
                                transport=_transport(h))
    assert out["bitcoin"]["usd"] == Decimal("65000.5")
    assert out["ethereum"]["eur"] == Decimal("2960.5")


def test_fetch_spot_prices_empty_inputs_yield_empty_dict():
    assert cg.fetch_spot_prices([], ["usd"], transport=_transport(lambda r: httpx.Response(200))) == {}
    assert cg.fetch_spot_prices(["bitcoin"], [], transport=_transport(lambda r: httpx.Response(200))) == {}


def test_fetch_ohlc_maps_array_response_to_candle_dicts():
    raw = [
        [1735689600000, 90000.0, 91000.0, 89500.0, 90800.0],
        [1735776000000, 90800.0, 92000.0, 90500.0, 91500.0],
    ]
    transport = _transport(lambda r: httpx.Response(200, json=raw))
    candles = cg.fetch_ohlc("bitcoin", "usd", days=30, transport=transport)
    assert len(candles) == 2

    c = candles[0]
    assert c["symbol"] == "BITCOIN-USD"
    assert c["interval"] == "4h"  # 30 days → 4h granularity
    assert c["open"]  == 90000.0
    assert c["high"]  == 91000.0
    assert c["low"]   == 89500.0
    assert c["close"] == 90800.0
    assert c["source"] == "coingecko"
    assert c["asset_type"] == "crypto"
    assert c["exchange"] == "coingecko"
    assert c["time"] == datetime.fromtimestamp(1735689600, tz=timezone.utc)


def test_fetch_ohlc_interval_picks_30m_for_1_day():
    raw = [[1735689600000, 1.0, 1.1, 0.9, 1.05]]
    transport = _transport(lambda r: httpx.Response(200, json=raw))
    candles = cg.fetch_ohlc("bitcoin", "usd", days=1, transport=transport)
    assert candles[0]["interval"] == "30m"


def test_fetch_ohlc_interval_picks_1d_for_long_range():
    raw = [[1735689600000, 1.0, 1.1, 0.9, 1.05]]
    transport = _transport(lambda r: httpx.Response(200, json=raw))
    candles = cg.fetch_ohlc("bitcoin", "usd", days=365, transport=transport)
    assert candles[0]["interval"] == "1d"


def test_fetch_ohlc_rejects_zero_days():
    with pytest.raises(ValueError, match="days must be >= 1"):
        cg.fetch_ohlc("bitcoin", "usd", days=0, transport=_transport(lambda r: httpx.Response(200)))


def test_search_coin_normalizes_response():
    payload = {"coins": [
        {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "extra": "ignored"},
        {"id": "wrapped-bitcoin", "symbol": "wbtc", "name": "Wrapped Bitcoin"},
    ]}
    transport = _transport(lambda r: httpx.Response(200, json=payload))
    out = cg.search_coin("btc", transport=transport)
    assert out == [
        {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"},
        {"id": "wrapped-bitcoin", "symbol": "wbtc", "name": "Wrapped Bitcoin"},
    ]


def test_http_error_propagates():
    transport = _transport(lambda r: httpx.Response(500, json={"error": "boom"}))
    with pytest.raises(httpx.HTTPStatusError):
        cg.fetch_ohlc("bitcoin", "usd", days=30, transport=transport)
