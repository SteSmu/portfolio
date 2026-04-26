import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import { fmtDate, fmtMoney, fmtQty } from '../lib/format'
import EmptyPortfolio from '../components/EmptyPortfolio'

export default function Holdings() {
  const { activeId } = useActivePortfolio()
  const { data, isLoading, error } = useQuery({
    queryKey: ['holdings', activeId],
    queryFn: () => api.listHoldings(activeId!),
    enabled: activeId != null,
  })

  if (activeId == null) return <EmptyPortfolio />
  if (isLoading) return <p className="text-zinc-500">loading…</p>
  if (error)     return <p className="loss">Error: {(error as Error).message}</p>
  if (!data || data.length === 0) {
    return (
      <div className="card text-zinc-400 text-sm">
        No open positions yet. Record buys on the{' '}
        <a href="/transactions" className="text-blue-400 hover:underline">Transactions</a> page.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Holdings ({data.length})</h1>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-zinc-400 text-xs uppercase">
            <tr className="border-b border-zinc-800">
              <th className="text-left py-2">Symbol</th>
              <th className="text-left">Type</th>
              <th className="text-right">Qty</th>
              <th className="text-right">Avg cost</th>
              <th className="text-right">Total cost</th>
              <th className="text-right">Cur</th>
              <th className="text-right">First buy</th>
              <th className="text-right">Last tx</th>
              <th className="text-right">Tx</th>
            </tr>
          </thead>
          <tbody>
            {data.map(h => (
              <tr key={`${h.symbol}-${h.asset_type}`}
                  className="border-b border-zinc-900 hover:bg-zinc-900/50">
                <td className="py-2 font-medium">{h.symbol}</td>
                <td className="text-zinc-400">{h.asset_type}</td>
                <td className="text-right tabular-nums">{fmtQty(h.quantity, 8)}</td>
                <td className="text-right tabular-nums">{fmtMoney(h.avg_cost, '', 4)}</td>
                <td className="text-right tabular-nums font-medium">{fmtMoney(h.total_cost)}</td>
                <td className="text-right text-zinc-400">{h.currency}</td>
                <td className="text-right text-zinc-500">{fmtDate(h.first_tx_at)}</td>
                <td className="text-right text-zinc-500">{fmtDate(h.last_tx_at)}</td>
                <td className="text-right text-zinc-500">{h.tx_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
