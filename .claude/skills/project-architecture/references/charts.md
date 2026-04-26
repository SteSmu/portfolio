# Charts

Two libraries split by purpose:

| Use | Library | Why |
|--|--|--|
| Equity curve, drawdown, allocation donut/sunburst, holdings treemap heatmap, sparklines, dividend bars (future), correlation heatmap (future), sankey (future) | **Apache ECharts** via [`lib/echarts.ts`](../../frontend/src/lib/echarts.ts) | One library covers donut/sunburst/treemap/heatmap/sankey on a single canvas. Tree-shaken (`echarts/core` + only the chart types and components we register) → ~110 kB gz. First-class TS, React 19 OK. |
| AssetDetail price chart with buy/sell markers + horizontal cost-basis line | **lightweight-charts v5** | Built for finance: `createSeriesMarkers` plugin pins markers above/below bars, `createPriceLine` for the cost-basis horizontal, multi-pane support. ~35 kB gz. Other libs need wrapping to do this; lightweight-charts does it natively. |

Both wrappers re-mount on theme change so the palette stays readable.
**Never** install a third charting library — Recharts (planned originally)
was dropped because it lacks Sunburst and has a weak Sankey, which would
have pushed us to a 3-lib zoo.

## ECharts wrapper — [`components/charts/Chart.tsx`](../../frontend/src/components/charts/Chart.tsx)

```tsx
<Chart option={option} height={300} onClick={(p) => ...} />
```

Internally:
1. `useChartTheme()` from [`lib/echarts.ts`](../../frontend/src/lib/echarts.ts)
   reads CSS variables (`--bg-base`, `--text-primary`, `--chart-grid`,
   `--gain`, `--loss`, `--accent`, `--cat-1..8`) and registers an ECharts
   theme `pt-dark` / `pt-light`. Theme name + a bump key are returned;
   the wrapper destroys & re-inits the chart whenever the bump changes
   (i.e. when the user toggles the theme).
2. `ResizeObserver` calls `chart.resize()` on container width changes.
3. `setOption(option)` runs on every `option` prop change without
   re-mounting (animation is preserved).

Only registered chart-types are available on `Chart`. Adding a new chart
type means `echarts.use([NewChart])` inside `lib/echarts.ts` — keep this
explicit, not auto-imported.

## lightweight-charts wrapper — [`components/charts/AssetPriceChart.tsx`](../../frontend/src/components/charts/AssetPriceChart.tsx)

v5 API (DON'T fall back to v4 docs):

```tsx
import { createChart, LineSeries, createSeriesMarkers } from 'lightweight-charts'

const chart = createChart(container, options)
const series = chart.addSeries(LineSeries, { color, lineWidth: 2 })
series.setData([{ time: utcSeconds, value: number }, ...])
const markers = createSeriesMarkers(series, [
  { time, position: 'belowBar', shape: 'arrowUp',   color: gain, text: 'buy 0.1 @ 84000' },
  { time, position: 'aboveBar', shape: 'arrowDown', color: loss, text: 'sell 0.1 @ 98000' },
])
markers.setMarkers(nextMarkers)  // mutate without re-mount
const pl = series.createPriceLine({ price: avgCost, lineStyle: 2, axisLabelVisible: true, title: 'cost basis' })
series.removePriceLine(pl)        // strip stale lines on data update
```

Time is `UTCTimestamp = unix-seconds`. The wrapper re-mounts on theme
change (via the `useTheme()` hook's `resolved` value) so the colour-
scheme switch is instant.

**Marker primitive lifecycle.** `createSeriesMarkers(series, [...])` returns
an `ISeriesMarkersPluginApi` — keep it in a ref and call `setMarkers(...)`
on subsequent updates instead of calling `createSeriesMarkers` again
(each call attaches a fresh plugin and the old markers stay until
unmount). Same for `createPriceLine`: track the returned `IPriceLine` and
`series.removePriceLine(pl)` before adding a new one, otherwise stale
lines stack up.

**News overlay (optional).** When `showNews` is true, AssetPriceChart
draws one `circle`/`inBar` marker per `NewsItem` at `published_at`,
tinted by `sentiment` (>0 gain, <0 loss, 0 grey). Items on the same UTC
day are de-duplicated to the strongest-sentiment one to keep the chart
readable. A click handler subscribed via `chart.subscribeClick` snaps to
the nearest news pin within ±1 day and opens the article URL in a new
tab — there is no per-marker click event in v5, so proximity is the only
way to map a click back to a marker.

## Theme tokens used by charts

Defined in [`index.css`](../../frontend/src/index.css) on `:root` and
`:root[data-theme="light"]`. Charts read them via `getComputedStyle` —
either through `lib/echarts.ts:readChartTokens()` for ECharts or
`readVar()` inside `AssetPriceChart.tsx`.

| Token | Used by |
|--|--|
| `--bg-base`, `--bg-elev` | chart background, tooltip border |
| `--chart-grid`, `--chart-axis` | grid lines + axis labels |
| `--text-primary`, `--text-secondary`, `--text-tertiary` | tooltip + label text |
| `--gain`, `--loss`, `--flat` | buy/sell markers, P&L colour, drawdown fill |
| `--accent` | line colour for the asset price chart |
| `--cat-1..8` | categorical palette for sunburst / donut / treemap (each variant has a 2026-suitable accessible palette) |
| `--chart-tooltip-bg`, `--chart-tooltip-border` | tooltip box |

Light + dark have their own colour values for every token; the chart
theme bridge re-derives all colours when the toggle fires.

## Adding a new chart

1. Pick the library: ECharts unless it's a financial OHLC + markers
   chart (then lightweight-charts).
2. If ECharts and the chart type is new (e.g. you want a `RadarChart`):
   import + `echarts.use([RadarChart])` inside `lib/echarts.ts`.
3. Build a wrapper component under `components/charts/` that takes
   typed props (NOT the raw ECharts option) and computes the option
   inline. Example in [`EquityCurve.tsx`](../../frontend/src/components/charts/EquityCurve.tsx).
4. In the wrapper, prefer `var(--token)` over hex literals for any
   colour the user might see. ECharts accepts `var(...)` strings
   wherever a colour is expected.
5. Use `<Chart option={...} height={...} />` — never call
   `echarts.init` directly outside `Chart.tsx`, otherwise the chart
   loses theme-switch handling and the resize observer.

## Benchmark overlay normalisation

Pattern used by `EquityCurve`'s `benchmark` prop (Dashboard + Performance):

1. Pull benchmark candles via `api.listCandles(symbol, asset_type)` —
   no dedicated endpoint, candles are already keyed off `(symbol,
   asset_type)` in `public.candles`.
2. **Trim to the snapshot window** (`candle.time >= visibleSnaps[0].date`).
   Without this, the benchmark line predates the portfolio's first
   snapshot and skews the visual comparison.
3. **Start-aligned ratio scale**:
   `factor = first_visible_snapshot.total_value / first_in-window_close`,
   then `scaled_close = close * factor` per point. The first plotted
   benchmark point therefore equals the portfolio's starting value, and
   subsequent points encode relative performance only — outperformance
   shows as the benchmark line drifting below the equity curve, and
   vice versa.
4. The wrapper (`EquityCurve.tsx`) is intentionally normalisation-agnostic
   — the parent (`Dashboard`/`Performance`) feeds an already-scaled
   `series: Array<[isoDate, number]>`. The shared hook is
   [`lib/benchmark.ts:useBenchmarkOverlay`](../../frontend/src/lib/benchmark.ts).
5. **Edge case — fewer snapshots than benchmark history.** When the user
   has only e.g. 30 snapshots but synced 365d of SPY, the trim step
   (#2) discards the SPY history before the 30-day window. The line
   appears short, anchored at the same start point as the equity
   curve, never extending past the portfolio's actual lifetime.
6. **Edge case — fewer benchmark candles than snapshots.** If the user
   selected a benchmark and never ran `POST /api/benchmarks/{symbol}/sync`,
   the candle history is empty and the overlay returns
   `{name, series: []}` — `EquityCurve` simply omits the line. No error,
   no implicit fetch — the picker / a future explicit "sync" button is
   the place to trigger backfill.

## Benchmark sync UX

`<BenchmarkPicker>` exposes a small `⟳` button that fires
`api.syncBenchmark(symbol, 365)` for the current selection and
invalidates `['benchmark-candles', symbol, asset_type]` so the overlay
appears as soon as the rows land. Parents (Dashboard + Performance)
additionally render `<BenchmarkSyncBanner>` above the equity curve when
the user has a selection but `useBenchmarkOverlay()` returns
`{name, series: []}` despite `visibleSnaps.length >= 2` — that combination
means the catalog has no candles yet and an explicit one-shot sync is
the only way out (the hook deliberately does not auto-fetch).

## Gotchas

- **lightweight-charts v5 ≠ v4.** v4 used `chart.addLineSeries()`; v5
  uses `chart.addSeries(LineSeries, ...)`. Markers moved from
  `series.setMarkers()` (v4) to the standalone `createSeriesMarkers()`
  primitive plugin (v5). When debugging, check the installed version
  in `package.json` first.
- **ECharts cannot resolve `var(--token)` on every property.** The
  `theme.color` array (read from `--cat-1..8` via `readChartTokens()`)
  reaches the canvas, but per-series `areaStyle.color: 'var(--cat-3)'`
  silently falls back to default greys on at least the stacked-area /
  treemap renderers. Pattern: don't override `color` per-series — let
  the theme palette do it. If you absolutely must pin a colour, resolve
  the var with `getComputedStyle(...).getPropertyValue(...).trim()` first
  (same pattern `AssetPriceChart` uses for `--gain`/`--loss`/`--accent`).
- **Tree-shaking only works if you import from `echarts/core`.**
  `import * as echarts from 'echarts'` pulls everything (~350 kB gz).
  All chart-type registration must go through `echarts.use([...])`,
  and all imports must come from `echarts/core` / `echarts/charts` /
  `echarts/components` / `echarts/renderers`. Audit `lib/echarts.ts`
  before merging — a stray `import 'echarts'` defeats the budget.
- **CSS-variable reads require browser context.** `getComputedStyle`
  is undefined during SSR; we don't SSR today, but if we ever add it,
  the chart wrappers will need to defer initialisation to
  `useEffect`. Currently they already do via `useChartTheme()`.
- **Treemap + Sunburst can't co-exist on a tile.** ECharts's `treemap`
  series carries its own breadcrumb / drill semantics; the sunburst's
  `emphasis: ancestor` is incompatible. Use one or the other per chart.
- **Marker overlap on AssetDetail.** When multiple buys land on the
  same date+price, lightweight-charts renders them stacked. Group
  identical-price markers on the API/aggregation side if visual noise
  becomes a problem (out of scope for Phase A).
