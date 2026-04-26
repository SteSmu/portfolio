import { useEffect, useRef } from 'react'
import {
  createChart,
  createSeriesMarkers,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import { useTheme } from '../../state/theme'
import type { Candle, Transaction } from '../../api/client'

type Props = {
  candles: Candle[]
  transactions: Transaction[]
  /** Avg unit cost — drawn as a dashed horizontal price line. */
  avgCost?: number | null
  height?: number
}

function isoToTime(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp
}

function readVar(name: string): string {
  if (typeof document === 'undefined') return ''
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

/**
 * Per-asset price chart using lightweight-charts v5.
 *  - Single line series fed from `public.candles` close values.
 *  - Per-tx markers (buy ▲ green, sell ▼ red, transfer dot blue) via
 *    createSeriesMarkers — v5's official primitive for plotting events
 *    on a series without re-mounting it.
 *  - Horizontal `priceLine` for the avg cost basis.
 *  - Re-mounts on theme change so colours stay readable.
 */
export default function AssetPriceChart({
  candles, transactions, avgCost, height = 380,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const { resolved } = useTheme()

  // Mount/dispose on theme change so the chart picks up the new palette.
  useEffect(() => {
    if (!containerRef.current) return
    const textColor = readVar('--text-secondary') || '#a1a1aa'
    const gridColor = readVar('--chart-grid') || '#27272a'

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: 'transparent' },
        textColor,
        fontFamily: 'inherit',
      },
      grid: {
        vertLines: { color: gridColor, style: 1 },
        horzLines: { color: gridColor, style: 1 },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: gridColor,
      },
      rightPriceScale: { borderColor: gridColor },
      crosshair: {
        horzLine: { color: textColor, labelBackgroundColor: 'var(--bg-elev-hi)' },
        vertLine: { color: textColor, labelBackgroundColor: 'var(--bg-elev-hi)' },
      },
    })
    const series = chart.addSeries(LineSeries, {
      color: readVar('--accent') || '#3b82f6',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    })
    chartRef.current = chart
    seriesRef.current = series

    return () => { chart.remove(); chartRef.current = null; seriesRef.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolved])

  // Push new data whenever inputs change.
  useEffect(() => {
    const series = seriesRef.current
    const chart = chartRef.current
    if (!series || !chart) return

    // 1. Line data (closes) — sorted asc, dedupe per UTC day.
    const points: LineData<UTCTimestamp>[] = []
    const seen = new Set<number>()
    for (const c of candles) {
      if (c.close == null) continue
      const t = isoToTime(c.time)
      if (seen.has(t)) continue
      seen.add(t)
      points.push({ time: t, value: Number(c.close) })
    }
    points.sort((a, b) => (a.time as number) - (b.time as number))
    series.setData(points)

    // 2. Tx markers.
    const markers: SeriesMarker<Time>[] = transactions
      .filter(t => t.action === 'buy' || t.action === 'sell'
                || t.action === 'transfer_in' || t.action === 'transfer_out')
      .map(t => ({
        time: isoToTime(t.executed_at),
        position:
          t.action === 'buy' || t.action === 'transfer_in' ? 'belowBar' as const : 'aboveBar' as const,
        color:
          t.action === 'buy' || t.action === 'transfer_in'
            ? readVar('--gain') || '#34d399'
            : readVar('--loss') || '#fb7185',
        shape:
          t.action === 'buy' || t.action === 'transfer_in' ? 'arrowUp' as const : 'arrowDown' as const,
        text: `${t.action === 'transfer_in' ? 'in' : t.action === 'transfer_out' ? 'out' : t.action} ${Number(t.quantity)} @ ${Number(t.price)}`,
      }))
      .sort((a, b) => (a.time as number) - (b.time as number))
    createSeriesMarkers(series, markers)

    // 3. Cost-basis horizontal line.
    if (avgCost != null && avgCost > 0) {
      // First-clear stale lines: lightweight-charts has no list-priceLines API,
      // so we recreate by removing all (none) and adding fresh. Component
      // re-mounts on theme change anyway, which clears them.
      series.createPriceLine({
        price: avgCost,
        color: readVar('--text-tertiary') || '#71717a',
        lineWidth: 1,
        lineStyle: 2, // dashed
        axisLabelVisible: true,
        title: 'cost basis',
      })
    }

    if (points.length > 0) chart.timeScale().fitContent()
  }, [candles, transactions, avgCost])

  return <div ref={containerRef} style={{ width: '100%', height }} />
}
