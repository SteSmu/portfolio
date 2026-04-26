import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import { fmtMoney, fmtPrice, fmtQty, pnlClass } from '../lib/format'
import EmptyPortfolio from '../components/EmptyPortfolio'

export default function Dashboard() {
  const { activeId } = useActivePortfolio()

  const summary = useQuery({
    queryKey: ['perf-summary', activeId],
    queryFn: () => api.performanceSummary(activeId!),
    enabled: activeId != null,
  })
  const holdings = useQuery({
    queryKey: ['holdings', activeId],
    queryFn: () => api.listHoldings(activeId!),
    enabled: activeId != null,
  })

  if (activeId == null) return <EmptyPortfolio />

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {summary.data && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Stat label="Open positions" value={String(summary.data.open_lot_count)} />
          <Stat label="Cost basis" value={fmtMoney(summary.data.open_cost_basis)} />
          <Stat
            label="Realized P&L"
            value={fmtMoney(summary.data.realized_pnl)}
            pnl={summary.data.realized_pnl}
          />
          <Stat label="Transactions" value={String(summary.data.tx_count)} />
        </div>
      )}

      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">Top holdings (cost basis)</h2>
          <a href="/holdings" className="text-xs text-zinc-400 hover:text-zinc-100">
            view all →
          </a>
        </div>
        {holdings.isLoading && <p className="text-zinc-500 text-sm">loading…</p>}
        {holdings.data && holdings.data.length === 0 && (
          <p className="text-zinc-500 text-sm">
            No holdings yet. Add transactions on the{' '}
            <a href="/transactions" className="text-blue-400 hover:underline">
              Transactions
            </a>{' '}
            page.
          </p>
        )}
        {holdings.data && holdings.data.length > 0 && (
          <table className="w-full text-sm">
            <thead className="text-zinc-400">
              <tr className="border-b border-zinc-800">
                <th className="text-left py-1.5">Symbol</th>
                <th className="text-left">Type</th>
                <th className="text-right">Qty</th>
                <th className="text-right">Avg cost</th>
                <th className="text-right">Cost basis</th>
                <th className="text-right">Cur</th>
              </tr>
            </thead>
            <tbody>
              {holdings.data
                .slice()
                .sort((a, b) => Number(b.total_cost) - Number(a.total_cost))
                .slice(0, 5)
                .map(h => (
                  <tr key={`${h.symbol}-${h.asset_type}`} className="border-b border-zinc-900">
                    <td className="py-1.5 font-medium">
                      <Link to={`/asset/${encodeURIComponent(h.symbol)}/${h.asset_type}`}
                            className="text-blue-400 hover:underline">
                        {h.symbol}
                      </Link>
                    </td>
                    <td className="text-zinc-400">{h.asset_type}</td>
                    <td className="text-right tabular-nums">{fmtQty(h.quantity)}</td>
                    <td className="text-right tabular-nums">{fmtPrice(h.avg_cost)}</td>
                    <td className="text-right">{fmtMoney(h.total_cost)}</td>
                    <td className="text-right text-zinc-400">{h.currency}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function Stat(props: { label: string; value: string; pnl?: string }) {
  return (
    <div className="card">
      <div className="text-xs text-zinc-400 uppercase tracking-wide">{props.label}</div>
      <div className={`text-2xl font-bold mt-1 ${pnlClass(props.pnl)}`}>{props.value}</div>
    </div>
  )
}
