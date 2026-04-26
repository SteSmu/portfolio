import type { EChartsOption } from 'echarts'
import type { Snapshot } from '../../api/client'
import { pickEquitySeries } from '../../lib/snapshotSeries'
import Chart from './Chart'

export type BenchmarkOverlay = {
  /** Display name shown in the legend, e.g. "S&P 500 (SPY)". */
  name: string
  /** Already-normalized series, oldest first: `[isoDate, value-in-portfolio-units]`. */
  series: Array<[string, number]>
}

type Props = {
  snapshots: Snapshot[]
  height?: number
  showCostBasis?: boolean
  /**
   * Optional benchmark overlay. The wrapper does NOT do the normalization —
   * compute `factor = first_total_value / first_benchmark_close` in the
   * parent and pass the scaled close-prices here. See [charts.md] for the
   * canonical pattern. This keeps EquityCurve agnostic to whatever
   * snapshot the parent considers "first".
   */
  benchmark?: BenchmarkOverlay | null
}

/**
 * Equity curve: total portfolio value over time, with the running cost-basis
 * as a dashed reference line. The gap between them is unrealized P&L.
 *
 * When `benchmark` is supplied, a third line renders in the categorical
 * benchmark colour (`var(--cat-3)`) with the benchmark's display name in
 * the legend. The series is already normalized — see Props doc.
 *
 * Snapshots are expected oldest-first (the API returns them that way).
 */
export default function EquityCurve({
  snapshots,
  height = 300,
  showCostBasis = true,
  benchmark = null,
}: Props) {
  if (snapshots.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg"
        style={{
          height,
          color: 'var(--text-tertiary)',
          border: '1px dashed var(--border-base)',
        }}
      >
        no snapshots yet
      </div>
    )
  }

  // Prefer base-currency series when every visible snapshot has it. The
  // helper also FX-converts cost basis via the per-day implicit rate so
  // both lines are in the same currency — without that, an EUR portfolio
  // holding USD assets would compare a USD value line to a USD cost line
  // labelled as EUR (the chart-area helper formats in the portfolio's
  // base currency below).
  const { mode, currency, values: valueSeries, costs: costSeries } = pickEquitySeries(snapshots)
  const moneyFormat = mode === 'base' && currency ? currency : 'EUR'

  const option: EChartsOption = {
    grid: { left: 8, right: 16, top: 24, bottom: 24, containLabel: true },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => formatMoney(v as number, moneyFormat),
    },
    legend: {
      top: 0,
      right: 8,
      icon: 'roundRect',
      itemWidth: 10,
      itemHeight: 10,
    },
    xAxis: {
      type: 'time',
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { formatter: (v) => formatAxisMoney(v as number) },
    },
    series: [
      {
        name: 'Value',
        type: 'line',
        showSymbol: false,
        smooth: false,
        lineStyle: { width: 2 },
        areaStyle: {
          opacity: 0.12,
        },
        data: valueSeries,
      },
      ...(showCostBasis
        ? [{
            name: 'Cost basis',
            type: 'line' as const,
            showSymbol: false,
            lineStyle: { width: 1.5, type: 'dashed' as const },
            data: costSeries,
          }]
        : []),
      ...(benchmark && benchmark.series.length > 0
        ? [{
            name: benchmark.name,
            type: 'line' as const,
            showSymbol: false,
            lineStyle: { width: 1.5, color: 'var(--cat-3)' },
            itemStyle: { color: 'var(--cat-3)' },
            data: benchmark.series,
          }]
        : []),
    ],
  }

  return <Chart option={option} height={height} />
}

function formatMoney(v: number, currency = 'EUR'): string {
  if (!Number.isFinite(v)) return '—'
  // Some "currencies" coming from snapshot metadata may be unknown to
  // Intl (rare — fallback keeps the number renderable).
  try {
    return new Intl.NumberFormat('de-DE', { style: 'currency', currency }).format(v)
  } catch {
    return new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2 }).format(v) + ' ' + currency
  }
}

function formatAxisMoney(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(0)}k`
  return `${v.toFixed(0)}`
}
