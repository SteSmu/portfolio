import { useEffect, useRef } from 'react'
import {
  createChart,
  createSeriesMarkers,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LineData,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import { useTheme } from '../../state/theme'
import type { Candle, NewsItem, Transaction } from '../../api/client'

type Props = {
  candles: Candle[]
  transactions: Transaction[]
  /** Avg unit cost — drawn as a dashed horizontal price line. */
  avgCost?: number | null
  height?: number
  /** Optional news items — when `showNews` is true, one dot per item is
   *  pinned at its `published_at` time and tinted by sentiment. Click on a
   *  dot opens the source URL in a new tab. */
  news?: NewsItem[]
  showNews?: boolean
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
 *  - Optional news markers (dots, sentiment-tinted) when `showNews` is on.
 *  - Horizontal `priceLine` for the avg cost basis.
 *  - Re-mounts on theme change so colours stay readable.
 */
export default function AssetPriceChart({
  candles, transactions, avgCost, height = 380, news, showNews = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const priceLinesRef = useRef<ReturnType<ISeriesApi<'Line'>['createPriceLine']>[]>([])
  // Map from utc-second timestamp of a news marker → news item, used by the
  // chart-click handler to figure out which dot the user hit.
  const newsByTimeRef = useRef<Map<number, NewsItem>>(new Map())
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

    // Click handler — find the news item closest to the clicked time. We
    // don't have per-marker click events in lightweight-charts v5, so we
    // approximate by snapping to the nearest day with a news pin.
    const onClick = (param: { time?: Time }) => {
      if (param.time == null) return
      const map = newsByTimeRef.current
      if (map.size === 0) return
      const t = Number(param.time)
      // Find within ±1 day (86400s) of click. Stops random clicks from
      // opening unrelated news.
      let best: { ts: number; item: NewsItem } | null = null
      for (const [ts, item] of map.entries()) {
        const d = Math.abs(ts - t)
        if (d > 86_400) continue
        if (best == null || d < Math.abs(best.ts - t)) best = { ts, item }
      }
      if (best) window.open(best.item.url, '_blank', 'noopener,noreferrer')
    }
    chart.subscribeClick(onClick)

    return () => {
      chart.unsubscribeClick(onClick)
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
      markersRef.current = null
      priceLinesRef.current = []
      newsByTimeRef.current = new Map()
    }
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
    const txMarkers: SeriesMarker<Time>[] = transactions
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

    // 3. News markers (optional). Sentiment >0 gain, <0 loss, neutral grey.
    //    Group by UTC-day so multiple items on the same day don't stack —
    //    we keep the strongest-sentiment item for the dot, but the click
    //    handler can still map any nearby click onto something useful.
    const newsByTime = new Map<number, NewsItem>()
    const newsMarkers: SeriesMarker<Time>[] = []
    if (showNews && news && news.length > 0) {
      for (const item of news) {
        const t = isoToTime(item.published_at)
        const existing = newsByTime.get(t)
        if (existing) {
          const a = item.sentiment != null ? Math.abs(Number(item.sentiment)) : 0
          const b = existing.sentiment != null ? Math.abs(Number(existing.sentiment)) : 0
          if (a > b) newsByTime.set(t, item)
        } else {
          newsByTime.set(t, item)
        }
      }
      const gain = readVar('--gain') || '#34d399'
      const loss = readVar('--loss') || '#fb7185'
      const flat = readVar('--text-tertiary') || '#71717a'
      for (const [t, item] of newsByTime.entries()) {
        const s = item.sentiment != null ? Number(item.sentiment) : 0
        const color = !Number.isFinite(s) || s === 0 ? flat : s > 0 ? gain : loss
        newsMarkers.push({
          time: t as UTCTimestamp,
          position: 'inBar' as const,
          shape: 'circle' as const,
          color,
          size: 0.8,
          text: item.title.length > 60 ? `${item.title.slice(0, 57)}…` : item.title,
        })
      }
    }
    newsByTimeRef.current = newsByTime

    const allMarkers: SeriesMarker<Time>[] = [...txMarkers, ...newsMarkers]
      .sort((a, b) => (a.time as number) - (b.time as number))

    if (markersRef.current) {
      markersRef.current.setMarkers(allMarkers)
    } else {
      markersRef.current = createSeriesMarkers(series, allMarkers)
    }

    // 4. Cost-basis horizontal line. Strip any prior line first so updates
    //    don't stack new lines on top of stale ones.
    for (const pl of priceLinesRef.current) series.removePriceLine(pl)
    priceLinesRef.current = []
    if (avgCost != null && avgCost > 0) {
      const pl = series.createPriceLine({
        price: avgCost,
        color: readVar('--text-tertiary') || '#71717a',
        lineWidth: 1,
        lineStyle: 2, // dashed
        axisLabelVisible: true,
        title: 'cost basis',
      })
      priceLinesRef.current.push(pl)
    }

    if (points.length > 0) chart.timeScale().fitContent()
  }, [candles, transactions, avgCost, news, showNews])

  return <div ref={containerRef} style={{ width: '100%', height }} />
}
