# Portfolio Tracker

Multi-Asset-Portfolio-Tracking & Analyse — read-only, korrekte Zahlen, weltklasse UX.

> "Ich öffne die App, sehe in 3 Sekunden meinen Portfolio-Stand, was sich seit
> gestern/letzter Woche/seit Kauf getan hat, sehe pro Asset die wichtigsten News,
> und kann zu 100% den Zahlen vertrauen — egal ob Stocks, Crypto, ETFs, FX oder
> Rohstoffe."

## Was es kann

| Feature | Status |
|--|--|
| Multi-Asset (Stocks, ETFs, Crypto, FX, Commodities, Bonds) | ✓ |
| Manuelle Transaktions-Eingabe (Buy/Sell/Dividend/Split/Transfer/...) | ✓ |
| Audit-Trail per DB-Trigger (jede Änderung immutable) | ✓ |
| Multi-Asset-Sync: CoinGecko (free), Twelve Data (free key), Frankfurter (ECB, free) | ✓ |
| Performance-Engine: TWR, MWR/XIRR (Excel-kompatibel), Sharpe/Sortino/MaxDD/Calmar/Vola | ✓ |
| Cost-Basis-Methoden: FIFO / LIFO / Average mit Reference-Tests | ✓ |
| Realized-P&L-Reports mit Short-/Long-Term-Bucket | ✓ |
| Live-Pricing auf Holdings (Market Value, Unrealized P&L, Color-Code) | ✓ |
| News pro Asset (Finnhub + Marketaux), Sentiment-Color | ✓ |
| Strukturiertes Logging mit Request-IDs | ✓ |
| GitHub-Actions-CI für Backend + Frontend | ✓ |
| PDF-Importer (Trade Republic, Scalable) | geplant |
| LLM-Insights (OpenRouter via Frontend) | geplant |
| Tax-Reports (DE Format, Spekulationsfrist) | geplant |
| Allocation- / Income- / Settings-Pages | geplant |
| claude-trader-Bridge | geplant |

## Stack

| Layer | Technologie |
|--|--|
| Backend | Python 3.12, FastAPI, Typer-CLI, psycopg 3 |
| DB | TimescaleDB (geteilt mit `claude-trader`) |
| Frontend | React 19 + TS 5.9 + Vite 8 + Tailwind 4 + TanStack Query 5 + React Router 7 |
| Money-Math | `decimal.Decimal` — niemals Float für Geldbeträge |

## Quick Start

```bash
# 1) Shared TimescaleDB starten (aus claude-trader)
cd ../claude-trader && docker compose up -d timescaledb
cd ../portfolio

# 2) Python-Setup
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3) Schema migrieren
pt db migrate

# 4) Tests laufen lassen
pytest

# 5) Backend + Frontend starten (zwei Terminals)
PT_DB_PORT=5434 uvicorn pt.api.app:app --reload --port 8430
cd frontend && npm install && npm run dev   # → http://localhost:5174

# 6) CLI nutzen
pt portfolio create "Real-Depot" -c EUR
pt tx add -p 1 -s AAPL -t stock -a buy -q 10 --price 180.50 -c USD --executed-at 2025-01-15
pt sync crypto --coin bitcoin --days 30
pt holdings list -p 1
pt perf summary -p 1
```

## CLI

```text
pt --help

  db          migrate / status         schema apply + introspection
  portfolio   create / list / show / archive
  tx          add / list / show / audit / delete
  holdings    list / show              aggregated from transactions
  asset       add / list / show / find asset master metadata
  sync        fx / crypto / stock      pull market data into TimescaleDB
  perf        cost-basis / realized / summary    FIFO/LIFO/Avg + realized P&L
```

Every data command supports `--json` (machine-readable). Exit codes follow the
semantic convention: `0` ok, `2` usage, `3` not-found, `5` conflict.

## REST API

24+ endpoints under `/api/`. See `pt/api/routes/` or open the interactive docs
at `http://localhost:8430/docs` once the server is running. Highlights:

```
GET  /api/health                                 enriched probe (DB latency + counts)
POST /api/portfolios                             { name, base_currency }
GET  /api/portfolios/{id}/holdings               with_prices=true by default
POST /api/portfolios/{id}/transactions           single-buy/sell/...
GET  /api/portfolios/{id}/performance/summary    + cost-basis / realized
GET  /api/news/{symbol}/{asset_type}             cached news + 14d sentiment
POST /api/news/sync                              Finnhub + Marketaux refresh
POST /api/sync/portfolio/{id}/auto-prices        bulk price refresh per holding
```

Every response carries an `X-Request-ID` header — same id ends up in every
backend log line for that request.

## Repo-Struktur

```
pt/                      Python package
  cli.py                 Typer entry (`pt`)
  cli_*.py               sub-apps per domain
  api/
    app.py               FastAPI app + /api/health
    middleware.py        request-id + access-log middleware
    routes/              one router per domain
  db/                    psycopg helpers (no ORM)
    schema_portfolio.sql idempotent DDL
    portfolios.py / transactions.py / holdings.py / assets.py / prices.py
    news.py / insights.py / migrate.py / connection.py
  data/                  market-data fetchers
    coingecko.py / twelve_data.py / frankfurter.py / store.py
    finnhub.py / marketaux.py
  performance/           the math
    money.py             Decimal helpers + FX conversion
    cost_basis.py        FIFO / LIFO / Average
    twr.py / mwr.py      Time- + Money-Weighted Return (Excel-XIRR-compat)
    metrics.py           CAGR, Sharpe, Sortino, MaxDD, Calmar, Vol
  insights/              LLM scaffolding (dormant — moved to TS frontend later)
  tax/ audit/ trader_bridge/    placeholders for upcoming phases
  logging.py             stdlib JSON / human formatter

frontend/                React 19 + Vite + Tailwind 4
  src/
    App.tsx              router
    api/client.ts        typed REST client
    pages/               Dashboard, Holdings, Transactions,
                         Performance, AssetDetail
    components/          Layout, PortfolioPicker, EmptyPortfolio
    state/portfolio.ts   active-portfolio in localStorage
    lib/format.ts        fmtMoney / fmtPrice / fmtQty / pnlClass
  Dockerfile             multi-stage build → nginx
  nginx.conf             SPA fallback + /api proxy

tests/                   pytest, 166 tests, full happy-path + edge cases
docker-compose.yml       dev (uses claude-trader's TimescaleDB)
docker-compose.prod.yml  prod (api + frontend behind nginx)
.github/workflows/       CI (pytest + tsc + vite build)
```

## Deployment (production)

```bash
# Default: shared TimescaleDB with claude-trader
cd ../claude-trader && docker compose up -d timescaledb
cd ../portfolio
docker compose -f docker-compose.prod.yml up -d --build

# → http://localhost:5174   (frontend, /api proxied to api container)
```

Standalone DB (no claude-trader running): uncomment the `timescaledb` block in
`docker-compose.prod.yml` and set `PT_DB_HOST=pt-timescaledb`.

## Hard rules

- **NEVER `float` for money.** Always `Decimal`. Rounding only at display.
- **Holdings are derived, never stored as primary records.** Transactions are
  the single source of truth — correcting a wrong tx recomputes everything.
- **Audit is DB-enforced.** A trigger (`fn_log_transaction_audit`) writes
  every INSERT/UPDATE on transactions to `transaction_audit` automatically.
  Soft-delete (`UPDATE deleted_at`) preserves the history; hard-delete is
  test-only.
- **No trading.** This tool reads broker statements and live prices; it
  never writes to brokers, never executes orders.

## Status

8 commits, 166 tests, end-to-end live-verified Dashboard / Holdings /
Transactions / Performance / AssetDetail. Live-Pricing on holdings shows
real BTC/ETH market values from CoinGecko, color-coded gains/losses. AAPL
without a Twelve Data key falls back to "—" cleanly.

See `.claude/plans/portfolio-bootstrap.md` for the full implementation plan
and `git log --oneline` for the chronology.

## License

Privat / unveröffentlicht.
