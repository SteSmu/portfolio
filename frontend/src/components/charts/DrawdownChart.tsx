import type { EChartsOption } from 'echarts'
import type { Snapshot } from '../../api/client'
import { drawdownFromValues, pickEquitySeries } from '../../lib/snapshotSeries'
import Chart from './Chart'

type Props = {
  snapshots: Snapshot[]
  height?: number
}

/**
 * Drawdown view: cumulative max-peak vs current value, expressed as a
 * percentage. Always non-positive — every tick shows how far below the
 * running peak the portfolio is. The deepest red zone IS the max DD.
 */
export default function DrawdownChart({ snapshots, height = 200 }: Props) {
  if (snapshots.length < 2) {
    return (
      <div
        className="flex items-center justify-center rounded-lg"
        style={{
          height,
          color: 'var(--text-tertiary)',
          border: '1px dashed var(--border-base)',
        }}
      >
        not enough snapshots for drawdown
      </div>
    )
  }

  // Use base-currency values when available so the drawdown reflects
  // FX moves alongside price moves (an EUR investor in USD assets feels
  // both). Falls back to FX-naive total_value otherwise.
  const { values } = pickEquitySeries(snapshots)
  const data = drawdownFromValues(values)

  const minDd = data.length ? Math.min(...data.map(d => d[1])) : 0

  const option: EChartsOption = {
    grid: { left: 8, right: 16, top: 16, bottom: 24, containLabel: true },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) =>
        Number.isFinite(v as number) ? `${(v as number).toFixed(2)}%` : '—',
    },
    xAxis: { type: 'time' },
    yAxis: {
      type: 'value',
      min: Math.floor(minDd * 1.1),
      max: 0,
      axisLabel: { formatter: (v) => `${v}%` },
    },
    series: [{
      name: 'Drawdown',
      type: 'line',
      smooth: false,
      showSymbol: false,
      lineStyle: { color: 'var(--loss)', width: 1.5 },
      areaStyle: { color: 'var(--loss)', opacity: 0.18 },
      data,
    }],
  }

  return <Chart option={option} height={height} />
}
