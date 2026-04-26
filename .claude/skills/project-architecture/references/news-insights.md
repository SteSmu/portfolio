# News + Insights pipeline

Two news providers feed `portfolio.asset_news`. The frontend's AssetDetail
page shows the feed with sentiment colour and a manual "Refresh" button.
LLM-generated insights are intentionally **not in the live path** — the
Python scaffolding exists but the LLM step will move to the TS frontend
via the OpenRouter SDK in a later phase.

## Live components

| Module | Source | Auth | Coverage |
|--|--|--|--|
| [`pt/data/finnhub.py`](../../pt/data/finnhub.py) | Finnhub | `FINNHUB_API_KEY` | Per-stock news + market news + earnings calendar |
| [`pt/data/marketaux.py`](../../pt/data/marketaux.py) | Marketaux | `MARKETAUX_API_KEY` | Multi-asset news with built-in sentiment scores |
| [`pt/db/news.py`](../../pt/db/news.py) | — | — | `upsert_many`, `list_for_symbol`, `latest_fetched_at`, `avg_sentiment(lookback_days)` |
| [`pt/api/routes/news.py`](../../pt/api/routes/news.py) | — | — | `GET /api/news/{symbol}/{type}`, `POST /api/news/sync` |
| [`frontend/src/pages/AssetDetail.tsx`](../../frontend/src/pages/AssetDetail.tsx) | — | — | News card + sentiment colour + Refresh button |

## Data flow

```
user clicks Refresh         POST /api/news/sync
        │                          │
        │       ┌──────────────────┴───────────────────┐
        ▼       ▼                                      ▼
   Finnhub.fetch_company_news        Marketaux.fetch_news_for_symbols
                │                                      │
                └────────► news.upsert_many ◄──────────┘
                                  │
                                  ▼
                       portfolio.asset_news
                                  │
                                  ▼
   GET /api/news/{symbol}/{type}  →   AssetDetail re-renders
```

The sync endpoint returns per-provider results (`{ok, fetched, written,
error}`). One provider failing doesn't fail the whole call — the AssetDetail
page surfaces the breakdown so users see exactly which feed was unavailable.

## Sentiment

Marketaux ships sentiment scores per `(article × matched-entity)`. We store
them in `asset_news.sentiment` (NUMERIC(4,3), range -1..+1). Finnhub free
tier doesn't provide sentiment, so its rows have `sentiment=NULL`.

`asset_news.avg_sentiment(symbol, asset_type, lookback_days=14)` returns the
14-day mean across all rated items. The AssetDetail page renders it next
to "last refresh" with the same green/red colour helper as P&L.

## Dormant LLM scaffolding

These files are **not** wired into any CLI / API / cron. They're a
placeholder for a future Python LLM path if the strategy ever flips back:

| File | Status |
|--|--|
| [`pt/insights/llm.py`](../../pt/insights/llm.py) | OpenRouter via httpx — `chat`, `chat_json` |
| [`pt/insights/outlook.py`](../../pt/insights/outlook.py) | Per-asset outlook prompt + persistence to `asset_insights` |

LLM strategy decision lives in the user-memory file `llm_provider_choice.md`
(`~/.claude/projects/.../portfolio/memory/`). Summary: the Phase-6 first cut
ships news-listing only; LLM features land in the **frontend** via the
OpenRouter TS SDK with the user's API key in the browser session, not in
the backend `.env`.

## Schema

```sql
CREATE TABLE portfolio.asset_news (
  id            BIGSERIAL PRIMARY KEY,
  published_at  TIMESTAMPTZ NOT NULL,
  source        TEXT NOT NULL,           -- 'finnhub' / 'marketaux' / 'test'
  symbol        TEXT NOT NULL,           -- ticker, or '_MARKET_' for market-wide
  asset_type    TEXT NOT NULL,           -- 'stock' / 'crypto' / 'fx' / ...
  title         TEXT NOT NULL,
  summary       TEXT,
  url           TEXT NOT NULL,
  sentiment     NUMERIC(4,3),            -- -1.0 .. +1.0, NULL if not rated
  metadata      JSONB,                   -- provider-specific (image, related, ...)
  fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX uq_news_url ON asset_news (source, url);
CREATE INDEX idx_news_symbol_time ON asset_news (symbol, asset_type, published_at DESC);

CREATE TABLE portfolio.asset_insights (
  id            BIGSERIAL PRIMARY KEY,
  symbol        TEXT NOT NULL,
  asset_type    TEXT NOT NULL,
  insight_type  TEXT NOT NULL,           -- 'asset_outlook' / 'earnings_summary' / ...
  content       TEXT NOT NULL,           -- JSON-stringified payload
  model         TEXT NOT NULL,
  generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  valid_until   TIMESTAMPTZ NOT NULL,    -- TTL — `latest_valid` filters by this
  metadata      JSONB
);
```

## Tests

- [`tests/test_api_news.py`](../../tests/test_api_news.py) — 4 tests: empty
  cache shape, persisted-items round-trip, unknown-source rejection,
  graceful-degradation when both API keys are missing.

Fetcher unit tests (Finnhub, Marketaux) are NOT yet present — placeholder
for a follow-up that mocks via `httpx.MockTransport`.

## Gotchas

- **Marketaux emits one row per entity**, so an article tagged with AAPL +
  MSFT becomes two rows. Per-symbol queries work without LIKE'ing
  metadata, at the cost of slightly inflated row counts in dashboards.
- **`url` is the dedup key.** Articles re-emitted by the same provider
  upsert and refresh title/summary/sentiment. Different providers reposting
  the same source URL get separate rows because `(source, url)` is the
  UNIQUE constraint, not `url` alone — by design, in case provider
  metadata diverges.
- **Finnhub category-news are stored with `symbol='_MARKET_'`.** The
  AssetDetail page filters for the asset's symbol so it doesn't show
  these. If you ever build a market-wide news feed, query
  `WHERE symbol = '_MARKET_'`.
- **Sync is sync.** A 2-3s round-trip per provider is acceptable for a
  manual button click. If we ever need batch refresh in the background,
  promote this to a Bull-style queue or APScheduler job — not the API
  request thread.
- **`pt/insights/llm.py` and `outlook.py` are dormant.** Don't import them
  from new code without checking whether the LLM-in-frontend strategy is
  still in effect. The user-memory file is the source of truth for that
  decision.
