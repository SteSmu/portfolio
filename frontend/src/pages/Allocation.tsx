import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import EmptyPortfolio from '../components/EmptyPortfolio'
import AllocationSunburst from '../components/charts/AllocationSunburst'
import { fmtMoney, fmtPct } from '../lib/format'

type View = 'sunburst' | 'donut'

export default function Allocation() {
  const { activeId } = useActivePortfolio()
  const [view, setView] = useState<View>('sunburst')

  const holdings = useQuery({
    queryKey: ['holdings', activeId],
    queryFn: () => api.listHoldings(activeId!),
    enabled: activeId != null,
  })

  if (activeId == null) return <EmptyPortfolio />

  const live = holdings.data ?? []
  const total = useMemo(
    () => live.reduce((s, h) => s + Number(h.market_value ?? h.total_cost ?? 0), 0),
    [live],
  )
  const groups = useMemo(() => bucketByAssetType(live), [live])

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          Allocation
        </h1>
        <div className="flex items-center gap-2">
          <ViewToggle value={view} onChange={setView} />
        </div>
      </div>

      <section className="card">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
              {view === 'sunburst' ? 'Asset class → Currency → Symbol' : 'Asset class'}
            </h2>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
              FX-naive · sized by market value (cost basis if no live price)
            </p>
          </div>
          <span className="text-sm tabular-nums" style={{ color: 'var(--text-secondary)' }}>
            total: <strong style={{ color: 'var(--text-primary)' }}>{fmtMoney(total)}</strong>
          </span>
        </div>
        {holdings.isLoading ? (
          <div className="skeleton h-96" />
        ) : (
          <AllocationSunburst holdings={live} variant={view} height={420} />
        )}
      </section>

      {/* Per-asset-class breakdown table */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {groups.map(g => (
          <div key={g.assetType} className="card">
            <div className="flex justify-between items-baseline mb-2">
              <h2 className="font-semibold capitalize" style={{ color: 'var(--text-primary)' }}>
                {g.assetType}
              </h2>
              <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                {fmtMoney(g.value)}{' '}
                <span style={{ color: 'var(--text-tertiary)' }}>
                  ({fmtPct(total > 0 ? g.value / total : 0)})
                </span>
              </span>
            </div>
            <ul className="space-y-1 text-sm">
              {g.holdings
                .slice()
                .sort((a, b) => b.value - a.value)
                .map(h => (
                  <li key={`${h.symbol}-${h.assetType}`} className="flex justify-between gap-2">
                    <Link
                      to={`/asset/${encodeURIComponent(h.symbol)}/${h.assetType}`}
                      className="font-medium"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {h.symbol}
                      <span className="ml-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                        {h.currency}
                      </span>
                    </Link>
                    <span className="tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                      {fmtMoney(h.value)}{' '}
                      <span style={{ color: 'var(--text-tertiary)' }}>
                        ({fmtPct(g.value > 0 ? h.value / g.value : 0)})
                      </span>
                    </span>
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </div>

      {live.length === 0 && !holdings.isLoading && (
        <div className="card text-sm" style={{ color: 'var(--text-tertiary)' }}>
          No holdings yet. Import a PDF or add a transaction to see your allocation.
        </div>
      )}
    </div>
  )
}

function ViewToggle({ value, onChange }: { value: View; onChange: (v: View) => void }) {
  const opts: View[] = ['sunburst', 'donut']
  return (
    <div
      className="inline-flex rounded-md p-0.5 text-xs"
      style={{ backgroundColor: 'var(--bg-elev-hi)', border: '1px solid var(--border-base)' }}
      role="radiogroup"
      aria-label="Allocation view"
    >
      {opts.map(o => {
        const active = o === value
        return (
          <button
            key={o} type="button" role="radio" aria-checked={active}
            onClick={() => onChange(o)}
            className="rounded px-2.5 py-1 capitalize transition-colors"
            style={{
              backgroundColor: active ? 'var(--accent)' : 'transparent',
              color: active ? '#ffffff' : 'var(--text-secondary)',
            }}
          >
            {o}
          </button>
        )
      })}
    </div>
  )
}

type Group = {
  assetType: string
  value: number
  holdings: { symbol: string; assetType: string; currency: string; value: number }[]
}

function bucketByAssetType(holdings: { symbol: string; asset_type: string; currency: string; market_value?: string | null; total_cost: string }[]): Group[] {
  const groups = new Map<string, Group>()
  for (const h of holdings) {
    const v = Number(h.market_value ?? h.total_cost ?? 0)
    if (!Number.isFinite(v) || v <= 0) continue
    const g = groups.get(h.asset_type) ?? { assetType: h.asset_type, value: 0, holdings: [] }
    g.value += v
    g.holdings.push({ symbol: h.symbol, assetType: h.asset_type, currency: h.currency, value: v })
    groups.set(h.asset_type, g)
  }
  return [...groups.values()].sort((a, b) => b.value - a.value)
}
