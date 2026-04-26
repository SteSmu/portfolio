# REST API

FastAPI app at [`pt/api/app.py`](../../pt/api/app.py). Seven routers under
`/api/`. Pydantic v2 models on writes, dict responses on reads (FastAPI
auto-serializes Decimal as a JSON string — frontend keeps it as string and
never math's it).

## Routers

| Router | Prefix | Endpoints |
|--|--|--|
| [`portfolios.py`](../../pt/api/routes/portfolios.py) | `/portfolios` | `POST /` create, `GET /` list, `GET /{id}` get, `DELETE /{id}` archive |
| [`transactions.py`](../../pt/api/routes/transactions.py) | `/portfolios/{id}/transactions` | `POST /`, `GET /`, `GET /{tx_id}`, `DELETE /{tx_id}` (soft), `GET /{tx_id}/audit` |
| [`holdings.py`](../../pt/api/routes/holdings.py) | `/portfolios/{id}/holdings` | `GET /` (with `?with_prices=true` default), `GET /sparklines?days=N` (specific path BEFORE catch-all), `GET /{symbol}/{type}` |
| [`assets.py`](../../pt/api/routes/assets.py) | `/assets` | `POST /` upsert, `GET /` list, `GET /_search/{q}`, `GET /{symbol}/{type}/candles?start&end&interval&limit` (specific 3-segment path BEFORE catch-all), `GET /{symbol}/{type}` |
| [`performance.py`](../../pt/api/routes/performance.py) | `/portfolios/{id}/performance` | `GET /cost-basis`, `GET /realized` (year filter), `GET /summary` (now returns `timeseries` block — TWR/MWR/MaxDD/Vola/Sharpe/Calmar — null until snapshots exist) |
| [`snapshots.py`](../../pt/api/routes/snapshots.py) | `/portfolios/{id}/snapshots` | `GET /?from&to`, `POST /?backfill=N` (on-demand) |
| [`sync.py`](../../pt/api/routes/sync.py) | `/sync` | `POST /fx`, `POST /crypto`, `POST /stock`, `POST /portfolio/{id}/auto-prices` |
| [`news.py`](../../pt/api/routes/news.py) | `/news` | `GET /{symbol}/{type}`, `POST /sync` |
| [`imports.py`](../../pt/api/routes/imports.py) | `/portfolios/{id}/import` | `POST /pdf` (multipart, `?dry_run=bool`) — see [pdf-import.md](pdf-import.md) |

Plus `GET /api/health` (in `app.py`) returning status + version + DB
latency + per-table counts.

OpenAPI docs at [`http://localhost:8430/docs`](http://localhost:8430/docs)
when uvicorn is running.

## HTTP semantics

| Code | When |
|--|--|
| `200/204` | Success |
| `400` | Validation error from a `_db.*` helper or invalid query param |
| `404` | Not found (portfolio / tx / asset / holding) |
| `409` | Duplicate-name portfolio create |
| `502` | Upstream provider failed (Finnhub, Twelve Data, etc.) |

Every response carries `X-Request-ID` (echoes client's value if present,
otherwise a fresh uuid4 hex). Client errors are JSON `{"detail": "..."}`
per FastAPI convention.

## Middleware

[`pt/api/middleware.py`](../../pt/api/middleware.py):

- `RequestLogMiddleware` — logs every request as a single line with
  `extra={method, path, status, latency_ms}`. Suppresses noise for
  successful `/api/health` probes.
- `RequestIdLogFilter` — installed on the root logger via
  `install_logging_filter()`. Pulls `request_id` from a `contextvar` and
  stamps it on every record so any library that logs (psycopg, httpx,
  uvicorn, ...) gets the same id.

CORS is open for `localhost:5173/5174/8430`. `expose_headers=["X-Request-ID"]`
so the browser can read it.

## Pydantic models

Only on writes: `PortfolioCreate`, `TransactionIn`, `AssetUpsert`,
`SyncNewsBody`. Reads return plain dicts so we don't pay the validation
overhead on big lists. The frontend's `client.ts` mirrors the response
shapes with TypeScript types.

## Tests

- [`tests/test_api.py`](../../tests/test_api.py) — happy paths + error
  codes for every router via `fastapi.testclient.TestClient`.
- [`tests/test_api_news.py`](../../tests/test_api_news.py) — news routes
  including graceful-degradation when API keys are missing.

## Gotchas

- **Route ordering matters.** `/_search/{q}` MUST be declared BEFORE
  `/{symbol}/{asset_type}` in `assets.py` — otherwise FastAPI matches
  `/_search/foo` as `symbol="_search", asset_type="foo"` and returns 404.
  → fix: when adding any literal-prefix route to a router that has a
  catch-all path-param route, declare it first.
- **`with_prices=true` is the default on holdings.** This adds a
  `latest_close_many` join — single SELECT DISTINCT ON, fast even at 1000+
  holdings. Pass `?with_prices=false` if a caller only needs aggregation
  shape (e.g. nightly snapshot job).
- **`POST /api/news/sync` tolerates partial failure.** One provider failing
  doesn't fail the whole call — the response shape is `{rows_written:
  total, sources: {finnhub: {ok, ...}, marketaux: {ok, ...}}}`. New
  multi-provider endpoints should follow the same shape.
- **`POST /api/sync/portfolio/{id}/auto-prices` returns per-holding results.**
  Caller iterates `results[]` to display per-symbol successes/errors. Don't
  add a `raise HTTPException` mid-loop — that would fail the whole sync
  on the first bad symbol.
- **Decimal serialization.** FastAPI's default JSON encoder emits Decimal
  as `"123.45"` (string). Frontend's `client.ts` types money fields as
  `string` — display helpers parse via `Number(...)` only at render time.
  → fix: never `parseFloat` and arithmetically combine money strings in
  the frontend. Compute on the backend, return computed values.
- **Reload mode + module-level state.** `pt/api/app.py` calls
  `configure_logging()` and `install_logging_filter()` at import time.
  Under `uvicorn --reload` this re-runs on every reload — `configure`
  is idempotent so it's fine, but if you add new module-level side
  effects, make sure they're idempotent too.
