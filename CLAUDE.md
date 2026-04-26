# Portfolio Tracker — orientation for new sessions

This file is the entry point for any Claude session working in this repo.
Read it first; load the architecture skill for depth.

## What this is

Single-user, multi-asset portfolio tracking & analytics. **Read-only** —
never writes to brokers, never executes orders. Python 3.12 + FastAPI
backend, React 19 + Vite frontend, TimescaleDB (shareable with the sibling
`claude-trader` repo at `/Users/stefan/projects/private/prod/claude-trader/`).

## Where things live

The architecture skill at `.claude/skills/project-architecture/` is the
deep-dive map. Hub `SKILL.md` lists 12 references. Quick-orientation table:

| Want to ... | Read |
|--|--|
| change DB schema, write a query, touch the audit trigger | `references/db.md` |
| add a market-data source (prices, FX) | `references/data-fetchers.md` |
| touch TWR / MWR / cost-basis math | `references/performance.md` |
| add or change a REST route | `references/api.md` |
| add a `pt` sub-app | `references/cli.md` |
| build a frontend page or change formatting | `references/frontend.md` |
| add a broker PDF parser, debug OCR | `references/pdf-import.md` |
| edit Docker / nginx / CI / first-start init | `references/deployment.md` |
| trace a request, debug logging | `references/observability.md` |
| live-pricing on holdings | `references/pricing.md` |
| add a chart, theme tokens, pick ECharts vs lightweight-charts | `references/charts.md` |
| news fetching, sentiment, dormant LLM scaffold | `references/news-insights.md` |

## Hard rules (don't violate without good reason)

- **NEVER `float` for money.** Always `decimal.Decimal`. Rounding only at
  display via `pt.performance.money.quantize_money`. CI tests pin every
  formula against Excel-XIRR / CFA reference cases.
- **Holdings are derived from transactions.** No separate holdings table.
  Every read aggregates the tx log; correcting a wrong tx auto-corrects
  everything downstream.
- **Holdings SQL must mirror `cost_basis.py` semantics.** Both modules
  treat `transfer_in` as buy-equivalent (cost = qty × price + fees) and
  `transfer_out` as sell-equivalent. Drift between them silently zeros
  out cost basis for any portfolio populated solely via PDF import.
- **Audit is DB-enforced.** `fn_log_transaction_audit` writes audit rows
  on INSERT/UPDATE. Soft-delete (`UPDATE deleted_at`) preserves history;
  hard-delete is test-only and bypasses the audit FK by design.
- **Idempotent migrations.** `pt/db/schema_portfolio.sql` re-runs cleanly.
  New schema work goes in the same file — no alembic, no separate
  migration files.
- **Missing API keys are non-fatal.** Fetchers + sync routes return
  `{ok: false, error: "..."}` rather than crashing. Frontend surfaces
  the per-provider error breakdown.
- **Read-only-on-brokers.** No order execution, no broker writes. PDF
  imports, manual entry, and read-only price syncs only.
- **Symbol priority: ticker > ISIN > name.** PDF parsers populate
  `ParsedHolding.bloomberg_ticker` whenever the source carries one;
  `.symbol` resolves the priority cascade. Twelve Data + Yahoo both key
  off bare tickers — falling back to ISIN works for the holdings table
  but breaks `auto-prices`.
- **Skip > wrong-import.** When OCR / parsing can't recover a critical
  field (entry_price, entry_date), `to_transactions` returns no row
  rather than fabricating a value. A wrong cost basis contaminates all
  downstream P&L; a missing row is flagged in `warnings` and the user
  fills it in via `pt tx add`.

## Quick start

```bash
# Dev (uses claude-trader's TimescaleDB on :5434)
cd ../claude-trader && docker compose up -d timescaledb
cd ../portfolio
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pt db migrate                          # idempotent
pytest                                 # 174 tests
PT_DB_PORT=5434 uvicorn pt.api.app:app --reload --port 8430
cd frontend && npm install && npm run dev   # http://localhost:5174

# Prod (own TimescaleDB + persistent volume)
# On macOS, source .env first — Compose v2 may not auto-load it for substitution:
set -a && . .env && set +a
docker compose -f docker-compose.prod.yml up -d --build
# → http://localhost:5174
```

CLI cheat sheet:
```bash
pt portfolio create "Real-Depot" -c EUR
pt tx add -p 1 -s AAPL -t stock -a buy -q 10 --price 180.50 -c USD --executed-at 2025-01-15
pt sync crypto --coin bitcoin --days 30
pt holdings list -p 1
pt perf summary -p 1
```

## Conventions

- **Decimals as JSON strings** at the API boundary. The frontend renders
  via `fmtMoney` (locked 2 dp), `fmtPrice` (min 2, max N), `fmtQty`
  (min 0, max N). Never call `toLocaleString` directly in components,
  never combine money strings arithmetically client-side.
- **Tailwind v4 forbids `@apply` on self-defined classes.** Inline the
  utilities in each variant (`.btn-primary`, `.btn-ghost` are full
  utility-chains, not `@apply btn ...`).
- **Routers register specific paths BEFORE catch-alls.** `/_search/{q}`
  must come before `/{symbol}/{type}` in `pt/api/routes/assets.py`.
- **Idempotency at two layers** for any destructive-or-write operation:
  DB-level UNIQUE constraint + an `import_log` / `audit` row for human
  inspection.
- **Sync over async** for fetchers (`httpx.Client`). Async refactor
  deferred until parallelism is a measurable bottleneck. Yahoo fetcher
  wraps `yfinance` (synchronous scrape) and follows the same shape.
- **Provider-fallback chains** (e.g. Twelve Data → Yahoo for stock/etf)
  preserve the primary's error on the per-symbol outcome row even when
  the secondary succeeds, so the UI surfaces "got NOVN via Yahoo because
  TD said: needs Pro plan" rather than a silent provider switch. Bare
  ticker is the DB key regardless of provider; `_YAHOO_SYMBOL_MAP` in
  `pt/api/routes/sync.py` translates non-US tickers to Yahoo form.

## What lives elsewhere

- claude-trader (`/Users/stefan/projects/private/prod/claude-trader/`)
  is the sibling repo. Same DB, separate schema. Async fetchers, ML
  classifiers, LangChain agents, BTC-only trading focus. We share the
  `public.candles` + `public.market_meta` tables; we do not share any
  `portfolio.*` tables.
- LLM features go in the **frontend** via OpenRouter TS SDK (planned).
  `pt/insights/llm.py` + `outlook.py` are dormant scaffolding — don't
  wire them into live paths without checking the user's preference
  memory at `~/.claude/projects/-Users-stefan-.../portfolio/memory/`.
- Per-user / per-machine config in `.env` (gitignored). Defaults in
  `.env.example`.

## Status

217 tests green. PDF importer ships for LGT Bank Vermögensaufstellung
including OCR recovery for date / price-column fragments and Bloomberg
ticker extraction; other brokers are a registry-extension away
(`pt/importers/pdf/format_detect.py`).

Auto-prices supports CoinGecko (crypto), Twelve Data primary + Yahoo
Finance fallback (stock/etf). SIX Swiss listings (NOVN/ROG/SDZ) routed
directly to Yahoo via `_YAHOO_SYMBOL_MAP`.

**Frontend Phase A done** — UX redesign turned the tracker into an
insight tool. Equity curve + cost-basis overlay on the Dashboard,
TradingView-style asset chart with tx markers + cost-basis line on
AssetDetail, TWR/MWR/Risk cards + drawdown view on Performance,
drillable allocation sunburst, Finviz-style holdings treemap, per-row
sparklines, light/dark toggle backed by token-driven CSS variables.
Charts: **Apache ECharts** via the `lib/echarts.ts` theme bridge
(donut, sunburst, treemap, line, drawdown, sparkline) +
**lightweight-charts v5** for the AssetDetail price+marker chart.
Plan stayed `recharts`-free. New backend prereqs: `pt sync snapshots`
generator (idempotent UPSERT), `GET /api/portfolios/{id}/snapshots`,
`GET /api/assets/{symbol}/{type}/candles`, `GET .../holdings/sparklines`,
extended `/performance/summary` with a `timeseries` block (TWR / MWR /
max DD / vola / Sharpe / Calmar) — null until snapshots exist.

Next-up tracked in `.claude/plans/portfolio-bootstrap.md`: Phase 7 (Tax
DE-Reports), Phase 8 (Income / dividends, FX-aware base-currency
totals), Phase 9 (claude-trader bridge). LLM-insights via OpenRouter
TS still planned for the frontend.
