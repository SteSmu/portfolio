---
name: project-architecture
description: Architectural deep-dive for the portfolio tracker. Use when you need to know where things live, how data flows between Python backend and React frontend, which DB tables back which feature, how performance math is structured (TWR/MWR/cost-basis), how news + live-pricing + PDF-import pipelines work, where the audit trigger lives, how the API + CLI relate, how frontend pages map to API routes, where logging + request-ids hook in, how prod Docker + nginx are wired, where conventions diverge from claude-trader. Activate keywords - portfolio, holdings, transactions, performance engine, TWR, MWR, XIRR, cost basis, FIFO, LIFO, audit trigger, news, marketaux, finnhub, coingecko, twelve data, frankfurter, market_meta, candles, asset_news, asset_insights, insights, openrouter, llm, fastapi, typer, pt cli, react, vite, tailwind, tanstack query, holdings page, asset detail, performance page, transactions page, dashboard, request id, structured logging, json logging, healthcheck, docker prod, nginx, ci workflow, github actions, claude-trader bridge, decimal money math, frontend api client, fmtMoney fmtPrice fmtQty, pdf import, lgt bank, broker statement, vermögensaufstellung, pdfplumber, transfer_in, import_log, file_hash, idempotent import, ocr, dockerfile, docker-compose, docker-entrypoint-initdb, persistent volume, pt_db_data, multi-stage build.
---

# Portfolio Tracker — Architecture

Single-user portfolio analytics tool. Python 3.12 + FastAPI + Typer backend,
React 19 + Vite + Tailwind frontend, TimescaleDB shared with claude-trader.
**Read-only**: never writes to brokers, never executes orders.

The transaction log is the single source of truth — holdings, P&L,
performance metrics are all computed at query time. A DB trigger guarantees
every transactional change is audited.

## Quick orientation

| If you want to ... | Read |
|--|--|
| Touch DB schema, write a new query, add an audit-aware mutation | [db.md](references/db.md) |
| Add a new market-data source (prices, FX, candles) | [data-fetchers.md](references/data-fetchers.md) |
| Touch TWR / MWR / cost-basis / Sharpe / metrics math | [performance.md](references/performance.md) |
| Add a new REST route or change response shape | [api.md](references/api.md) |
| Add a new CLI sub-app or `pt` command | [cli.md](references/cli.md) |
| Build a new frontend page, change formatting, wire a new API call | [frontend.md](references/frontend.md) |
| Investigate logs, add tracing, debug request-id propagation | [observability.md](references/observability.md) |
| Touch news fetching, sentiment, or the dormant LLM-insights scaffold | [news-insights.md](references/news-insights.md) |
| Live-pricing on holdings (current_price, market_value, unrealized P&L) | [pricing.md](references/pricing.md) |
| Import a broker-statement PDF, add a new broker parser, debug OCR | [pdf-import.md](references/pdf-import.md) |
| Build/deploy Docker stack, edit nginx, change CI, schema bootstrap | [deployment.md](references/deployment.md) |

## Subsystems at a glance

### Database (`pt/db/`)
TimescaleDB shared with claude-trader. Two schemas: `public` (candles +
market_meta — owned by claude-trader, augmented with `asset_type` + `exchange`
columns) and `portfolio` (assets, portfolios, transactions, audit, news,
insights, snapshots). One idempotent SQL file does the migration. A
PostgreSQL trigger `fn_log_transaction_audit` writes audit rows on every
INSERT/UPDATE on transactions automatically.
-> Details: [db.md](references/db.md)

### Data fetchers (`pt/data/`)
Six sync httpx clients: CoinGecko (free), Twelve Data (key), Frankfurter (ECB,
free), Finnhub (key), Marketaux (key), Binance (claude-trader-shared). All
write into `public.candles` (prices) or `public.market_meta` (FX) via
`store.insert_candles` / `store.insert_fx_rates`. News fetchers write into
`portfolio.asset_news` via `pt.db.news.upsert_many`.
-> Details: [data-fetchers.md](references/data-fetchers.md)

### Performance engine (`pt/performance/`)
Decimal-only math, regression-tested against Excel XIRR + hand-computed
reference cases. Five modules: `money` (Decimal helpers + ECB-rate FX
conversion), `cost_basis` (FIFO/LIFO/Average tax-lot tracking), `twr`
(Time-Weighted Return), `mwr` (Money-Weighted Return / XIRR via
Newton-Raphson + bisection fallback), `metrics` (CAGR / Sharpe / Sortino /
MaxDD / Calmar / Vol).
-> Details: [performance.md](references/performance.md)

### REST API (`pt/api/`)
FastAPI app, 7 routers under `/api/`. Pydantic v2 on writes, dict responses
on reads (FastAPI auto-serializes Decimal). Errors map to standard HTTP:
400 usage / 404 not-found / 409 conflict / 502 upstream-down. Every
response carries `X-Request-ID`. CORS open for `:5173/:5174/:8430`.
-> Details: [api.md](references/api.md)

### CLI (`pt/cli*.py`)
Typer entry `pt`, 7 sub-apps mirroring the API one-for-one (`db`, `portfolio`,
`tx`, `holdings`, `asset`, `sync`, `perf`). Every data-producing command
ships `--json`. Semantic exit codes (0 ok / 2 usage / 3 not-found /
5 conflict).
-> Details: [cli.md](references/cli.md)

### Frontend (`frontend/`)
React 19 + TS 5.9 + Vite 8 + Tailwind 4 + TanStack Query 5 + React Router 7.
Five pages (Dashboard, Holdings, Transactions, Performance, AssetDetail) hit
the API via a typed `client.ts`. localStorage-backed active-portfolio hook
keeps multiple `<PortfolioPicker>` instances in sync. Money never gets
math'd in the frontend — display only.
-> Details: [frontend.md](references/frontend.md)

### Observability (`pt/logging.py` + `pt/api/middleware.py`)
Stdlib-only logger (no extra deps). Two formatters: human (TTY colour) +
JSON (one obj per line). `RequestLogMiddleware` generates / echoes
`X-Request-ID`, `RequestIdLogFilter` propagates it via `contextvar` so any
library that logs sees the id. Health probe reports DB latency + per-table
counts.
-> Details: [observability.md](references/observability.md)

### News + Insights (`pt/data/{finnhub,marketaux}.py`, `pt/db/{news,insights}.py`)
Two news providers (Finnhub for stocks, Marketaux for multi-asset with
built-in sentiment). Per-asset cache in `portfolio.asset_news`, idempotent
on `(source, url)`. AssetDetail page shows the feed + 14d avg sentiment +
manual "Refresh" button. The `pt/insights/llm.py` + `pt/insights/outlook.py`
files are deliberately dormant scaffolding — LLM features will live in the
TS frontend via OpenRouter SDK in a later phase.
-> Details: [news-insights.md](references/news-insights.md)

### Live-pricing (`pt/db/prices.py`, `pt/api/routes/sync.py`)
Holdings auto-enrich with the latest close per `(symbol, asset_type)` from
`public.candles`. `POST /api/sync/portfolio/{id}/auto-prices` bulk-syncs
every open holding through the right provider (CoinGecko for crypto,
Twelve Data for stock/etf), tolerating partial failures. UI colours unrealized
P&L green/red.
-> Details: [pricing.md](references/pricing.md)

### PDF importer (`pt/importers/pdf/`)
Generic registry-based pipeline that ingests broker-statement PDFs as
`transfer_in` transactions. One concrete parser today (LGT Bank
Vermögensaufstellung) using x-coordinate column extraction to survive
OCR noise. Idempotency at two layers (`import_log.file_hash` + per-tx
UNIQUE `source_doc_id`). Frontend widget on Holdings page provides
file → dry-run preview → confirm.
-> Details: [pdf-import.md](references/pdf-import.md)

### Deployment (`Dockerfile`, `frontend/Dockerfile`, `docker-compose.prod.yml`)
Three-container production stack: `pt-timescaledb` (own DB, persistent
named volume `pt_db_data`), `pt-api` (uvicorn JSON logs, internal-only),
`pt-frontend` (nginx 1.27 multi-stage, host `:5174 → 80`, proxies `/api`
to `pt-api:8430`). Schema bootstraps via TimescaleDB's
`/docker-entrypoint-initdb.d/` hook on first start. GitHub Actions runs
pytest + tsc + vite build on push.
-> Details: [deployment.md](references/deployment.md)

## Cross-cutting conventions

- **Decimal everywhere for money.** Never `float`. Rounding only at display
  via `pt.performance.money.quantize_money`.
- **Holdings are derived.** Aggregated from transactions on every read. No
  separate holdings table.
- **Audit is DB-enforced.** A trigger writes audit rows on INSERT/UPDATE.
  Soft-delete via `UPDATE deleted_at` preserves history; hard-delete is
  test-only and skips the trigger by design.
- **Idempotent migrations.** `schema_portfolio.sql` re-runs cleanly. New
  schema work goes in the same file, never as separate migrations.
- **Env-driven config.** `PT_DB_*` for DB, `PT_LOG_FORMAT/LEVEL` for logs,
  per-provider `*_API_KEY` for fetchers. Missing keys cause graceful
  degradation, not crashes.
- **Number formatting in the frontend.** `fmtMoney` (locked 2 decimals),
  `fmtPrice` (min 2, max N — strips trailing zeros past cents), `fmtQty`
  (min 0, max N). Never call `toLocaleString` directly in components.

## Where this differs from claude-trader

- **Same DB instance, different schema.** Portfolio tables live under
  `portfolio.*`. The `public.candles` table is shared and was augmented
  with `asset_type` + `exchange` columns — `'crypto'` is the default so
  claude-trader behaviour is unchanged.
- **No LLM in the live path.** claude-trader uses LangChain + OpenRouter
  from Python. Portfolio puts the LLM step in the frontend via the
  OpenRouter TS SDK (planned). The backend `pt/insights/llm.py` is dormant
  scaffolding.
- **Sync over async.** Fetchers use `httpx.Client` (sync). Async refactor
  deferred until parallelism becomes a measurable bottleneck.
- **No ML.** Cost-basis + statistical metrics live here, but the regime/
  volatility classifiers and TCN sequence models are claude-trader-only.
