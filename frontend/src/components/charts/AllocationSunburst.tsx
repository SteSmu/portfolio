import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import type { Holding } from '../../api/client'
import Chart from './Chart'

type Props = {
  holdings: Holding[]
  /** 'donut' = single-ring, 'sunburst' = drillable multi-ring. */
  variant?: 'sunburst' | 'donut'
  height?: number
}

type Tree = {
  name: string
  value?: number
  children?: Tree[]
  itemStyle?: { color?: string }
}

/**
 * Drill levels (sunburst):
 *   asset_type → currency → symbol
 *
 * Sizes are market_value in source currency (FX-naive). Donut variant
 * collapses to asset_type only.
 */
export default function AllocationSunburst({
  holdings, variant = 'sunburst', height = 380,
}: Props) {
  const tree = useMemo(() => buildTree(holdings, variant), [holdings, variant])
  const total = useMemo(() =>
    holdings.reduce((s, h) => s + Number(h.market_value ?? h.total_cost ?? 0), 0),
    [holdings])

  if (tree.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg"
        style={{
          height,
          color: 'var(--text-tertiary)',
          border: '1px dashed var(--border-base)',
        }}
      >
        no holdings to allocate
      </div>
    )
  }

  const option: EChartsOption = variant === 'sunburst'
    ? sunburstOption(tree, total)
    : donutOption(tree, total)

  return <Chart option={option} height={height} />
}

function buildTree(holdings: Holding[], variant: 'sunburst' | 'donut'): Tree[] {
  // Bucket: asset_type -> currency -> symbol → market_value (or total_cost)
  const byType: Record<string, Record<string, Record<string, number>>> = {}
  for (const h of holdings) {
    const v = Number(h.market_value ?? h.total_cost ?? 0)
    if (!Number.isFinite(v) || v <= 0) continue
    const at = h.asset_type
    const cy = h.currency
    byType[at]      ??= {}
    byType[at][cy]  ??= {}
    byType[at][cy][h.symbol] = (byType[at][cy][h.symbol] ?? 0) + v
  }
  const types = Object.entries(byType)
  if (variant === 'donut') {
    return types.map(([at, currencies]) => ({
      name: at,
      value: Object.values(currencies)
        .reduce((s, ccyMap) => s + Object.values(ccyMap).reduce((x, y) => x + y, 0), 0),
    }))
  }
  return types.map(([at, currencies]) => ({
    name: at,
    children: Object.entries(currencies).map(([cy, syms]) => ({
      name: cy,
      children: Object.entries(syms).map(([sym, v]) => ({
        name: sym,
        value: v,
      })),
    })),
  }))
}

function sunburstOption(tree: Tree[], total: number): EChartsOption {
  return {
    tooltip: {
      formatter: (params: any) => {
        const v = Number(params.value ?? 0)
        const pct = total > 0 ? (v / total * 100) : 0
        return `<div style="font-weight:500">${params.name}</div>` +
               `<div style="opacity:0.8">${formatMoney(v)} · ${pct.toFixed(1)}%</div>`
      },
    },
    series: [{
      type: 'sunburst',
      data: tree,
      radius: [0, '90%'],
      sort: undefined,
      emphasis: { focus: 'ancestor' },
      levels: [
        {},
        { r0: '15%',   r: '45%',   itemStyle: { borderWidth: 1, borderColor: 'transparent' },
          label: { rotate: 'tangential', fontSize: 11 } },
        { r0: '45%',   r: '70%',   itemStyle: { borderWidth: 1, borderColor: 'transparent' },
          label: { fontSize: 10, align: 'right' } },
        { r0: '70%',   r: '90%',   itemStyle: { borderWidth: 0 },
          label: { fontSize: 10, position: 'outside', silent: false } },
      ],
    }],
  }
}

function donutOption(tree: Tree[], total: number): EChartsOption {
  return {
    tooltip: {
      formatter: (params: any) => {
        const v = Number(params.value ?? 0)
        const pct = total > 0 ? (v / total * 100) : 0
        return `<div style="font-weight:500">${params.name}</div>` +
               `<div style="opacity:0.8">${formatMoney(v)} · ${pct.toFixed(1)}%</div>`
      },
    },
    legend: { orient: 'vertical', right: 8, top: 'middle' },
    series: [{
      type: 'pie',
      radius: ['45%', '78%'],
      center: ['38%', '50%'],
      itemStyle: { borderWidth: 2, borderColor: 'var(--bg-elev)' },
      label: { formatter: '{b}\n{d}%', fontSize: 11 },
      labelLine: { length: 8, length2: 8 },
      data: tree.map(t => ({ name: t.name, value: t.value ?? 0 })),
    }],
  }
}

function formatMoney(v: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency', currency: 'EUR', maximumFractionDigits: 0,
  }).format(v)
}
