# Data fetchers (market data + news)

Every external data source is a thin sync httpx client returning dicts
shaped to slot directly into the `pt.data.store` insert helpers.
[`pt/data/store.py`](../../pt/data/store.py) is the only module that talks
to the DB — fetchers themselves are pure functions, easy to test with
`httpx.MockTransport`.

## Modules

| Module | Source | Auth | Output | Free-tier limit |
|--|--|--|--|--|
| [`coingecko.py`](../../pt/data/coingecko.py) | CoinGecko | none | OHLC candles, spot prices, coin search | ~10-30 req/min |
| [`twelve_data.py`](../../pt/data/twelve_data.py) | Twelve Data | `TWELVE_DATA_API_KEY` | Quote, OHLCV time-series, symbol search | 800/day, 8/min |
| [`frankfurter.py`](../../pt/data/frankfurter.py) | ECB via Frankfurter.dev | none | FX rates (latest, historical, time-series) | unlimited |
| [`finnhub.py`](../../pt/data/finnhub.py) | Finnhub | `FINNHUB_API_KEY` | Per-stock + market news, earnings calendar | 60/min |
| [`marketaux.py`](../../pt/data/marketaux.py) | Marketaux | `MARKETAUX_API_KEY` | Multi-asset news with built-in sentiment | 100/day |
| [`store.py`](../../pt/data/store.py) | — | — | `insert_candles`, `insert_fx_rates`, `latest_candle_time` | — |

## Output schema

Every price-fetcher returns `list[dict]` with the keys
`{time, symbol, interval, open, high, low, close, volume, source,
asset_type, exchange}`. `store.insert_candles` upserts on
`(time, symbol, interval)` so re-runs are cheap and safe.

FX fetchers (`frankfurter.to_market_meta_rows`) emit
`{time, source, symbol, value, metadata}` for `public.market_meta`.

News fetchers emit
`{time, source, symbol, asset_type, title, summary, url, sentiment, metadata}`
for `portfolio.asset_news` via `pt.db.news.upsert_many`. The DB upserts on
`(source, url)`.

## Symbol conventions

- **Crypto candles** are written with `symbol=f"{COIN_ID}-{VS_CURRENCY}"`
  in upper-case (e.g. `BITCOIN-USD`). The CoinGecko coin id (e.g. `bitcoin`)
  is normalised through a small alias table (`_CRYPTO_ID_ALIASES` in
  [`pt/api/routes/sync.py`](../../pt/api/routes/sync.py)) for the most
  common 15 symbols, otherwise lower-case-fallback. New aliases go there.
- **Stock candles** use the bare ticker (e.g. `AAPL`).
- **FX in `market_meta`** uses `<BASE><QUOTE>` (e.g. `EURUSD`). Triangulation
  via EUR is implemented in `pt.performance.money.convert` — no need to
  store cross-pairs explicitly when ECB has the rate vs EUR.

## CLI

```text
pt sync fx [--base EUR --quote USD --quote CHF --days N]
pt sync crypto --coin bitcoin --vs-currency usd --days 365
pt sync stock AAPL --interval 1day --outputsize 365
```

REST equivalents are at `/api/sync/{fx,crypto,stock}` — see
[api.md](api.md). The bulk endpoint
`POST /api/sync/portfolio/{id}/auto-prices` walks every open holding and
picks the right provider per asset_type.

## Tests

- [`tests/test_data_coingecko.py`](../../tests/test_data_coingecko.py),
  [`test_data_twelve_data.py`](../../tests/test_data_twelve_data.py),
  [`test_data_frankfurter.py`](../../tests/test_data_frankfurter.py) —
  pure unit tests via `httpx.MockTransport`. No real HTTP.
- [`tests/test_data_store.py`](../../tests/test_data_store.py) — integration
  against the live shared DB, writes synthetic `_PT_TEST_*` symbols and
  cleans them on teardown.

## Gotchas

- **`extra-index-url` in `~/.pip/pip.conf` may point at the markt
  artifactory.** Off-VPN, pip will hang trying to reach it before falling
  back. Set `PIP_EXTRA_INDEX_URL=` to disable, or just connect VPN.
- **Twelve Data interval strings** are renamed in the fetcher
  (`1day → 1d`, `1week → 1w`, etc.) so they match candles' interval
  convention. Do the renaming in the fetcher, never on the raw API value.
- **CoinGecko OHLC granularity is auto-picked**: 30m for ≤1d, 4h for ≤30d,
  1d for >30d. This is hard-coded in `_interval_for_days` — don't try to
  override it via params, the API simply returns whatever it returns and
  ignores the request.
- **Finnhub free tier returns NO sentiment**, even though the response
  schema has the field. We surface `sentiment=None` for finnhub items;
  Marketaux is the only provider currently writing real sentiment scores.
- **Marketaux emits one row per (article × matched-symbol).** A single
  article tagged for AAPL+MSFT becomes two rows so per-symbol queries
  don't have to LIKE the metadata. Same article URL is OK because the
  upsert is on `(source, url)` — but the symbol column changes, so you
  see the same article from each holding's perspective.
- **`fetch_general_news(category=...)`** writes with `symbol='_MARKET_'`
  so per-asset queries don't accidentally match it. Frontend currently
  ignores `_MARKET_`; render at the dashboard level if you ever surface it.
- **Rate-limit backoff is the caller's job.** Fetchers raise
  `httpx.HTTPStatusError` on 429 and propagate. Auto-prices in
  `routes/sync.py` already catches this and reports per-symbol; new bulk
  callers must do the same.
