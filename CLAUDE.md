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
deep-dive map. Hub `SKILL.md` lists 11 references. Quick-orientation table:

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
| news fetching, sentiment, dormant LLM scaffold | `references/news-insights.md` |

## Hard rules (don't violate without good reason)

- **NEVER `float` for money.** Always `decimal.Decimal`. Rounding only at
  display via `pt.performance.money.quantize_money`. CI tests pin every
  formula against Excel-XIRR / CFA reference cases.
- **Holdings are derived from transactions.** No separate holdings table.
  Every read aggregates the tx log; correcting a wrong tx auto-corrects
  everything downstream.
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
  deferred until parallelism is a measurable bottleneck.

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

15 commits in. ~1750 LOC Python + ~1200 LOC TypeScript + 174 tests
green. PDF importer ships for LGT Bank Vermögensaufstellung; other
brokers are a registry-extension away. Next-up phases tracked in
`.claude/plans/portfolio-bootstrap.md`: Phase 7 (Tax DE-Reports),
Phase 8 (Allocation/Income/Settings pages), Phase 9 (claude-trader
bridge).
