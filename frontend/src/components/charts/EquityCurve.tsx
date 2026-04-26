import type { EChartsOption } from 'echarts'
import type { Snapshot } from '../../api/client'
import Chart from './Chart'

type Props = {
  snapshots: Snapshot[]
  height?: number
  showCostBasis?: boolean
}

/**
 * Equity curve: total portfolio value over time, with the running cost-basis
 * as a dashed reference line. The gap between them is unrealized P&L.
 *
 * Snapshots are expected oldest-first (the API returns them that way).
 */
export default function EquityCurve({ snapshots, height = 300, showCostBasis = true }: Props) {
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

  const valueSeries = snapshots.map(s => [s.date, Number(s.total_value)])
  const costSeries  = snapshots.map(s => [s.date, Number(s.total_cost_basis)])

  const option: EChartsOption = {
    grid: { left: 8, right: 16, top: 24, bottom: 24, containLabel: true },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => formatMoney(v as number),
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
    ],
  }

  return <Chart option={option} height={height} />
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
