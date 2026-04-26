import { useNavigate } from 'react-router-dom'
import type { EChartsOption } from 'echarts'
import type { Holding } from '../../api/client'
import Chart from './Chart'

type Props = {
  holdings: Holding[]
  height?: number
}

/**
 * Finviz-style position heatmap. Each tile = one holding, sized by
 * `market_value` (cost basis if no live price) and coloured by daily-change
 * proxy — we don't have intraday Δ, so we use unrealized_pnl_pct as the
 * tone signal instead. Diverging palette: red < 0 < green.
 *
 * Click a tile to drill into AssetDetail.
 */
export default function HoldingsTreemap({ holdings, height = 480 }: Props) {
  const navigate = useNavigate()

  const tiles = holdings
    .map(h => {
      const v = Number(h.market_value ?? h.total_cost ?? 0)
      if (!Number.isFinite(v) || v <= 0) return null
      const pct = h.unrealized_pnl_pct ?? null
      return {
        name: h.symbol,
        value: v,
        pct,
        symbol: h.symbol,
        asset_type: h.asset_type,
        itemStyle: { color: pctToColor(pct) },
      }
    })
    .filter((x): x is NonNullable<typeof x> => x !== null)

  if (tiles.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg"
        style={{
          height,
          color: 'var(--text-tertiary)',
          border: '1px dashed var(--border-base)',
        }}
      >
        no positions to map
      </div>
    )
  }

  const option: EChartsOption = {
    tooltip: {
      formatter: (params: any) => {
        const v = params.data?.value as number
        const p = params.data?.pct as number | null
        const pctStr = p == null ? 'no live price'
                      : `${p >= 0 ? '+' : ''}${(p * 100).toFixed(2)}%`
        return `<div style="font-weight:500">${params.name}</div>` +
               `<div>${formatMoney(v)}</div>` +
               `<div style="opacity:0.8">${pctStr}</div>`
      },
    },
    series: [{
      type: 'treemap',
      data: tiles,
      label: {
        show: true,
        formatter: (p: any) => {
          const v = p.data?.value as number
          const pct = p.data?.pct as number | null
          const pctStr = pct == null ? '' : `\n${pct >= 0 ? '+' : ''}${(pct * 100).toFixed(1)}%`
          return `${p.name}\n${shortMoney(v)}${pctStr}`
        },
        fontSize: 12,
        fontWeight: 500,
      },
      labelLayout: { hideOverlap: true },
      itemStyle: {
        borderColor: 'var(--bg-base)',
        borderWidth: 2,
        gapWidth: 2,
      },
      breadcrumb: { show: false },
      roam: false,
    }],
  }

  return (
    <Chart
      option={option}
      height={height}
      onClick={(p: any) => {
        if (p?.data?.symbol && p?.data?.asset_type) {
          navigate(`/asset/${encodeURIComponent(p.data.symbol)}/${p.data.asset_type}`)
        }
      }}
    />
  )
}

/**
 * Diverging red→neutral→green for unrealized P&L %.
 * Saturation peaks at ±10%, beyond that the colour clamps.
 */
function pctToColor(pct: number | null | undefined): string {
  if (pct == null || !Number.isFinite(pct)) return 'rgba(113,113,122,0.45)' // zinc-500 @ 45%
  const clamped = Math.max(-0.10, Math.min(0.10, pct))
  const t = Math.abs(clamped) / 0.10  // 0..1 saturation
  if (clamped >= 0) {
    // mix zinc-700 (#3f3f46) → emerald-500 (#10b981)
    return mix('#3f3f46', '#10b981', t)
  }
  return mix('#3f3f46', '#e11d48', t)
}

function mix(a: string, b: string, t: number): string {
  const ar = parseInt(a.slice(1, 3), 16)
  const ag = parseInt(a.slice(3, 5), 16)
  const ab = parseInt(a.slice(5, 7), 16)
  const br = parseInt(b.slice(1, 3), 16)
  const bg = parseInt(b.slice(3, 5), 16)
  const bb = parseInt(b.slice(5, 7), 16)
  const r = Math.round(ar + (br - ar) * t)
  const g = Math.round(ag + (bg - ag) * t)
  const bl = Math.round(ab + (bb - ab) * t)
  return `rgb(${r}, ${g}, ${bl})`
}

function shortMoney(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(1)}k`
  return v.toFixed(0)
}

function formatMoney(v: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency', currency: 'EUR', maximumFractionDigits: 0,
  }).format(v)
}
