# 2026-04-26 — Frontend UX redesign (Phase A)

## Outcome

Turned the portfolio tracker from a stat-card dashboard into an
insight-rich, chart-driven UI. **5 commits** on `main`, **+217 tests
green** (was 204 — added 13 around the new snapshot job + 4 new API
routes), full design-token migration, light/dark/system theme.

## What shipped

| Phase | Commit | What |
|--|--|--|
| A1 | `5d5d76e` | Design tokens (CSS vars), Light/Dark/System toggle, Settings page, ECharts core wired with theme bridge |
| A2 | `7f11d4d` | `pt sync snapshots` generator + 4 new API routes (`/snapshots`, `/candles`, `/sparklines`, extended `/performance/summary` with TWR/MWR/Risk timeseries) + client.ts mirrors |
| A3 | `8197f2c` | Dashboard rewrite (Hero KPIs, ECharts equity curve, top-movers, top-holdings + sparklines), AssetDetail price chart with tx markers + cost-basis priceLine via lightweight-charts v5 |
| A4 | `bb5483c` | Performance time-series (TWR/MWR/Risk cards + Equity+Drawdown), Allocation drillable Sunburst (asset_type → currency → symbol) + Donut variant, Holdings Treemap heatmap (size = market value, colour = unrealized %) |
| A5 | `11ab732` + (refs) | Transactions filter bar + audit-trail modal showing the DB-trigger's INSERT JSONB, full token migration of PdfImport + EmptyPortfolio, architecture-refs update |

## Architectural decisions

- **Chart library: Apache ECharts + lightweight-charts v5** — dropped the
  originally-planned `recharts` because it lacks Sunburst and has a
  weak Sankey, which would have forced a 3rd library. Verified 2026
  ecosystem state via three research agents (ApexCharts paid >$2M,
  Highcharts paid for commercial, Tremor is now Tremor Raw / wraps
  Recharts, Visx too low-level for a one-person project). ECharts
  covers donut/sunburst/treemap/heatmap/sankey/drawdown/sparkline on
  one tree-shaken canvas; lightweight-charts v5 handles the only
  finance-specific need (price + buy/sell markers + cost-basis line)
  natively.
- **Snapshot job is the data spine.** `portfolio.portfolio_snapshots`
  was a defined table that nothing wrote to. Without it there's no
  TWR / drawdown / equity curve. New `pt/jobs/snapshots.py` writes
  one row per (portfolio_id, snapshot_date) with FIFO cost-basis,
  realized-pnl-to-date, FX-naive total_value (per-asset_type +
  per-currency breakdown in `metadata` JSONB for the future allocation-
  over-time chart). `--backfill 365` is O(days × symbols) but uses
  the existing `latest_close_many(as_of=...)` so each day is one round-
  trip to TimescaleDB.
- **Token-driven theming, not Tailwind colour utilities.** All colours
  funnel through CSS variables on `:root[data-theme="light|dark"]`.
  Custom `light:` / `dark:` Tailwind variants registered for the
  occasional `bg-zinc-*` literal we still want. Charts read the same
  variables via `getComputedStyle` and re-mount on `pt:theme-change`
  — written into [`lib/echarts.ts`](../../frontend/src/lib/echarts.ts).
- **Vite dev port → 5175.** Prod docker stack already binds 5174 on
  the same machine. `.claude/launch.json` has `autoPort: true` as a
  fallback. The vite proxy keeps `/api` same-origin so CORS doesn't
  need updating.

## Findings worth keeping

- ECharts treemap couldn't be told to color by a non-value field via
  `colorMappingBy` + `visualDimension`; the cleanest path is to
  pre-compute `itemStyle.color` per tile based on `unrealized_pnl_pct`.
  Diverging palette `mix('#3f3f46', '#10b981'/'#e11d48', t)` with a
  ±10% saturation clamp works well for a dark-on-dark Finviz look.
- lightweight-charts v5 broke the `addLineSeries` / `series.setMarkers`
  API: now `chart.addSeries(LineSeries)` and the standalone
  `createSeriesMarkers(series, markers)` plugin. Documented in
  `references/charts.md` so future work doesn't accidentally code
  against v4 patterns.
- DB-stored candle intervals are inconsistent: Twelve Data writes
  `'1day'`, Binance/CoinGecko write `'1d'`. Extended
  `pt/db/prices.history(interval=...)` to accept a list and exposed
  `DAILY_INTERVALS = ('1day', '1d')` for the sparklines route to be
  source-agnostic. AssetDetail probes both per asset_type.

## Next-up

Per the approved plan in `.claude/plans/lass-uns-in-dieser-crispy-marshmallow.md`:

- **Defer**: Income page (dividend calendar — needs real dividend tx
  data), DE-Tax reports, contribution-to-return chart, correlation
  matrix, target-rebalance, ETF X-Ray.
- **Soon-ish**: FX-aware base-currency totals on the Dashboard hero
  (snapshot job already supports it via `pt.performance.money.convert`,
  just needs the FX backfill `pt sync fx --days 400` and a flag in
  the snapshot writer).
- **Later**: Benchmark overlay (S&P500 / MSCI World) on the equity
  curve (requires those symbols in `public.candles`).

## Stats

- Tests: 204 → **217** (+13 new in `tests/test_jobs_snapshots.py` and
  `tests/test_api_phase_a2.py`)
- LoC delta (frontend): roughly **+2700 / -200**
- Bundle add: `echarts@6` + `echarts-for-react@3` (~110 kB gz tree-
  shaken to the chart-types we actually use)
- Pages: 5 → **7** (Allocation, Settings added)
- Charts in production: **0 → 8** (equity curve, drawdown, sunburst,
  donut, treemap heatmap, sparkline, asset price chart with markers,
  per-row table sparkline)
