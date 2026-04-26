// Typed API client for the FastAPI backend.
// `/api/*` is proxied by Vite to http://localhost:8430 in dev.

const BASE = '/api'

export type Portfolio = {
  id: number
  user_id: string | null
  name: string
  base_currency: string
  created_at: string
  archived_at: string | null
}

export type Transaction = {
  id: number
  portfolio_id: number
  symbol: string
  asset_type: string
  action: string
  executed_at: string
  quantity: string
  price: string
  trade_currency: string
  fees: string
  fees_currency: string | null
  fx_rate: string | null
  note: string | null
  source: string
  source_doc_id: string | null
  imported_at: string
  deleted_at: string | null
}

export type Holding = {
  symbol: string
  asset_type: string
  currency: string
  quantity: string
  total_cost: string
  avg_cost: string
  first_tx_at: string
  last_tx_at: string
  tx_count: number
  // Optional, populated when the API was called with `with_prices` (default).
  current_price?: string | null
  last_price_at?: string | null
  market_value?: string | null
  unrealized_pnl?: string | null
  unrealized_pnl_pct?: number | null
}

export type AutoPriceSyncResponse = {
  portfolio_id: number
  holdings_count: number
  rows_written: number
  results: Array<{
    symbol: string
    asset_type: string
    ok: boolean
    source?: string
    coingecko_id?: string
    fetched?: number
    written?: number
    error?: string
  }>
}

export type PerformanceSummary = {
  portfolio_id: number
  method: string
  tx_count: number
  open_lot_count: number
  open_cost_basis: string
  realized_pnl: string
  match_count: number
  /** Time-series metrics — null until snapshots exist (run `pt sync snapshots`). */
  timeseries: {
    from: string
    to: string
    snapshot_count: number
    twr_period: string
    twr_annualized: string
    mwr: string | null
    max_drawdown: string
    volatility: string
    sharpe: string
    calmar: string
  } | null
}

export type Snapshot = {
  date: string
  total_value: string
  total_cost_basis: string
  realized_pnl: string
  unrealized_pnl: string
  cash: string
  holdings_count: number
  metadata: {
    by_asset_type?: Record<string, string>
    by_currency?: Record<string, string>
    priced_holdings?: number
    open_holdings?: number
    tx_total?: number
  }
}

export type SnapshotsResponse = {
  portfolio_id: number
  from: string | null
  to: string | null
  snapshots: Snapshot[]
}

export type Candle = {
  time: string
  open: string | null
  high: string | null
  low: string | null
  close: string | null
  volume: string | null
  interval: string
}

export type CandlesResponse = {
  symbol: string
  asset_type: string
  interval: string
  candles: Candle[]
}

export type SparklinesResponse = {
  days: number
  series: Record<string, Array<{ time: string; close: string }>>
}

export type RealizedReport = {
  year: number | null
  method: string
  total: string
  match_count: number
  by_symbol: Record<string, string>
  by_holding_period: { short: string; long: string }
  matches: Array<{
    sell_transaction_id: number
    lot_transaction_id: number
    symbol: string
    asset_type: string
    sold_quantity: string
    cost_per_unit: string
    sell_price: string
    proceeds: string
    cost: string
    realized_pnl: string
    holding_period_days: number
    sell_executed_at: string
    buy_executed_at: string
    currency: string
  }>
}

export type CostBasisReport = {
  method: string
  open_lots: Array<{
    transaction_id: number
    symbol: string
    asset_type: string
    quantity: string
    quantity_original: string
    price: string
    fees: string
    executed_at: string
    currency: string
    cost_basis: string
  }>
  matches: RealizedReport['matches']
  realized_pnl: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = ''
    try {
      const j = await res.json()
      detail = j?.detail ? `: ${j.detail}` : ''
    } catch {
      // body wasn't JSON
    }
    throw new Error(`HTTP ${res.status}${detail}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  health: () => request<{
    status: 'ok' | 'degraded'
    version: string
    now: string
    db: { status: 'ok' | 'unavailable'; latency_ms: number }
    counts: {
      portfolios: number | null
      transactions: number | null
      candles: number | null
      news: number | null
      insights: number | null
    }
  }>('/health'),

  // Portfolios
  listPortfolios: (includeArchived = false) =>
    request<Portfolio[]>(`/portfolios?include_archived=${includeArchived}`),
  createPortfolio: (body: { name: string; base_currency?: string }) =>
    request<Portfolio>('/portfolios', { method: 'POST', body: JSON.stringify(body) }),
  getPortfolio: (id: number) => request<Portfolio>(`/portfolios/${id}`),
  archivePortfolio: (id: number) =>
    request<void>(`/portfolios/${id}`, { method: 'DELETE' }),

  // Transactions
  listTransactions: (portfolioId: number, opts: { symbol?: string; limit?: number } = {}) => {
    const qs = new URLSearchParams()
    if (opts.symbol) qs.set('symbol', opts.symbol)
    qs.set('limit', String(opts.limit ?? 200))
    return request<Transaction[]>(`/portfolios/${portfolioId}/transactions?${qs}`)
  },
  createTransaction: (portfolioId: number, body: Omit<Transaction,
      'id' | 'portfolio_id' | 'imported_at' | 'deleted_at' | 'source_doc_id'>) =>
    request<Transaction>(`/portfolios/${portfolioId}/transactions`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  deleteTransaction: (portfolioId: number, txId: number) =>
    request<void>(`/portfolios/${portfolioId}/transactions/${txId}`, { method: 'DELETE' }),

  // Holdings
  listHoldings: (portfolioId: number, withPrices = true) =>
    request<Holding[]>(
      `/portfolios/${portfolioId}/holdings?with_prices=${withPrices}`,
    ),
  syncPortfolioPrices: (portfolioId: number, days = 30) =>
    request<AutoPriceSyncResponse>(
      `/sync/portfolio/${portfolioId}/auto-prices?days=${days}`,
      { method: 'POST' },
    ),

  // Performance
  performanceSummary: (portfolioId: number, method = 'fifo') =>
    request<PerformanceSummary>(
      `/portfolios/${portfolioId}/performance/summary?method=${method}`,
    ),
  costBasis: (portfolioId: number, method = 'fifo') =>
    request<CostBasisReport>(
      `/portfolios/${portfolioId}/performance/cost-basis?method=${method}`,
    ),
  realized: (portfolioId: number, opts: { method?: string; year?: number } = {}) => {
    const qs = new URLSearchParams()
    qs.set('method', opts.method ?? 'fifo')
    if (opts.year) qs.set('year', String(opts.year))
    return request<RealizedReport>(`/portfolios/${portfolioId}/performance/realized?${qs}`)
  },

  // Audit history for a single transaction (returned by the audit trigger)
  txAudit: (portfolioId: number, txId: number) =>
    request<Array<{
      id: number
      transaction_id: number
      operation: 'INSERT' | 'UPDATE' | 'DELETE'
      old_data: Record<string, unknown> | null
      new_data: Record<string, unknown> | null
      changed_at: string
      changed_by: string | null
    }>>(`/portfolios/${portfolioId}/transactions/${txId}/audit`),

  // Snapshots — equity-curve / drawdown / allocation-over-time data source
  listSnapshots: (portfolioId: number, opts: { from?: string; to?: string } = {}) => {
    const qs = new URLSearchParams()
    if (opts.from) qs.set('start', opts.from)
    if (opts.to)   qs.set('end',   opts.to)
    const tail = qs.toString() ? `?${qs}` : ''
    return request<SnapshotsResponse>(`/portfolios/${portfolioId}/snapshots${tail}`)
  },
  generateSnapshots: (portfolioId: number, backfill = 0) =>
    request<{
      portfolio_id: number
      rows_written: number
      from: string
      to: string
      latest: {
        date: string
        total_value: string
        total_cost_basis: string
        unrealized_pnl: string
        realized_pnl: string
        holdings_count: number
      }
    }>(
      `/portfolios/${portfolioId}/snapshots?backfill=${backfill}`,
      { method: 'POST' },
    ),

  // Per-asset OHLCV history (for the AssetDetail TradingView-style chart)
  listCandles: (
    symbol: string,
    assetType: string,
    opts: { start?: string; end?: string; interval?: string; limit?: number } = {},
  ) => {
    const qs = new URLSearchParams()
    if (opts.start)    qs.set('start',    opts.start)
    if (opts.end)      qs.set('end',      opts.end)
    qs.set('interval', opts.interval ?? '1day')
    qs.set('limit', String(opts.limit ?? 2000))
    return request<CandlesResponse>(
      `/assets/${encodeURIComponent(symbol)}/${assetType}/candles?${qs}`,
    )
  },

  // Bulk per-symbol close-only series for inline holdings-table sparklines
  holdingSparklines: (portfolioId: number, days = 30) =>
    request<SparklinesResponse>(
      `/portfolios/${portfolioId}/holdings/sparklines?days=${days}`,
    ),

  // Benchmarks (curated whitelist + on-demand history sync)
  listBenchmarks: () => request<Benchmark[]>('/benchmarks'),
  syncBenchmark: (symbol: string, days = 365) =>
    request<BenchmarkSyncResponse>(
      `/benchmarks/${encodeURIComponent(symbol)}/sync?days=${days}`,
      { method: 'POST' },
    ),

  // News
  listNews: (symbol: string, assetType: string, limit = 30) =>
    request<NewsResponse>(`/news/${symbol}/${assetType}?limit=${limit}`),
  syncNews: (symbol: string, assetType: string, sources?: string[]) =>
    request<SyncNewsResponse>('/news/sync', {
      method: 'POST',
      body: JSON.stringify({ symbol, asset_type: assetType, sources }),
    }),

  // PDF import
  importPdfDryRun: async (portfolioId: number, file: File): Promise<ImportPdfDryRun> => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(`${BASE}/portfolios/${portfolioId}/import/pdf?dry_run=true`,
                            { method: 'POST', body: fd })
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(`HTTP ${res.status}: ${detail?.detail ?? 'import failed'}`)
    }
    return res.json()
  },
  importPdfCommit: async (portfolioId: number, file: File): Promise<ImportPdfResult> => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(`${BASE}/portfolios/${portfolioId}/import/pdf`,
                            { method: 'POST', body: fd })
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(`HTTP ${res.status}: ${detail?.detail ?? 'import failed'}`)
    }
    return res.json()
  },
}

export type ImportPdfDryRun = {
  dry_run: true
  parser: string
  customer: string
  statement_date: string
  base_currency: string
  file_name: string
  file_hash: string
  holdings_parsed: number
  cash_parsed: number
  transactions_planned: number
  transactions: Array<{
    symbol: string
    asset_type: string
    action: string
    executed_at: string
    quantity: string
    price: string
    trade_currency: string
    fees: string
    note: string | null
    source: string
  }>
  warnings: string[]
}

export type ImportPdfResult = {
  dry_run: false
  parser: string
  file_name: string
  file_hash: string
  customer: string
  statement_date: string
  transactions_added: number
  transactions_skipped: number
  holdings_parsed: number
  cash_parsed: number
  warnings: string[]
  skipped_reason: string | null
}

export type Benchmark = {
  symbol: string
  asset_type: string
  display_name: string
  region: string
}

export type BenchmarkSyncResponse = {
  ok: boolean
  symbol: string
  asset_type: string
  source: string
  twelve_data_error?: string | null
  rows_written: number
  /** Decimal serialized as JSON string; null if no candle is yet stored. */
  last_close: string | null
  last_price_at: string | null
}

export type NewsItem = {
  id: number
  symbol: string
  asset_type: string
  published_at: string
  source: string
  title: string
  summary: string | null
  url: string
  sentiment: string | null
  metadata: Record<string, unknown> | null
  fetched_at: string
}

export type NewsResponse = {
  symbol: string
  asset_type: string
  items: NewsItem[]
  avg_sentiment_14d: string | null
  last_fetched_at: string | null
}

export type SyncNewsResponse = {
  symbol: string
  asset_type: string
  rows_written: number
  sources: Record<string, { ok: boolean; fetched?: number; written?: number; error?: string }>
}
