"""Marketaux news fetcher.

Free tier: 100 calls/day. Requires MARKETAUX_API_KEY env. Strength is built-in
sentiment scoring per article.

Endpoint: GET /v1/news/all
"""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal

import httpx
from dateutil import parser as dateparser

BASE_URL = "https://api.marketaux.com"
DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class MarketauxError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.getenv("MARKETAUX_API_KEY", "").strip()
    if not key:
        raise MarketauxError(
            "MARKETAUX_API_KEY env var not set. Get a free key at https://marketaux.com."
        )
    return key


def _client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=DEFAULT_TIMEOUT, transport=transport)


def fetch_news_for_symbols(
    symbols: list[str],
    *,
    limit: int = 20,
    language: str = "en",
    api_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> list[dict]:
    """News for one or more tickers. Marketaux supports a comma-separated list.

    Returns asset_news rows with the per-article `sentiment_score` mapped to
    our `sentiment` column (clipped to [-1, 1]).
    """
    if not symbols:
        return []
    if limit < 1 or limit > 100:
        raise ValueError("limit must be 1..100")

    params = {
        "symbols": ",".join(s.upper() for s in symbols),
        "language": language,
        "limit": limit,
        "api_token": api_key or _api_key(),
    }
    with _client(transport=transport) as c:
        resp = c.get("/v1/news/all", params=params)
        resp.raise_for_status()
        data = resp.json()
    if "error" in data:
        raise MarketauxError(str(data["error"]))

    rows: list[dict] = []
    for item in data.get("data", []):
        published = item.get("published_at")
        if not published:
            continue
        when = dateparser.parse(published)
        # Marketaux ties an article to potentially multiple entities (tickers).
        # We emit one row per (article × matched-symbol) so per-symbol queries
        # work without LIKE'ing the metadata.
        entities = item.get("entities") or []
        if not entities:
            entities = [{"symbol": symbols[0].upper(), "type": "stock"}]
        seen: set[str] = set()
        for entity in entities:
            sym = (entity.get("symbol") or "").upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            sentiment = entity.get("sentiment_score") or item.get("sentiment_score")
            try:
                sentiment_dec = (
                    Decimal(str(sentiment)).quantize(Decimal("0.001"))
                    if sentiment is not None
                    else None
                )
            except Exception:
                sentiment_dec = None
            rows.append({
                "time": when,
                "source": "marketaux",
                "symbol": sym,
                "asset_type": _asset_type_from_entity(entity),
                "title": item.get("title") or "(untitled)",
                "summary": item.get("description") or item.get("snippet"),
                "url": item.get("url") or "",
                "sentiment": sentiment_dec,
                "metadata": {
                    "uuid": item.get("uuid"),
                    "image_url": item.get("image_url"),
                    "source_label": item.get("source"),
                    "entity_type": entity.get("type"),
                    "match_score": entity.get("match_score"),
                },
            })
    return rows


def _asset_type_from_entity(entity: dict) -> str:
    et = (entity.get("type") or "").lower()
    if et == "crypto":
        return "crypto"
    if et == "forex":
        return "fx"
    return "stock"
