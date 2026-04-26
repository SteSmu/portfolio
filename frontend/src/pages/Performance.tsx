import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import { fmtDate, fmtMoney, fmtPrice, fmtQty, pnlClass } from '../lib/format'
import EmptyPortfolio from '../components/EmptyPortfolio'

const METHODS = ['fifo', 'lifo', 'average'] as const
type Method = (typeof METHODS)[number]

export default function Performance() {
  const { activeId } = useActivePortfolio()
  const [method, setMethod] = useState<Method>('fifo')
  const [year, setYear] = useState<string>('')

  const cb = useQuery({
    queryKey: ['cost-basis', activeId, method],
    queryFn: () => api.costBasis(activeId!, method),
    enabled: activeId != null,
  })
  const realized = useQuery({
    queryKey: ['realized', activeId, method, year],
    queryFn: () => api.realized(activeId!,
                                 { method, year: year ? Number(year) : undefined }),
    enabled: activeId != null,
  })

  if (activeId == null) return <EmptyPortfolio />

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <h1 className="text-2xl font-bold">Performance</h1>
        <div className="flex items-center gap-3">
          <div>
            <label className="text-xs text-zinc-400 mr-2">Method</label>
            <select className="input" value={method}
                    onChange={e => setMethod(e.target.value as Method)}>
              {METHODS.map(m => <option key={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-zinc-400 mr-2">Year (realized)</label>
            <input className="input w-24" placeholder="all"
                   value={year}
                   onChange={e => setYear(e.target.value.replace(/\D/g, ''))} />
          </div>
        </div>
      </div>

      {/* Realized summary */}
      {realized.data && (
        <div className="card">
          <h2 className="font-semibold mb-3">Realized P&L</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <Stat label="Total" value={fmtMoney(realized.data.total)}
                  pnl={realized.data.total} />
            <Stat label="Short-term (<1y)" value={fmtMoney(realized.data.by_holding_period.short)}
                  pnl={realized.data.by_holding_period.short} />
            <Stat label="Long-term (≥1y)" value={fmtMoney(realized.data.by_holding_period.long)}
                  pnl={realized.data.by_holding_period.long} />
            <Stat label="Matches" value={String(realized.data.match_count)} />
          </div>
          {Object.keys(realized.data.by_symbol).length > 0 && (
            <div>
              <h3 className="text-xs uppercase text-zinc-400 mb-2">By symbol</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {Object.entries(realized.data.by_symbol)
                  .sort(([, a], [, b]) => Number(b) - Number(a))
                  .map(([sym, pnl]) => (
                    <div key={sym} className="flex justify-between bg-zinc-800/50 px-3 py-1.5 rounded">
                      <span className="font-medium">{sym}</span>
                      <span className={`tabular-nums ${pnlClass(pnl)}`}>{fmtMoney(pnl)}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Open lots */}
      {cb.data && cb.data.open_lots.length > 0 && (
        <div className="card overflow-x-auto">
          <h2 className="font-semibold mb-3">Open tax lots — {method}</h2>
          <table className="w-full text-sm">
            <thead className="text-zinc-400 text-xs uppercase">
              <tr className="border-b border-zinc-800">
                <th className="text-left py-2">TxID</th>
                <th className="text-left">Symbol</th>
                <th className="text-left">Acquired</th>
                <th className="text-right">Qty (rem)</th>
                <th className="text-right">Unit cost</th>
                <th className="text-right">Cost basis</th>
                <th className="text-right">Cur</th>
              </tr>
            </thead>
            <tbody>
              {cb.data.open_lots.map(l => (
                <tr key={l.transaction_id} className="border-b border-zinc-900">
                  <td className="py-2 text-zinc-500">#{l.transaction_id}</td>
                  <td className="font-medium">{l.symbol}</td>
                  <td className="text-zinc-400">{fmtDate(l.executed_at)}</td>
                  <td className="text-right tabular-nums">{fmtQty(l.quantity)}</td>
                  <td className="text-right tabular-nums">{fmtPrice(l.price)}</td>
                  <td className="text-right tabular-nums">{fmtMoney(l.cost_basis)}</td>
                  <td className="text-right text-zinc-400">{l.currency}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Realized matches */}
      {cb.data && cb.data.matches.length > 0 && (
        <div className="card overflow-x-auto">
          <h2 className="font-semibold mb-3">Realized matches</h2>
          <table className="w-full text-sm">
            <thead className="text-zinc-400 text-xs uppercase">
              <tr className="border-b border-zinc-800">
                <th className="text-left py-2">Sell→Buy</th>
                <th className="text-left">Symbol</th>
                <th className="text-right">Sold qty</th>
                <th className="text-right">Cost</th>
                <th className="text-right">Proceeds</th>
                <th className="text-right">P&L</th>
                <th className="text-right">Days</th>
              </tr>
            </thead>
            <tbody>
              {cb.data.matches.map((m, i) => (
                <tr key={i} className="border-b border-zinc-900">
                  <td className="py-2 text-zinc-500 tabular-nums">
                    #{m.sell_transaction_id}→#{m.lot_transaction_id}
                  </td>
                  <td className="font-medium">{m.symbol}</td>
                  <td className="text-right tabular-nums">{fmtQty(m.sold_quantity)}</td>
                  <td className="text-right tabular-nums">{fmtMoney(m.cost)}</td>
                  <td className="text-right tabular-nums">{fmtMoney(m.proceeds)}</td>
                  <td className={`text-right tabular-nums font-medium ${pnlClass(m.realized_pnl)}`}>
                    {fmtMoney(m.realized_pnl)}
                  </td>
                  <td className="text-right text-zinc-500">{m.holding_period_days}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Stat(props: { label: string; value: string; pnl?: string }) {
  return (
    <div>
      <div className="text-xs text-zinc-400 uppercase">{props.label}</div>
      <div className={`text-xl font-bold tabular-nums ${pnlClass(props.pnl)}`}>
        {props.value}
      </div>
    </div>
  )
}
