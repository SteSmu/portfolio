import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api, type Candle, type Snapshot } from '../api/client'
import type { BenchmarkSel } from '../state/benchmark'
import type { BenchmarkOverlay } from '../components/charts/EquityCurve'

/**
 * Resolve a benchmark selection into a chart-ready overlay, normalised so
 * the first plotted point equals the portfolio's first visible
 * `total_value`. Always returns a defined object so call-sites can pass it
 * straight to `<EquityCurve>` — when nothing useful is available, the
 * series is empty and EquityCurve simply omits the line.
 *
 * The math (kept in one place):
 *   factor = first_visible_snapshot.total_value / first_benchmark_close
 *   scaled = candles.map(c => [date, Number(c.close) * factor])
 *
 * Caveats:
 *  - If the user has fewer snapshots than the benchmark history covers,
 *    the benchmark line is trimmed to the snapshot window so the visual
 *    comparison stays apples-to-apples (no "phantom history" beyond the
 *    portfolio's start date). With <2 snapshots there's no equity curve
 *    to overlay onto, so we return an empty series.
 *  - If the user is showing a 30-day window but only synced 5 days of
 *    benchmark history, the line will be short rather than missing —
 *    the parent should call `syncBenchmark()` when this happens, but we
 *    don't trigger it implicitly.
 */
export function useBenchmarkOverlay(
  selected: BenchmarkSel,
  visibleSnaps: Snapshot[],
): BenchmarkOverlay | null {
  // Pull benchmark candles when a selection is active.
  const candles = useQuery({
    queryKey: ['benchmark-candles', selected?.symbol, selected?.asset_type],
    queryFn: () => api.listCandles(selected!.symbol, selected!.asset_type, {
      interval: '1day', limit: 2000,
    }),
    enabled: selected != null,
    staleTime: 60_000,
  })

  // Pull the catalog only to resolve the display name. Cheap, cached.
  const catalog = useQuery({
    queryKey: ['benchmarks'],
    queryFn: () => api.listBenchmarks(),
    staleTime: 5 * 60_000,
  })

  return useMemo<BenchmarkOverlay | null>(() => {
    if (selected == null) return null
    if (visibleSnaps.length < 2) return { name: selected.symbol, series: [] }
    const all = candles.data?.candles ?? []
    if (all.length === 0) return { name: selected.symbol, series: [] }

    const firstSnap = visibleSnaps[0]
    // Trim benchmark candles to the snapshot window (start-aligned overlay).
    const fromDate = firstSnap.date
    const inWindow = all.filter(c => isoDate(c.time) >= fromDate && c.close != null)
    if (inWindow.length === 0) return { name: selected.symbol, series: [] }

    const firstClose = Number(inWindow[0].close)
    if (!Number.isFinite(firstClose) || firstClose <= 0) {
      return { name: selected.symbol, series: [] }
    }
    const factor = Number(firstSnap.total_value) / firstClose

    const series: Array<[string, number]> = inWindow.map(c => [
      isoDate(c.time),
      Number(c.close) * factor,
    ])

    const name = catalog.data?.find(b => b.symbol === selected.symbol)?.display_name
      ?? selected.symbol
    return { name, series }
  }, [selected, visibleSnaps, candles.data, catalog.data])
}

function isoDate(time: string): string {
  // Candles' `time` is an ISO timestamp; snapshots' `date` is "YYYY-MM-DD".
  // Trim to date so the alignment math compares like-for-like.
  return time.slice(0, 10)
}

/** Re-export for convenience so call-sites only need one import. */
export type { Candle }
