import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import { fmtDate, fmtMoney, fmtPrice, fmtQty } from '../lib/format'
import EmptyPortfolio from '../components/EmptyPortfolio'

const ACTIONS = ['buy', 'sell', 'dividend', 'transfer_in', 'transfer_out',
                 'deposit', 'withdrawal', 'fee', 'split']
const ASSET_TYPES = ['stock', 'etf', 'crypto', 'fx', 'commodity', 'bond']

export default function Transactions() {
  const { activeId } = useActivePortfolio()
  const qc = useQueryClient()

  const txQuery = useQuery({
    queryKey: ['transactions', activeId],
    queryFn: () => api.listTransactions(activeId!),
    enabled: activeId != null,
  })

  const del = useMutation({
    mutationFn: (txId: number) => api.deleteTransaction(activeId!, txId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['transactions', activeId] })
      qc.invalidateQueries({ queryKey: ['holdings', activeId] })
      qc.invalidateQueries({ queryKey: ['perf-summary', activeId] })
    },
  })

  if (activeId == null) return <EmptyPortfolio />

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Transactions</h1>

      <AddForm portfolioId={activeId} onAdded={() => qc.invalidateQueries()} />

      <div className="card overflow-x-auto">
        <h2 className="font-semibold mb-3">All transactions</h2>
        {txQuery.isLoading && <p className="text-zinc-500 text-sm">loading…</p>}
        {txQuery.data && txQuery.data.length === 0 && (
          <p className="text-zinc-500 text-sm">No transactions yet.</p>
        )}
        {txQuery.data && txQuery.data.length > 0 && (
          <table className="w-full text-sm">
            <thead className="text-zinc-400 text-xs uppercase">
              <tr className="border-b border-zinc-800">
                <th className="text-left py-2">When</th>
                <th className="text-left">Action</th>
                <th className="text-left">Symbol</th>
                <th className="text-left">Type</th>
                <th className="text-right">Qty</th>
                <th className="text-right">Price</th>
                <th className="text-right">Cur</th>
                <th className="text-right">Fees</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {txQuery.data.map(t => (
                <tr key={t.id} className="border-b border-zinc-900 hover:bg-zinc-900/50">
                  <td className="py-2 text-zinc-400">{fmtDate(t.executed_at)}</td>
                  <td>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      t.action === 'buy' ? 'bg-emerald-900/40 text-emerald-300' :
                      t.action === 'sell' ? 'bg-rose-900/40 text-rose-300' :
                      'bg-zinc-800 text-zinc-300'
                    }`}>
                      {t.action}
                    </span>
                  </td>
                  <td className="font-medium">{t.symbol}</td>
                  <td className="text-zinc-400">{t.asset_type}</td>
                  <td className="text-right tabular-nums">{fmtQty(t.quantity)}</td>
                  <td className="text-right tabular-nums">{fmtPrice(t.price)}</td>
                  <td className="text-right text-zinc-400">{t.trade_currency}</td>
                  <td className="text-right tabular-nums text-zinc-400">{fmtMoney(t.fees)}</td>
                  <td className="text-right">
                    <button
                      onClick={() => {
                        if (confirm(`Soft-delete tx #${t.id}?`)) del.mutate(t.id)
                      }}
                      className="text-rose-400 hover:text-rose-300 text-xs"
                    >
                      delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function AddForm({ portfolioId, onAdded }: { portfolioId: number; onAdded: () => void }) {
  const [symbol, setSymbol] = useState('')
  const [assetType, setAssetType] = useState('stock')
  const [action, setAction] = useState('buy')
  const [executedAt, setExecutedAt] = useState(() =>
    new Date().toISOString().slice(0, 10))
  const [quantity, setQuantity] = useState('')
  const [price, setPrice] = useState('')
  const [currency, setCurrency] = useState('USD')
  const [fees, setFees] = useState('0')
  const [note, setNote] = useState('')

  const add = useMutation({
    mutationFn: () =>
      api.createTransaction(portfolioId, {
        symbol, asset_type: assetType, action,
        executed_at: new Date(executedAt + 'T00:00:00Z').toISOString(),
        quantity, price, trade_currency: currency,
        fees, fees_currency: currency,
        fx_rate: null, note: note || null, source: 'manual',
      }),
    onSuccess: () => {
      setSymbol(''); setQuantity(''); setPrice(''); setFees('0'); setNote('')
      onAdded()
    },
  })

  return (
    <div className="card">
      <h2 className="font-semibold mb-3">Add transaction</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Field label="Symbol">
          <input className="input w-full" value={symbol}
                 onChange={e => setSymbol(e.target.value.toUpperCase())} placeholder="AAPL"/>
        </Field>
        <Field label="Asset type">
          <select className="input w-full" value={assetType}
                  onChange={e => setAssetType(e.target.value)}>
            {ASSET_TYPES.map(t => <option key={t}>{t}</option>)}
          </select>
        </Field>
        <Field label="Action">
          <select className="input w-full" value={action}
                  onChange={e => setAction(e.target.value)}>
            {ACTIONS.map(a => <option key={a}>{a}</option>)}
          </select>
        </Field>
        <Field label="Executed at">
          <input type="date" className="input w-full" value={executedAt}
                 onChange={e => setExecutedAt(e.target.value)} />
        </Field>
        <Field label="Quantity">
          <input className="input w-full" value={quantity}
                 onChange={e => setQuantity(e.target.value)} placeholder="10"/>
        </Field>
        <Field label="Price">
          <input className="input w-full" value={price}
                 onChange={e => setPrice(e.target.value)} placeholder="180.50"/>
        </Field>
        <Field label="Currency">
          <input className="input w-full" value={currency}
                 onChange={e => setCurrency(e.target.value.toUpperCase())} />
        </Field>
        <Field label="Fees">
          <input className="input w-full" value={fees}
                 onChange={e => setFees(e.target.value)} />
        </Field>
        <Field label="Note (optional)" className="md:col-span-3">
          <input className="input w-full" value={note}
                 onChange={e => setNote(e.target.value)} />
        </Field>
        <div className="flex items-end">
          <button className="btn-primary w-full"
                  disabled={!symbol || !quantity || !price || add.isPending}
                  onClick={() => add.mutate()}>
            {add.isPending ? 'Adding…' : 'Add'}
          </button>
        </div>
      </div>
      {add.error && (
        <p className="loss text-xs mt-2">{(add.error as Error).message}</p>
      )}
    </div>
  )
}

function Field({ label, children, className = '' }:
                { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <label className="block text-xs text-zinc-400 mb-1">{label}</label>
      {children}
    </div>
  )
}
