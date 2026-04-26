# Live-pricing on holdings

Holdings are aggregated from transactions on every read. Live-pricing adds
the latest market value via a `LEFT JOIN`-equivalent on
`public.candles`. Missing data → `null` in the response, `—` in the UI;
nothing crashes.

## Components

| File | Role |
|--|--|
| [`pt/db/prices.py`](../../pt/db/prices.py) | `latest_close(symbol, asset_type)` and bulk `latest_close_many(keys)` against `public.candles` |
| [`pt/db/holdings.py`](../../pt/db/holdings.py) | `list_for_portfolio_with_prices` enriches each row with `current_price`, `last_price_at`, `market_value`, `unrealized_pnl`, `unrealized_pnl_pct` |
| [`pt/api/routes/holdings.py`](../../pt/api/routes/holdings.py) | `?with_prices=true` (default) on the list endpoint; single-symbol endpoint also enriched |
| [`pt/api/routes/sync.py`](../../pt/api/routes/sync.py) | `POST /api/sync/portfolio/{id}/auto-prices` walks every open holding, picks the right provider, returns per-symbol results |
| [`frontend/src/pages/Holdings.tsx`](../../frontend/src/pages/Holdings.tsx) | 3 totals cards + 4 enriched columns + Refresh button + per-symbol error breakdown |

## Lookup query

```sql
SELECT DISTINCT ON (symbol, asset_type)
       symbol, asset_type, close, time
  FROM public.candles
 WHERE (symbol, asset_type) IN ((%s,%s), (%s,%s), ...)
 ORDER BY symbol, asset_type, time DESC
```

One round-trip per request, even with 100+ holdings.

## Auto-prices

`POST /api/sync/portfolio/{id}/auto-prices?days=30` iterates every open
holding and:

| `asset_type` | Provider | Notes |
|--|--|--|
| `crypto` | CoinGecko | Symbol normalised through `_CRYPTO_ID_ALIASES` (15 entries) — falls back to lower-casing the symbol if not aliased |
| `stock`, `etf` | Twelve Data | Requires `TWELVE_DATA_API_KEY` |
| `fx`, `commodity`, `bond` | — | Skipped, marked as not-auto-priced |

Per-holding errors are collected in `results[]`; the call returns 200
with `rows_written: <total>` even if some symbols fail. UI surfaces the
failures inline so the user sees "AAPL: TWELVE_DATA_API_KEY env var not
set" without losing the BTC/ETH success.

## CLI equivalent

The CLI has per-asset sync (`pt sync crypto --coin bitcoin --days 30`)
but not yet a per-portfolio bulk command. Add `pt sync auto-prices -p PID`
when needed — the API endpoint is already there.

## Frontend totals

```tsx
const totalMarketValue = data.reduce((s, h) =>
  h.market_value ? s + Number(h.market_value) : s, 0)
const totalUnrealized  = data.reduce((s, h) =>
  h.unrealized_pnl ? s + Number(h.unrealized_pnl) : s, 0)
```

`null` market values are silently skipped from the totals — partial
pricing produces a partial total, which is the user-visible behaviour we
want (don't fake numbers we don't have).

## Gotchas

- **Currency is not normalised.** `current_price` arrives in whatever
  currency the candle source used (Coingecko = vs_currency, Twelve Data =
  trade currency). Holdings carry `currency` from the underlying tx — the
  frontend renders `<price> <currency>` per row but doesn't FX-convert.
  Cross-currency totals (e.g. EUR ETF + USD Bitcoin) are therefore
  numerically suspect; flag this if a user asks "why is my total wrong".
  → fix: `pt.performance.money.convert(amount, from, to, on_date)` exists
  for the day we wire FX-aware totals; just don't ship it without per-row
  currency badges next to the converted total.
- **Holdings without candles render `—`, not `0`.** Frontend checks
  `h.current_price != null` before formatting. If you bypass that and
  just `Number(h.current_price)` you get `0` and a fake `-100% loss` —
  guard explicitly.
- **`with_prices=false`** is the escape hatch for callers that just need
  aggregation shape (e.g. a future `pt sync snapshots` job that writes
  `portfolio_snapshots`). Use it; the join is cheap but not free.
- **Crypto symbol → CoinGecko id mapping** lives in
  `pt/api/routes/sync.py` as `_CRYPTO_ID_ALIASES`. New aliases go there.
  Long-term, it should move to `assets.metadata` (`coingecko_id` key) so
  asset master is authoritative — that refactor is unblocked once we
  start storing asset master rows on tx-ingest.
- **`days` parameter limits historical depth.** 30 days is the default
  for auto-prices to keep CoinGecko calls cheap. The displayed `current
  price` is just the latest of those — fewer days doesn't change the
  current price, but it does affect what data is available for charts
  later.
- **Last-price freshness is on the row.** `last_price_at` lets the UI
  warn "stale price (>24h)" — currently not surfaced visually but the
  data is there. Add a stale-warning badge if needed.
