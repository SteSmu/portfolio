# Frontend (`frontend/`)

React 19 + TS 5.9 + Vite 8 + Tailwind 4 + TanStack Query 5 + React
Router 7. **Token-driven theming** (`light` / `dark` / `system`) via
CSS variables — no zinc-* classes leak past `index.css`. Mobile-
friendly via Tailwind responsive utilities. Vite proxies `/api` →
`http://localhost:8430` in dev. Dev port is 5175 (5174 reserved for
the prod docker stack on the same machine).

## Pages

| Page | Path | What it shows | Talks to |
|--|--|--|--|
| [`Dashboard.tsx`](../../frontend/src/pages/Dashboard.tsx) | `/` | Hero KPI grid (value + 1d/7d/1Y delta, cost basis, unrealized, realized), ECharts equity curve with cost-basis overlay + period selector, Top-Movers, Top-Holdings with per-row sparklines, Activity card, "no snapshots" CTA → POST snapshots backfill | `performanceSummary`, `listHoldings`, `listSnapshots`, `holdingSparklines`, `generateSnapshots` |
| [`Holdings.tsx`](../../frontend/src/pages/Holdings.tsx) | `/holdings` | Stat cards (market value / unrealized / cost), table with 30d sparkline column, **Heatmap toggle** (Finviz-style ECharts treemap, size = market value, colour = unrealized %), "Refresh prices" | `listHoldings`, `holdingSparklines`, `syncPortfolioPrices` |
| [`Allocation.tsx`](../../frontend/src/pages/Allocation.tsx) | `/allocation` | ECharts **sunburst** (asset_type → currency → symbol) with focus-on-ancestor drilldown; donut variant; **over-time stacked area** (per-snapshot `metadata.by_asset_type` history); per-asset-class breakdown cards | `listHoldings`, `listSnapshots` |
| [`Performance.tsx`](../../frontend/src/pages/Performance.tsx) | `/performance` | Three KPI cards (TWR period+annualized, MWR/XIRR, Risk: vola/MaxDD/Sharpe/Calmar) — populated from `summary.timeseries`. Equity curve + drawdown stack. Method/Year filters, realized summary + open-lots + matches tables | `performanceSummary`, `costBasis`, `realized`, `listSnapshots` |
| [`AssetDetail.tsx`](../../frontend/src/pages/AssetDetail.tsx) | `/asset/:symbol/:assetType` | TradingView-style price chart (lightweight-charts v5) with buy/sell markers + horizontal cost-basis priceLine, period selector, **"Show news" toggle** (overlays sentiment-tinted news dots; click opens article URL), position summary, tx table, news feed with sentiment | `listHoldings`, `listTransactions`, `listCandles`, `listNews`, `syncNews` |
| [`Transactions.tsx`](../../frontend/src/pages/Transactions.tsx) | `/transactions` | Add-form + filter bar (symbol/action/year), source-doc-id badges, click row → audit modal showing INSERT/UPDATE/DELETE history with JSONB diff | `listTransactions`, `createTransaction`, `deleteTransaction`, `txAudit` |
| [`Settings.tsx`](../../frontend/src/pages/Settings.tsx) | `/settings` | Theme toggle (dark/light/system), active portfolio metadata, backend health (status / DB latency / table counts), data-provider tier list | `getPortfolio`, `health` |
| [`YearInReview.tsx`](../../frontend/src/pages/YearInReview.tsx) | `/year/:year` | Parqet-Wrapped-style retro: hero total return + sparkline backdrop, best/worst calendar month, best ISO week, top-realized symbol, activity counters. Pure derivation from snapshots + tx-log + realized — no new API surface. Year nav buttons jump ±1 year. | `listSnapshots`, `listTransactions`, `realized` |

## Building blocks

| File | Purpose |
|--|--|
| [`App.tsx`](../../frontend/src/App.tsx) | Router (7 routes: Dashboard, Holdings, Allocation, Performance, Transactions, Settings, AssetDetail) |
| [`main.tsx`](../../frontend/src/main.tsx) | QueryClient (30s staleTime, 1 retry) + BrowserRouter |
| [`api/client.ts`](../../frontend/src/api/client.ts) | Typed REST client + types (Portfolio, Transaction, Holding, NewsItem, **Snapshot, Candle, SparklinesResponse, PerformanceSummary.timeseries**, etc.) |
| [`lib/format.ts`](../../frontend/src/lib/format.ts) | `fmtMoney` / `fmtPrice` / `fmtQty` / `fmtPct` / `fmtDate` / `pnlClass` / `pnlSign` |
| [`lib/echarts.ts`](../../frontend/src/lib/echarts.ts) | Tree-shaken ECharts core + `useChartTheme()` hook that re-derives the chart palette from CSS vars on every theme switch |
| [`state/portfolio.ts`](../../frontend/src/state/portfolio.ts) | `useActivePortfolio()` — localStorage-backed active id with cross-component sync via tiny event bus |
| [`state/theme.ts`](../../frontend/src/state/theme.ts) | `useTheme()` — `'dark'\|'light'\|'system'`, dispatches `pt:theme-change` so chart wrappers re-mount with the new palette |
| [`components/Layout.tsx`](../../frontend/src/components/Layout.tsx) | Sticky header (nav + portfolio picker + theme toggle + db-health badge), main, footer |
| [`components/ThemeToggle.tsx`](../../frontend/src/components/ThemeToggle.tsx) | 3-state radio group (dark/light/system) wired to `useTheme()` |
| [`components/PeriodSelector.tsx`](../../frontend/src/components/PeriodSelector.tsx) | Pill-button group `1W/1M/3M/YTD/1Y/ALL` + `periodStart()` ISO helper |
| [`components/PortfolioPicker.tsx`](../../frontend/src/components/PortfolioPicker.tsx) | `<select>` of portfolios, auto-picks first when nothing active |
| [`components/EmptyPortfolio.tsx`](../../frontend/src/components/EmptyPortfolio.tsx) | First-run onboarding (creates first portfolio inline) |
| [`components/PdfImport.tsx`](../../frontend/src/components/PdfImport.tsx) | Drop-in PDF upload widget (file → dry-run preview → confirm → write). Mounted on Holdings (also visible on the empty-state). See [pdf-import.md](pdf-import.md). |
| [`components/BenchmarkPicker.tsx`](../../frontend/src/components/BenchmarkPicker.tsx) | `<select>` over `GET /api/benchmarks` (SPY / URTH / IWDA / QQQ + "none") + an inline `⟳` refresh button that fires `syncBenchmark(symbol, 365)` for the active selection and invalidates the candles query. Selection persisted in localStorage under `pt:benchmark` via [`state/benchmark.ts`](../../frontend/src/state/benchmark.ts). Mounted on Dashboard + Performance equity-curve cards. |
| [`components/BenchmarkSyncBanner.tsx`](../../frontend/src/components/BenchmarkSyncBanner.tsx) | CTA banner rendered above the equity curve when a benchmark is selected but `useBenchmarkOverlay()` returns an empty series despite `visibleSnaps.length >= 2` (i.e. catalog has no candles cached yet). Click → `POST /benchmarks/{symbol}/sync?days=365`, then invalidates `['benchmark-candles', symbol, asset_type]` so the line appears as soon as the rows land. Dashboard + Performance both mount it. |
| [`lib/benchmark.ts`](../../frontend/src/lib/benchmark.ts) | `useBenchmarkOverlay(selected, visibleSnaps)` hook — pulls candles via `listCandles()`, normalises to portfolio start (factor = `first_total_value / first_close`), trims to the snapshot window, returns `{name, series}` ready for `<EquityCurve benchmark>`. |
| [`components/charts/Chart.tsx`](../../frontend/src/components/charts/Chart.tsx) | Thin ECharts wrapper: init / setOption / dispose, ResizeObserver, theme re-mount |
| [`components/charts/EquityCurve.tsx`](../../frontend/src/components/charts/EquityCurve.tsx) | ECharts line — total value + cost-basis dashed overlay + optional `benchmark` prop (start-aligned ratio-scaled overlay in `var(--cat-3)`). Wrapper is normalisation-agnostic; the parent supplies the scaled `[isoDate, value]` series via `useBenchmarkOverlay()`. |
| [`components/charts/DrawdownChart.tsx`](../../frontend/src/components/charts/DrawdownChart.tsx) | ECharts area chart, peak-to-trough %, always negative |
| [`components/charts/Sparkline.tsx`](../../frontend/src/components/charts/Sparkline.tsx) | Tiny inline trend, gain/loss tinted, used in Holdings table + Top-Holdings card |
| [`components/charts/AllocationSunburst.tsx`](../../frontend/src/components/charts/AllocationSunburst.tsx) | Drillable sunburst (asset_type → currency → symbol) + donut variant |
| [`components/charts/AllocationOverTime.tsx`](../../frontend/src/components/charts/AllocationOverTime.tsx) | Stacked-area allocation history. One series per asset_type, value from each snapshot's `metadata.by_asset_type`. Colours come from the theme palette (`--cat-1..8`) — never set `color: var(--cat-N)` on `areaStyle`, ECharts cannot resolve CSS vars there. |
| [`components/charts/HoldingsTreemap.tsx`](../../frontend/src/components/charts/HoldingsTreemap.tsx) | Finviz-style treemap, size=market_value, colour=unrealized %, click→AssetDetail |
| [`components/charts/AssetPriceChart.tsx`](../../frontend/src/components/charts/AssetPriceChart.tsx) | lightweight-charts v5 line + `createSeriesMarkers` (buy/sell/transfer arrows) + `createPriceLine` (cost-basis dashed) |

## Number-formatting rules

| Helper | Min dec | Max dec | Use for |
|--|--|--|--|
| `fmtMoney` | 2 | 2 | Fiat amounts, total cost, market value, P&L. Always shows cents |
| `fmtPrice` | 2 | 4 | Per-unit prices (avg cost, current price). Shows cents always, strips trailing zeros past cents |
| `fmtQty`   | 0 | 8 | Quantities. `8`, `0,5`, `0,12345678` — no trailing zeros |
| `fmtPct`   | — | 2 | `+12.34%` — input is a ratio (`0.1234`), output is percent |

`pnlClass(value)` returns `'gain'` / `'loss'` / `'flat'` for color-coding.
Defined in [`index.css`](../../frontend/src/index.css) as Tailwind composites.

## Active-portfolio hook

`useActivePortfolio()` is intentionally minimal — no Redux, no Zustand. A
module-level `Set` of subscribers keeps multiple `<PortfolioPicker>` (or
any component using the hook) in sync after a `setActive(id)` call.
Survives page reload via `localStorage`.

## API integration patterns

```ts
const { data, isLoading, error } = useQuery({
  queryKey: ['holdings', activeId],
  queryFn: () => api.listHoldings(activeId!),
  enabled: activeId != null,
})

const sync = useMutation({
  mutationFn: () => api.syncPortfolioPrices(activeId!),
  onSuccess: () => qc.invalidateQueries({ queryKey: ['holdings', activeId] }),
})
```

Decimal values arrive from the API as strings. Display helpers parse via
`Number(...)` only at the render boundary. **Never** combine money strings
arithmetically — the backend is the source of truth for sums.

## Production build

[`Dockerfile`](../../frontend/Dockerfile) is multi-stage: node 20 builds the
SPA, nginx 1.27 serves it. [`nginx.conf`](../../frontend/nginx.conf) does:
- Long-cache hashed assets (`/assets/*`, 1y immutable)
- Proxy `/api/*` to `pt-api:8430` (the docker-compose service name)
- SPA fallback (`try_files $uri /index.html`)
- No access log on `/api/health`

## Gotchas

- **Tailwind v4 forbids `@apply` on self-defined classes.** A class
  definition cannot reference another class defined in the same `@layer
  components` block. The build fails with "Cannot apply unknown utility
  class". → fix: inline the utilities in each variant. Example: `.btn-primary`
  contains the rounded/px/py/text-sm chain plus its own bg/text — no
  `.btn` base class.
- **Money math in the frontend = bug.** The backend returns Decimal
  strings; the frontend renders them. The Dashboard total in the
  Holdings page does sum `Number(h.market_value)` for the stat card, which
  is acceptable because the API guarantees those values are already
  reconciled — but never compute realized P&L or rebalance percentages
  client-side.
- **`with_prices=true` is the default on `listHoldings`.** Optional
  fields (`current_price`, `market_value`, `unrealized_pnl`,
  `unrealized_pnl_pct`) may be `null` when no candle exists for an asset.
  Always render `—` for null instead of crashing on `Number(null)`.
- **`encodeURIComponent` on the symbol** in router links is required —
  symbols like `BITCOIN-USD` work, but anything containing a slash (rare
  for tickers) would otherwise break path matching.
- **Vite HMR can show stale CSS errors after fixing them.** A failed
  Tailwind compile may stick on screen until you `location.reload()`
  manually. Don't chase ghosts — refresh first, then debug.
- **TypeScript strict mode is on.** `verbatimModuleSyntax`,
  `erasableSyntaxOnly`, `noUnusedLocals`, etc. Imports must use `import
  type { ... }` for type-only symbols, otherwise the build fails.
- **`tsconfig.node.json` has `types: []`** (was `["node"]` originally) —
  we don't ship `@types/node` since vite.config.ts doesn't import any
  node API. If you ever need `process.env.X` in `vite.config.ts`, add
  `@types/node` to devDependencies and flip this back.
- **Vite dev port 5175 (was 5174).** Reserved for the prod docker stack
  on the same machine. Set in `.claude/launch.json`; `vite.config.ts`
  still defaults to 5174 if you launch vite directly without `--port`.
  Backend port 8430 unchanged. CORS in `pt/api/app.py` allows
  `5173/5174/8430`; with the vite proxy `/api` is same-origin so 5175
  doesn't need a CORS entry.
- **Charts: ECharts for ~everything, lightweight-charts for the asset
  price chart.** See [charts.md](charts.md). Don't reach for a 3rd
  library — ECharts already covers donut/sunburst/treemap/heatmap/
  drawdown/sankey first-class on a single canvas.
- **Theme tokens, not Tailwind colours.** New code should pull colour
  from `var(--bg-base)` / `var(--text-primary)` / `var(--gain)` /
  `var(--accent)` etc. New `bg-zinc-*` / `text-emerald-*` literals will
  break light-mode rendering — `index.css` is the only place hex
  values appear.
- **Routing rule: 3-segment paths inside a router with a 2-segment
  catch-all.** `assets.py` has `/{symbol}/{asset_type}` (catch-all) and
  `/{symbol}/{asset_type}/candles` (specific). Register the specific
  one BEFORE the catch-all, just like `/_search/{q}`. Same pattern
  applied for `/holdings/sparklines` vs `/holdings/{symbol}/{type}`.
