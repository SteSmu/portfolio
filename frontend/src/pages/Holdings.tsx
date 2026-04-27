import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import { fmtDate, fmtMoney, fmtPct, fmtPrice, fmtQty, pnlClass } from '../lib/format'
import type { Holding } from '../api/client'
import EmptyPortfolio from '../components/EmptyPortfolio'
import PdfImport from '../components/PdfImport'
import Sparkline from '../components/charts/Sparkline'
import HoldingsTreemap from '../components/charts/HoldingsTreemap'

type View = 'table' | 'heatmap'

export default function Holdings() {
  const { activeId } = useActivePortfolio()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [view, setView] = useState<View>('table')

  const { data, isLoading, error } = useQuery({
    queryKey: ['holdings', activeId],
    queryFn: () => api.listHoldings(activeId!),
    enabled: activeId != null,
  })
  const portfolio = useQuery({
    queryKey: ['portfolio', activeId],
    queryFn: () => api.getPortfolio(activeId!),
    enabled: activeId != null,
  })
  const sparks = useQuery({
    queryKey: ['sparklines', activeId, 30],
    queryFn: () => api.holdingSparklines(activeId!, 30),
    enabled: activeId != null,
  })

  const syncPrices = useMutation({
    mutationFn: () => api.syncPortfolioPrices(activeId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['holdings', activeId] }),
  })

  if (activeId == null) return <EmptyPortfolio />
  if (isLoading) return <div className="skeleton h-72" />
  if (error)     return <p className="loss">Error: {(error as Error).message}</p>
  if (!data || data.length === 0) {
    return (
      <div className="space-y-4">
        <PdfImport portfolioId={activeId} />
        <div className="card text-sm" style={{ color: 'var(--text-tertiary)' }}>
          No open positions yet. Record buys on the{' '}
          <a href="/transactions" style={{ color: 'var(--accent)' }} className="hover:underline">
            Transactions
          </a>{' '}
          page, or import a broker statement above.
        </div>
      </div>
    )
  }

  // Sum FX-converted base-currency fields so cross-currency holdings (USD,
  // CHF, EUR, …) reconcile against the Dashboard hero (which reads
  // `total_value_base` from the latest snapshot). Summing native-currency
  // `market_value` straight across mixed-currency rows treats USD as EUR
  // and produces a misleading top-line — the original symptom of this fix.
  const baseCcy = portfolio.data?.base_currency ?? 'EUR'
  const sumBase = (key: keyof Pick<Holding, 'market_value_base' | 'unrealized_pnl_base' | 'total_cost_base'>) =>
    data.reduce((s, h) => h[key] != null ? s + Number(h[key]) : s, 0)
  const totalMarketValue = sumBase('market_value_base')
  const totalUnrealized  = sumBase('unrealized_pnl_base')
  const totalCost        = sumBase('total_cost_base')
  const fxGapRows = data.filter(h => h.current_price != null && h.market_value_base == null).length
  const havePrices = data.some(h => h.current_price != null)
  const series = sparks.data?.series ?? {}

  return (
    <div className="space-y-4">
      <PdfImport portfolioId={activeId} />

      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          Holdings ({data.length})
        </h1>
        <div className="flex items-center gap-2 flex-wrap">
          <ViewToggle value={view} onChange={setView} />
          <button
            className="btn-ghost"
            disabled={syncPrices.isPending}
            onClick={() => syncPrices.mutate()}
          >
            {syncPrices.isPending ? 'Refreshing prices…' : 'Refresh prices'}
          </button>
        </div>
      </div>

      {syncPrices.data && (
        <div className="card text-xs" style={{ color: 'var(--text-tertiary)' }}>
          <div className="mb-1">
            Wrote {syncPrices.data.rows_written} candle(s) across{' '}
            {syncPrices.data.holdings_count} holding(s).
          </div>
          {syncPrices.data.results.filter(r => !r.ok).map(r => (
            <div key={`${r.symbol}-${r.asset_type}`} className="loss">
              · {r.symbol} ({r.asset_type}): {r.error}
            </div>
          ))}
        </div>
      )}

      {havePrices && (
        <div className="card">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <Stat label={`Market value (${baseCcy})`} value={fmtMoney(totalMarketValue)} />
            <Stat label={`Unrealized P&L (${baseCcy})`} value={fmtMoney(totalUnrealized)}
                  pnl={totalUnrealized} />
            <Stat label={`Cost basis (${baseCcy})`} value={fmtMoney(totalCost)} />
          </div>
          {fxGapRows > 0 && (
            <p className="text-xs mt-2" style={{ color: 'var(--loss)' }}>
              ⚠ {fxGapRows} row(s) missing FX rate — totals exclude them.
              Run <code>pt sync fx --base {baseCcy} --days 400</code>.
            </p>
          )}
        </div>
      )}

      {view === 'heatmap' ? (
        <section className="card">
          <p className="text-xs mb-3" style={{ color: 'var(--text-tertiary)' }}>
            Tile size = market value · colour = unrealized P&L %. Click a tile to drill in.
          </p>
          <HoldingsTreemap holdings={data} height={520} />
        </section>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase" style={{ color: 'var(--text-tertiary)' }}>
              <tr style={{ borderBottom: '1px solid var(--border-base)' }}>
                <th className="text-left py-2">Symbol</th>
                <th className="text-left">Type</th>
                <th className="text-right">Qty</th>
                <th className="text-right">Avg cost</th>
                <th className="text-right">Cur price</th>
                <th className="text-left pl-3">30d</th>
                <th className="text-right">Market value</th>
                <th className="text-right">Unrealized</th>
                <th className="text-right">P&L %</th>
                <th className="text-right">Cost basis</th>
                <th className="text-right">Cur</th>
                <th className="text-right">Last tx</th>
              </tr>
            </thead>
            <tbody>
              {data.map(h => (
                <tr
                  key={`${h.symbol}-${h.asset_type}`}
                  className="cursor-pointer transition-colors hover:[background-color:var(--bg-elev-hi)]"
                  style={{ borderBottom: '1px solid var(--border-base)' }}
                  onClick={() =>
                    nav(`/asset/${encodeURIComponent(h.symbol)}/${h.asset_type}`)}
                >
                  <td className="py-2 font-medium hover:underline"
                      style={{ color: 'var(--accent)' }}>
                    {h.symbol}
                  </td>
                  <td style={{ color: 'var(--text-tertiary)' }}>{h.asset_type}</td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>
                    {fmtQty(h.quantity)}
                  </td>
                  <td className="text-right tabular-nums"
                      style={{ color: 'var(--text-secondary)' }}>
                    {fmtPrice(h.avg_cost)}
                  </td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>
                    {h.current_price
                      ? fmtPrice(h.current_price)
                      : <span style={{ color: 'var(--text-tertiary)' }}>—</span>}
                  </td>
                  <td className="pl-3" style={{ width: 100 }}>
                    <Sparkline points={series[h.symbol] ?? []} width={88} height={22} />
                  </td>
                  <td className="text-right tabular-nums font-medium"
                      style={{ color: 'var(--text-primary)' }}>
                    {h.market_value
                      ? fmtMoney(h.market_value)
                      : <span style={{ color: 'var(--text-tertiary)' }}>—</span>}
                  </td>
                  <td className={`text-right tabular-nums ${pnlClass(h.unrealized_pnl)}`}>
                    {h.unrealized_pnl != null
                      ? fmtMoney(h.unrealized_pnl)
                      : <span style={{ color: 'var(--text-tertiary)' }}>—</span>}
                  </td>
                  <td className={`text-right tabular-nums ${pnlClass(h.unrealized_pnl)}`}>
                    {h.unrealized_pnl_pct != null
                      ? fmtPct(h.unrealized_pnl_pct)
                      : <span style={{ color: 'var(--text-tertiary)' }}>—</span>}
                  </td>
                  <td className="text-right tabular-nums"
                      style={{ color: 'var(--text-tertiary)' }}>
                    {fmtMoney(h.total_cost)}
                  </td>
                  <td className="text-right" style={{ color: 'var(--text-tertiary)' }}>
                    {h.currency}
                  </td>
                  <td className="text-right" style={{ color: 'var(--text-tertiary)' }}>
                    {fmtDate(h.last_tx_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ViewToggle({ value, onChange }: { value: View; onChange: (v: View) => void }) {
  const opts: View[] = ['table', 'heatmap']
  return (
    <div
      className="inline-flex rounded-md p-0.5 text-xs"
      style={{ backgroundColor: 'var(--bg-elev-hi)', border: '1px solid var(--border-base)' }}
      role="radiogroup"
      aria-label="Holdings view"
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

function Stat(props: { label: string; value: string; pnl?: number | string }) {
  return (
    <div>
      <div className="text-xs uppercase" style={{ color: 'var(--text-tertiary)' }}>
        {props.label}
      </div>
      <div className={`text-xl font-bold tabular-nums mt-1 ${pnlClass(props.pnl)}`}
           style={{ color: pnlClass(props.pnl) === 'flat' ? 'var(--text-primary)' : undefined }}>
        {props.value}
      </div>
    </div>
  )
}
