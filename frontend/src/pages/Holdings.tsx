import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import { fmtDate, fmtMoney, fmtPrice, fmtQty, fmtPct, pnlClass } from '../lib/format'
import EmptyPortfolio from '../components/EmptyPortfolio'
import PdfImport from '../components/PdfImport'

export default function Holdings() {
  const { activeId } = useActivePortfolio()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['holdings', activeId],
    queryFn: () => api.listHoldings(activeId!),
    enabled: activeId != null,
  })

  const syncPrices = useMutation({
    mutationFn: () => api.syncPortfolioPrices(activeId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['holdings', activeId] }),
  })

  if (activeId == null) return <EmptyPortfolio />
  if (isLoading) return <p className="text-zinc-500">loading…</p>
  if (error)     return <p className="loss">Error: {(error as Error).message}</p>
  if (!data || data.length === 0) {
    return (
      <div className="space-y-4">
        <PdfImport portfolioId={activeId} />
        <div className="card text-zinc-400 text-sm">
          No open positions yet. Record buys on the{' '}
          <a href="/transactions" className="text-blue-400 hover:underline">Transactions</a> page,
          or import a broker statement above.
        </div>
      </div>
    )
  }

  const totalMarketValue = data.reduce((s, h) =>
    h.market_value ? s + Number(h.market_value) : s, 0)
  const totalUnrealized  = data.reduce((s, h) =>
    h.unrealized_pnl ? s + Number(h.unrealized_pnl) : s, 0)
  const havePrices = data.some(h => h.current_price != null)

  return (
    <div className="space-y-4">
      <PdfImport portfolioId={activeId} />

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Holdings ({data.length})</h1>
        <button
          className="btn-ghost"
          disabled={syncPrices.isPending}
          onClick={() => syncPrices.mutate()}
        >
          {syncPrices.isPending ? 'Refreshing prices…' : 'Refresh prices'}
        </button>
      </div>

      {syncPrices.data && (
        <div className="card text-xs text-zinc-400">
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
        <div className="card grid grid-cols-2 md:grid-cols-3 gap-4">
          <Stat label="Market value" value={fmtMoney(totalMarketValue)} />
          <Stat label="Unrealized P&L" value={fmtMoney(totalUnrealized)}
                pnl={totalUnrealized} />
          <Stat label="Cost basis"
                value={fmtMoney(data.reduce((s, h) => s + Number(h.total_cost || 0), 0))} />
        </div>
      )}

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-zinc-400 text-xs uppercase">
            <tr className="border-b border-zinc-800">
              <th className="text-left py-2">Symbol</th>
              <th className="text-left">Type</th>
              <th className="text-right">Qty</th>
              <th className="text-right">Avg cost</th>
              <th className="text-right">Cur price</th>
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
              <tr key={`${h.symbol}-${h.asset_type}`}
                  className="border-b border-zinc-900 hover:bg-zinc-900/50 cursor-pointer"
                  onClick={() => nav(`/asset/${encodeURIComponent(h.symbol)}/${h.asset_type}`)}>
                <td className="py-2 font-medium text-blue-400 hover:underline">{h.symbol}</td>
                <td className="text-zinc-400">{h.asset_type}</td>
                <td className="text-right tabular-nums">{fmtQty(h.quantity)}</td>
                <td className="text-right tabular-nums text-zinc-400">{fmtPrice(h.avg_cost)}</td>
                <td className="text-right tabular-nums">
                  {h.current_price ? fmtPrice(h.current_price)
                                   : <span className="text-zinc-600">—</span>}
                </td>
                <td className="text-right tabular-nums font-medium">
                  {h.market_value ? fmtMoney(h.market_value)
                                  : <span className="text-zinc-600">—</span>}
                </td>
                <td className={`text-right tabular-nums ${pnlClass(h.unrealized_pnl)}`}>
                  {h.unrealized_pnl != null ? fmtMoney(h.unrealized_pnl)
                                            : <span className="text-zinc-600">—</span>}
                </td>
                <td className={`text-right tabular-nums ${pnlClass(h.unrealized_pnl)}`}>
                  {h.unrealized_pnl_pct != null ? fmtPct(h.unrealized_pnl_pct)
                                                : <span className="text-zinc-600">—</span>}
                </td>
                <td className="text-right tabular-nums text-zinc-400">{fmtMoney(h.total_cost)}</td>
                <td className="text-right text-zinc-400">{h.currency}</td>
                <td className="text-right text-zinc-500">{fmtDate(h.last_tx_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Stat(props: { label: string; value: string; pnl?: number | string }) {
  return (
    <div>
      <div className="text-xs text-zinc-400 uppercase">{props.label}</div>
      <div className={`text-xl font-bold tabular-nums mt-1 ${pnlClass(props.pnl)}`}>
        {props.value}
      </div>
    </div>
  )
}
