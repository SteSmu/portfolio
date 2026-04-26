import type { EChartsOption } from 'echarts'
import Chart from './Chart'

type Point = { time: string; close: string }

type Props = {
  points: Point[]
  width?: number | string
  height?: number
  /** Force a color override (defaults to gain/loss based on first vs last point). */
  color?: string
}

/**
 * Tiny inline trend line — used in the holdings table and top-holdings card.
 * Takes a list of `{time, close}` and renders a no-axis line with one symbol
 * at the end so the eye lands on "where we are now".
 */
export default function Sparkline({ points, width = '100%', height = 28, color }: Props) {
  if (points.length < 2) {
    return (
      <span style={{ display: 'inline-block', width, height, color: 'var(--text-tertiary)' }}>—</span>
    )
  }
  const first = Number(points[0].close)
  const last  = Number(points[points.length - 1].close)
  const trendUp = last >= first
  const stroke = color ?? (trendUp ? 'var(--gain)' : 'var(--loss)')

  const option: EChartsOption = {
    grid: { left: 0, right: 0, top: 2, bottom: 2 },
    xAxis: { type: 'time', show: false },
    yAxis: { type: 'value', show: false, scale: true },
    tooltip: { show: false },
    animation: false,
    series: [{
      type: 'line',
      data: points.map(p => [p.time, Number(p.close)]),
      showSymbol: false,
      symbolSize: 0,
      smooth: false,
      lineStyle: { color: stroke, width: 1.5 },
      areaStyle: { color: stroke, opacity: 0.12 },
      markPoint: {
        symbol: 'circle',
        symbolSize: 4,
        itemStyle: { color: stroke },
        data: [{ name: 'last', coord: [points[points.length - 1].time, last] }],
        label: { show: false },
      },
    }],
  }
  return <Chart option={option} height={height} style={{ width }} />
}
