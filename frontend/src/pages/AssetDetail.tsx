import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import EmptyPortfolio from '../components/EmptyPortfolio'
import AssetPriceChart from '../components/charts/AssetPriceChart'
import PeriodSelector, { type Period, periodStart } from '../components/PeriodSelector'
import { fmtDate, fmtMoney, fmtPct, fmtPrice, fmtQty, pnlClass, pnlSign } from '../lib/format'

export default function AssetDetail() {
  const { activeId } = useActivePortfolio()
  const { symbol = '', assetType = '' } = useParams()
  const qc = useQueryClient()

  const [period, setPeriod] = useState<Period>('1Y')
  const start = useMemo(() => periodStart(period), [period])

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

  // Twelve Data writes '1day', Binance/CoinGecko '1d'. Prefer the source-
  // matching interval first; fall back to the other so symbols whose data
  // came in via the "wrong" provider still render.
  const candles = useQuery({
    queryKey: ['candles', symbol, assetType, start, period],
    queryFn: async () => {
      const primaryInterval = assetType === 'crypto' ? '1d' : '1day'
      const fallbackInterval = primaryInterval === '1day' ? '1d' : '1day'
      const primary = await api.listCandles(symbol, assetType, {
        start: start ?? undefined,
        interval: primaryInterval,
        limit: 5000,
      })
      if (primary.candles.length > 0) return primary
      return api.listCandles(symbol, assetType, {
        start: start ?? undefined,
        interval: fallbackInterval,
        limit: 5000,
      })
    },
    enabled: !!symbol && !!assetType,
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

  const avgCost = holding.data ? Number(holding.data.avg_cost) : null
  const currentPrice = holding.data?.current_price ? Number(holding.data.current_price) : null
  const unrealizedPct = holding.data?.unrealized_pnl_pct ?? null

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-3xl font-semibold" style={{ color: 'var(--text-primary)' }}>
            {symbol}
          </h1>
          <span
            className="text-sm uppercase tracking-wide"
            style={{ color: 'var(--text-tertiary)' }}
          >
            {assetType}
          </span>
          {currentPrice != null && (
            <span className="text-lg tabular-nums" style={{ color: 'var(--text-secondary)' }}>
              {fmtPrice(currentPrice)} {holding.data?.currency}
              {unrealizedPct != null && (
                <span
                  className="ml-2 text-sm"
                  style={{ color: unrealizedPct >= 0 ? 'var(--gain)' : 'var(--loss)' }}
                >
                  {pnlSign(unrealizedPct)}{fmtPct(unrealizedPct)}
                </span>
              )}
            </span>
          )}
        </div>
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      {/* Price chart */}
      <section className="card">
        {candles.isLoading ? (
          <div className="skeleton h-96" />
        ) : (candles.data?.candles.length ?? 0) === 0 ? (
          <div
            className="flex items-center justify-center text-sm"
            style={{ height: 380, color: 'var(--text-tertiary)' }}
          >
            No price history cached for {symbol}.{' '}
            {assetType === 'crypto' ? (
              <>Run <code>pt sync crypto --coin &lt;coingecko-id&gt;</code> to populate.</>
            ) : (
              <>Run <code>pt sync stock {symbol}</code> to populate.</>
            )}
          </div>
        ) : (
          <AssetPriceChart
            candles={candles.data!.candles}
            transactions={transactions.data ?? []}
            avgCost={avgCost}
            height={380}
          />
        )}
      </section>

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
        <div className="card text-sm" style={{ color: 'var(--text-tertiary)' }}>
          No open position for this asset in the current portfolio.
        </div>
      )}

      {/* Transactions list */}
      {transactions.data && transactions.data.length > 0 && (
        <div className="card overflow-x-auto">
          <h2 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
            Transactions ({transactions.data.length})
          </h2>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase" style={{ color: 'var(--text-tertiary)' }}>
              <tr style={{ borderBottom: '1px solid var(--border-base)' }}>
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
                <tr key={t.id} style={{ borderBottom: '1px solid var(--border-base)' }}>
                  <td className="py-2" style={{ color: 'var(--text-secondary)' }}>
                    {fmtDate(t.executed_at)}
                  </td>
                  <td>
                    <span className={
                      t.action === 'buy' || t.action === 'transfer_in' ? 'badge-gain' :
                      t.action === 'sell' || t.action === 'transfer_out' ? 'badge-loss' :
                      'badge-gain'
                    } style={
                      t.action === 'buy' || t.action === 'transfer_in' ||
                      t.action === 'sell' || t.action === 'transfer_out'
                        ? undefined
                        : { backgroundColor: 'var(--bg-elev-hi)', color: 'var(--text-secondary)' }
                    }>
                      {t.action}
                    </span>
                  </td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>
                    {fmtQty(t.quantity)}
                  </td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>
                    {fmtPrice(t.price)}
                  </td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-tertiary)' }}>
                    {fmtMoney(t.fees)}
                  </td>
                  <td className="text-right" style={{ color: 'var(--text-tertiary)' }}>
                    {t.trade_currency}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* News */}
      <div className="card">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="font-semibold" style={{ color: 'var(--text-primary)' }}>News</h2>
            {news.data?.last_fetched_at && (
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
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
        {syncNews.data && <SyncSummary data={syncNews.data} />}

        {news.isLoading && (
          <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>loading…</p>
        )}
        {news.data && news.data.items.length === 0 && (
          <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
            No news cached for this asset yet. Click <em>Refresh news</em> above.
          </p>
        )}
        {news.data && news.data.items.length > 0 && (
          <ul className="divide-y" style={{ borderColor: 'var(--border-base)' }}>
            {news.data.items.map(item => (
              <li key={item.id} className="py-3"
                  style={{ borderTop: '1px solid var(--border-base)' }}>
                <a href={item.url} target="_blank" rel="noopener noreferrer"
                   className="font-medium hover:underline"
                   style={{ color: 'var(--text-primary)' }}>
                  {item.title}
                </a>
                <div className="flex items-center gap-3 text-xs mt-1"
                     style={{ color: 'var(--text-tertiary)' }}>
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
                  <p className="text-sm mt-1.5 line-clamp-3"
                     style={{ color: 'var(--text-secondary)' }}>
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
      <div className="text-xs uppercase" style={{ color: 'var(--text-tertiary)' }}>{label}</div>
      <div className="text-xl font-bold tabular-nums mt-1"
           style={{ color: 'var(--text-primary)' }}>
        {value}
      </div>
    </div>
  )
}

function SyncSummary({ data }: { data: import('../api/client').SyncNewsResponse }) {
  return (
    <div className="text-xs mb-3 space-y-0.5" style={{ color: 'var(--text-tertiary)' }}>
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
