import type { EChartsOption } from 'echarts'
import type { Snapshot } from '../../api/client'
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

  let peak = 0
  const data: [string, number][] = []
  for (const s of snapshots) {
    const v = Number(s.total_value)
    if (!Number.isFinite(v) || v <= 0) continue
    if (v > peak) peak = v
    const dd = peak > 0 ? (v - peak) / peak * 100 : 0
    data.push([s.date, dd])
  }

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
