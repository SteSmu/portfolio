import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Transaction } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import { fmtDate, fmtMoney, fmtPrice, fmtQty } from '../lib/format'
import EmptyPortfolio from '../components/EmptyPortfolio'

const ACTIONS = ['buy', 'sell', 'dividend', 'transfer_in', 'transfer_out',
                 'deposit', 'withdrawal', 'fee', 'split']
const ASSET_TYPES = ['stock', 'etf', 'crypto', 'fx', 'commodity', 'bond']

export default function Transactions() {
  const { activeId } = useActivePortfolio()
  const qc = useQueryClient()
  const [filter, setFilter] = useState({ symbol: '', action: '', year: '' })
  const [auditTx, setAuditTx] = useState<Transaction | null>(null)

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
      qc.invalidateQueries({ queryKey: ['snapshots', activeId] })
    },
  })

  const filtered = useMemo(() => {
    const all = txQuery.data ?? []
    return all.filter(t => {
      if (filter.symbol && !t.symbol.toLowerCase().includes(filter.symbol.toLowerCase())) {
        return false
      }
      if (filter.action && t.action !== filter.action) return false
      if (filter.year && new Date(t.executed_at).getFullYear().toString() !== filter.year) {
        return false
      }
      return true
    })
  }, [txQuery.data, filter])

  if (activeId == null) return <EmptyPortfolio />

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold" style={{ color: 'var(--text-primary)' }}>
        Transactions
      </h1>

      <AddForm portfolioId={activeId} onAdded={() => qc.invalidateQueries()} />

      {/* Filter bar */}
      <div className="card flex items-end flex-wrap gap-3">
        <Field label="Symbol">
          <input
            className="input w-32"
            placeholder="search…"
            value={filter.symbol}
            onChange={e => setFilter(f => ({ ...f, symbol: e.target.value }))}
          />
        </Field>
        <Field label="Action">
          <select
            className="input"
            value={filter.action}
            onChange={e => setFilter(f => ({ ...f, action: e.target.value }))}
          >
            <option value="">all</option>
            {ACTIONS.map(a => <option key={a}>{a}</option>)}
          </select>
        </Field>
        <Field label="Year">
          <input
            className="input w-24"
            placeholder="all"
            value={filter.year}
            onChange={e => setFilter(f => ({ ...f, year: e.target.value.replace(/\D/g, '') }))}
          />
        </Field>
        {(filter.symbol || filter.action || filter.year) && (
          <button
            className="btn-ghost text-xs"
            onClick={() => setFilter({ symbol: '', action: '', year: '' })}
          >
            clear
          </button>
        )}
        <span className="ml-auto text-xs" style={{ color: 'var(--text-tertiary)' }}>
          {filtered.length} of {txQuery.data?.length ?? 0}
        </span>
      </div>

      <div className="card overflow-x-auto">
        <h2 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          Transactions
        </h2>
        {txQuery.isLoading && <div className="skeleton h-32" />}
        {txQuery.data && filtered.length === 0 && (
          <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
            {txQuery.data.length === 0 ? 'No transactions yet.' : 'No matches for the current filters.'}
          </p>
        )}
        {filtered.length > 0 && (
          <table className="w-full text-sm">
            <thead className="text-xs uppercase" style={{ color: 'var(--text-tertiary)' }}>
              <tr style={{ borderBottom: '1px solid var(--border-base)' }}>
                <th className="text-left py-2">When</th>
                <th className="text-left">Action</th>
                <th className="text-left">Symbol</th>
                <th className="text-left">Type</th>
                <th className="text-right">Qty</th>
                <th className="text-right">Price</th>
                <th className="text-right">Cur</th>
                <th className="text-right">Fees</th>
                <th>Source</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(t => (
                <tr key={t.id}
                    className="cursor-pointer transition-colors hover:[background-color:var(--bg-elev-hi)]"
                    style={{ borderBottom: '1px solid var(--border-base)' }}
                    onClick={() => setAuditTx(t)}>
                  <td className="py-2" style={{ color: 'var(--text-secondary)' }}>
                    {fmtDate(t.executed_at)}
                  </td>
                  <td>
                    <span className={
                      t.action === 'buy' || t.action === 'transfer_in' ? 'badge-gain' :
                      t.action === 'sell' || t.action === 'transfer_out' ? 'badge-loss' :
                      'inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium'
                    } style={
                      (t.action === 'buy' || t.action === 'transfer_in' ||
                       t.action === 'sell' || t.action === 'transfer_out')
                        ? undefined
                        : { backgroundColor: 'var(--bg-elev-hi)', color: 'var(--text-secondary)' }
                    }>
                      {t.action}
                    </span>
                  </td>
                  <td className="font-medium" style={{ color: 'var(--text-primary)' }}>
                    {t.symbol}
                  </td>
                  <td style={{ color: 'var(--text-tertiary)' }}>{t.asset_type}</td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>
                    {fmtQty(t.quantity)}
                  </td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>
                    {fmtPrice(t.price)}
                  </td>
                  <td className="text-right" style={{ color: 'var(--text-tertiary)' }}>
                    {t.trade_currency}
                  </td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-tertiary)' }}>
                    {fmtMoney(t.fees)}
                  </td>
                  <td className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    {t.source}
                    {t.source_doc_id && (
                      <span title={t.source_doc_id} className="ml-1 px-1 rounded"
                            style={{ backgroundColor: 'var(--bg-elev-hi)' }}>
                        #{t.source_doc_id.slice(0, 6)}
                      </span>
                    )}
                  </td>
                  <td className="text-right">
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        if (confirm(`Soft-delete tx #${t.id}?`)) del.mutate(t.id)
                      }}
                      className="text-xs hover:underline"
                      style={{ color: 'var(--loss)' }}
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

      {auditTx && (
        <AuditModal
          tx={auditTx}
          portfolioId={activeId}
          onClose={() => setAuditTx(null)}
        />
      )}
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
      <h2 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
        Add transaction
      </h2>
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

function AuditModal({
  tx, portfolioId, onClose,
}: { tx: Transaction; portfolioId: number; onClose: () => void }) {
  const audit = useQuery({
    queryKey: ['tx-audit', portfolioId, tx.id],
    queryFn: () => api.txAudit(portfolioId, tx.id),
  })

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.55)' }}
      onClick={onClose}
    >
      <div
        className="card max-w-2xl w-full max-h-[80vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
        style={{
          backgroundColor: 'var(--bg-elev)',
          borderColor: 'var(--border-strong)',
        }}
      >
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
            Audit trail · tx #{tx.id} · {tx.symbol}
          </h2>
          <button className="btn-ghost text-xs" onClick={onClose}>close</button>
        </div>
        <dl className="text-sm grid grid-cols-2 gap-x-4 gap-y-1 mb-4">
          <dt style={{ color: 'var(--text-secondary)' }}>Action</dt>
          <dd style={{ color: 'var(--text-primary)' }}>{tx.action}</dd>
          <dt style={{ color: 'var(--text-secondary)' }}>Executed</dt>
          <dd style={{ color: 'var(--text-primary)' }}>{fmtDate(tx.executed_at)}</dd>
          <dt style={{ color: 'var(--text-secondary)' }}>Quantity</dt>
          <dd className="tabular-nums" style={{ color: 'var(--text-primary)' }}>{fmtQty(tx.quantity)}</dd>
          <dt style={{ color: 'var(--text-secondary)' }}>Price</dt>
          <dd className="tabular-nums" style={{ color: 'var(--text-primary)' }}>
            {fmtPrice(tx.price)} {tx.trade_currency}
          </dd>
          <dt style={{ color: 'var(--text-secondary)' }}>Source</dt>
          <dd style={{ color: 'var(--text-primary)' }}>{tx.source}</dd>
          {tx.source_doc_id && (
            <>
              <dt style={{ color: 'var(--text-secondary)' }}>Source doc</dt>
              <dd style={{ color: 'var(--text-tertiary)' }}>
                <code className="text-xs">{tx.source_doc_id}</code>
              </dd>
            </>
          )}
        </dl>

        <h3 className="text-xs uppercase mb-2" style={{ color: 'var(--text-tertiary)' }}>
          Audit history (DB-trigger)
        </h3>
        {audit.isLoading && <div className="skeleton h-24" />}
        {audit.data && audit.data.length === 0 && (
          <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>no audit rows</p>
        )}
        {audit.data && audit.data.length > 0 && (
          <ul className="space-y-2 text-xs">
            {audit.data.map(a => (
              <li
                key={a.id}
                className="rounded p-3"
                style={{ backgroundColor: 'var(--bg-elev-hi)' }}
              >
                <div className="flex items-baseline justify-between">
                  <span className="font-medium" style={{ color: 'var(--text-primary)' }}>
                    {a.operation}
                  </span>
                  <span style={{ color: 'var(--text-tertiary)' }}>
                    {a.changed_at} · {a.changed_by ?? 'unknown'}
                  </span>
                </div>
                {a.new_data && (
                  <pre className="mt-2 overflow-x-auto"
                       style={{ color: 'var(--text-secondary)' }}>
{JSON.stringify(a.new_data, null, 2)}
                  </pre>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function Field({ label, children, className = '' }:
                { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <label className="block text-xs mb-1" style={{ color: 'var(--text-tertiary)' }}>{label}</label>
      {children}
    </div>
  )
}
