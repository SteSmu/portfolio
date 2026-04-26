import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import EmptyPortfolio from '../components/EmptyPortfolio'
import { fmtDate, fmtMoney, fmtPrice, fmtQty, pnlClass } from '../lib/format'

export default function AssetDetail() {
  const { activeId } = useActivePortfolio()
  const { symbol = '', assetType = '' } = useParams()
  const qc = useQueryClient()

  const holding = useQuery({
    queryKey: ['holding', activeId, symbol, assetType],
    queryFn: () => api.listHoldings(activeId!).then(rows =>
      rows.find(h => h.symbol === symbol && h.asset_type === assetType) ?? null,
    ),
    enabled: activeId != null && !!symbol,
  })

  const transactions = useQuery({
    queryKey: ['transactions', activeId, symbol],
    queryFn: () => api.listTransactions(activeId!, { symbol }),
    enabled: activeId != null && !!symbol,
  })

  const news = useQuery({
    queryKey: ['news', symbol, assetType],
    queryFn: () => api.listNews(symbol, assetType, 50),
    enabled: !!symbol && !!assetType,
  })

  const syncNews = useMutation({
    mutationFn: () => api.syncNews(symbol, assetType),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['news', symbol, assetType] }),
  })

  if (activeId == null) return <EmptyPortfolio />

  return (
    <div className="space-y-6">
      <div className="flex items-baseline gap-3">
        <h1 className="text-3xl font-bold">{symbol}</h1>
        <span className="text-sm uppercase tracking-wide text-zinc-400">{assetType}</span>
      </div>

      {/* Position summary */}
      {holding.data && (
        <div className="card grid grid-cols-2 md:grid-cols-4 gap-4">
          <Stat label="Quantity" value={fmtQty(holding.data.quantity)} />
          <Stat
            label="Avg cost"
            value={`${fmtPrice(holding.data.avg_cost)} ${holding.data.currency}`}
          />
          <Stat
            label="Total cost"
            value={`${fmtMoney(holding.data.total_cost)} ${holding.data.currency}`}
          />
          <Stat label="Transactions" value={String(holding.data.tx_count)} />
        </div>
      )}
      {holding.data === null && (
        <div className="card text-zinc-400 text-sm">
          No open position for this asset in the current portfolio.
        </div>
      )}

      {/* Transactions list */}
      {transactions.data && transactions.data.length > 0 && (
        <div className="card overflow-x-auto">
          <h2 className="font-semibold mb-3">Transactions ({transactions.data.length})</h2>
          <table className="w-full text-sm">
            <thead className="text-zinc-400 text-xs uppercase">
              <tr className="border-b border-zinc-800">
                <th className="text-left py-2">When</th>
                <th className="text-left">Action</th>
                <th className="text-right">Qty</th>
                <th className="text-right">Price</th>
                <th className="text-right">Fees</th>
                <th className="text-right">Cur</th>
              </tr>
            </thead>
            <tbody>
              {transactions.data.map(t => (
                <tr key={t.id} className="border-b border-zinc-900">
                  <td className="py-2 text-zinc-400">{fmtDate(t.executed_at)}</td>
                  <td>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      t.action === 'buy' ? 'bg-emerald-900/40 text-emerald-300' :
                      t.action === 'sell' ? 'bg-rose-900/40 text-rose-300' :
                      'bg-zinc-800 text-zinc-300'
                    }`}>{t.action}</span>
                  </td>
                  <td className="text-right tabular-nums">{fmtQty(t.quantity)}</td>
                  <td className="text-right tabular-nums">{fmtPrice(t.price)}</td>
                  <td className="text-right tabular-nums text-zinc-400">{fmtMoney(t.fees)}</td>
                  <td className="text-right text-zinc-400">{t.trade_currency}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* News */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="font-semibold">News</h2>
            {news.data?.last_fetched_at && (
              <p className="text-xs text-zinc-500 mt-0.5">
                last refresh {fmtDate(news.data.last_fetched_at)}
                {news.data.avg_sentiment_14d != null && (
                  <> · 14d sentiment{' '}
                    <span className={pnlClass(news.data.avg_sentiment_14d)}>
                      {Number(news.data.avg_sentiment_14d).toFixed(2)}
                    </span>
                  </>
                )}
              </p>
            )}
          </div>
          <button
            className="btn-ghost"
            disabled={syncNews.isPending}
            onClick={() => syncNews.mutate()}
          >
            {syncNews.isPending ? 'Refreshing…' : 'Refresh news'}
          </button>
        </div>

        {syncNews.error && (
          <p className="loss text-xs mb-3">{(syncNews.error as Error).message}</p>
        )}
        {syncNews.data && (
          <SyncSummary data={syncNews.data} />
        )}

        {news.isLoading && <p className="text-zinc-500 text-sm">loading…</p>}
        {news.data && news.data.items.length === 0 && (
          <p className="text-zinc-500 text-sm">
            No news cached for this asset yet. Click <em>Refresh news</em> above.
          </p>
        )}
        {news.data && news.data.items.length > 0 && (
          <ul className="divide-y divide-zinc-800">
            {news.data.items.map(item => (
              <li key={item.id} className="py-3">
                <a href={item.url} target="_blank" rel="noopener noreferrer"
                   className="text-zinc-100 hover:text-blue-400 font-medium">
                  {item.title}
                </a>
                <div className="flex items-center gap-3 text-xs text-zinc-500 mt-1">
                  <span>{fmtDate(item.published_at)}</span>
                  <span>·</span>
                  <span className="uppercase tracking-wide">{item.source}</span>
                  {item.sentiment != null && (
                    <>
                      <span>·</span>
                      <span className={pnlClass(item.sentiment)}>
                        sent {Number(item.sentiment).toFixed(2)}
                      </span>
                    </>
                  )}
                </div>
                {item.summary && (
                  <p className="text-sm text-zinc-300 mt-1.5 line-clamp-3">
                    {item.summary}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-zinc-400 uppercase">{label}</div>
      <div className="text-xl font-bold tabular-nums mt-1">{value}</div>
    </div>
  )
}

function SyncSummary({ data }: { data: import('../api/client').SyncNewsResponse }) {
  return (
    <div className="text-xs text-zinc-400 mb-3 space-y-0.5">
      <div>Wrote {data.rows_written} item(s).</div>
      {Object.entries(data.sources).map(([name, r]) => (
        <div key={name}>
          {r.ok
            ? `· ${name}: fetched ${r.fetched ?? 0}, wrote ${r.written ?? 0}`
            : <span className="loss">· {name}: {r.error}</span>}
        </div>
      ))}
    </div>
  )
}
