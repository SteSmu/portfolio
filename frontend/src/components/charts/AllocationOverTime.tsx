import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import type { Snapshot } from '../../api/client'
import Chart from './Chart'

type Props = {
  snapshots: Snapshot[]
  height?: number
}

/**
 * Stacked-area allocation history. One series per asset_type, value taken
 * from each snapshot's `metadata.by_asset_type` breakdown. Areas stack so
 * the silhouette equals total portfolio value over time.
 *
 * If a given snapshot doesn't carry a breakdown for an asset type that
 * appears elsewhere in the window, that value falls to 0 — the area
 * shrinks rather than the line vanishing entirely.
 *
 * The categorical palette is read from `--cat-1..8` so the colours stay
 * consistent with the sunburst/donut variants on the same page.
 */
export default function AllocationOverTime({ snapshots, height = 360 }: Props) {
  const { dates, types, series } = useMemo(() => buildSeries(snapshots), [snapshots])

  if (snapshots.length < 2) {
    return (
      <div
        className="flex items-center justify-center rounded-lg text-sm"
        style={{
          height,
          color: 'var(--text-tertiary)',
          border: '1px dashed var(--border-base)',
        }}
      >
        Need at least two snapshots — generate more on the Dashboard.
      </div>
    )
  }
  if (types.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg text-sm"
        style={{
          height,
          color: 'var(--text-tertiary)',
          border: '1px dashed var(--border-base)',
        }}
      >
        Snapshots are missing per-asset-type breakdowns. Re-run{' '}
        <code className="ml-1">pt sync snapshots</code> to backfill.
      </div>
    )
  }

  const option: EChartsOption = {
    grid: { left: 8, right: 16, top: 36, bottom: 24, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      valueFormatter: (v) => formatMoney(v as number),
    },
    legend: {
      top: 0,
      right: 8,
      icon: 'roundRect',
      itemWidth: 10,
      itemHeight: 10,
      type: 'scroll',
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { formatter: (v) => formatAxisMoney(v as number) },
    },
    series: types.map(t => ({
      name: t,
      type: 'line',
      stack: 'allocation',
      showSymbol: false,
      smooth: false,
      lineStyle: { width: 1 },
      // Colour comes from the theme's categorical palette (--cat-1..8) —
      // setting an explicit `color: var(--...)` here breaks because
      // ECharts can't resolve CSS vars on `areaStyle.color`. Relying on
      // the palette also keeps the colours in sync with the donut/sunburst
      // variants on the same page.
      areaStyle: { opacity: 0.85 },
      emphasis: { focus: 'series' },
      data: series[t],
    })),
  }

  return <Chart option={option} height={height} notMerge />
}

function buildSeries(snapshots: Snapshot[]): {
  dates: string[]
  types: string[]
  series: Record<string, number[]>
} {
  // Union of asset types across the whole window — sorted by total
  // contribution (largest at the bottom of the stack).
  const totals = new Map<string, number>()
  for (const s of snapshots) {
    const breakdown = s.metadata?.by_asset_type ?? {}
    for (const [t, v] of Object.entries(breakdown)) {
      const n = Number(v)
      if (!Number.isFinite(n)) continue
      totals.set(t, (totals.get(t) ?? 0) + n)
    }
  }
  const types = [...totals.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([t]) => t)

  const dates = snapshots.map(s => s.date)
  const series: Record<string, number[]> = {}
  for (const t of types) series[t] = new Array(snapshots.length).fill(0)
  snapshots.forEach((s, i) => {
    const breakdown = s.metadata?.by_asset_type ?? {}
    for (const t of types) {
      const v = Number(breakdown[t] ?? 0)
      series[t][i] = Number.isFinite(v) ? v : 0
    }
  })
  return { dates, types, series }
}

function formatMoney(v: number): string {
  if (!Number.isFinite(v)) return '—'
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(v)
}

function formatAxisMoney(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(0)}k`
  return `${v.toFixed(0)}`
}
