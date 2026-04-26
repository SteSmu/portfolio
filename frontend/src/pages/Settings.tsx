import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import { useTheme } from '../state/theme'

const PROVIDERS: { key: string; label: string; tier: string }[] = [
  { key: 'TWELVE_DATA_API_KEY', label: 'Twelve Data',  tier: '800/day free · stocks/etf primary' },
  { key: 'FINNHUB_API_KEY',     label: 'Finnhub',      tier: 'free tier · stock news + earnings' },
  { key: 'MARKETAUX_API_KEY',   label: 'Marketaux',    tier: '100/day free · multi-asset news + sentiment' },
  // CoinGecko, Frankfurter, Yahoo do not require keys.
]

export default function Settings() {
  const { activeId } = useActivePortfolio()
  const { theme, resolved, setTheme } = useTheme()

  const { data: portfolio, isLoading: portfolioLoading } = useQuery({
    queryKey: ['portfolio', activeId],
    queryFn: () => api.getPortfolio(activeId!),
    enabled: activeId != null,
  })

  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 30_000,
  })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold" style={{ color: 'var(--text-primary)' }}>
        Settings
      </h1>

      {/* Theme */}
      <section className="card">
        <h2 className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
          Appearance
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          {(['dark', 'light', 'system'] as const).map(opt => (
            <button
              key={opt}
              onClick={() => setTheme(opt)}
              className="rounded px-3 py-1.5 text-sm transition-colors"
              style={{
                backgroundColor: theme === opt ? 'var(--accent)' : 'var(--bg-elev-hi)',
                color: theme === opt ? '#ffffff' : 'var(--text-primary)',
                border: '1px solid var(--border-base)',
              }}
            >
              {opt.charAt(0).toUpperCase() + opt.slice(1)}
            </button>
          ))}
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            currently rendering: {resolved}
          </span>
        </div>
      </section>

      {/* Active Portfolio */}
      <section className="card">
        <h2 className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
          Active Portfolio
        </h2>
        {portfolioLoading ? (
          <div className="skeleton h-32" />
        ) : portfolio ? (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt style={{ color: 'var(--text-secondary)' }}>Name</dt>
            <dd style={{ color: 'var(--text-primary)' }}>{portfolio.name}</dd>
            <dt style={{ color: 'var(--text-secondary)' }}>Base currency</dt>
            <dd style={{ color: 'var(--text-primary)' }}>{portfolio.base_currency}</dd>
            <dt style={{ color: 'var(--text-secondary)' }}>Portfolio ID</dt>
            <dd style={{ color: 'var(--text-primary)' }}>#{portfolio.id}</dd>
            <dt style={{ color: 'var(--text-secondary)' }}>Created</dt>
            <dd style={{ color: 'var(--text-primary)' }}>
              {portfolio.created_at?.slice(0, 10) ?? '—'}
            </dd>
          </dl>
        ) : (
          <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
            no active portfolio — pick one in the header
          </p>
        )}
      </section>

      {/* Backend health */}
      <section className="card">
        <h2 className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
          Backend
        </h2>
        {healthLoading ? (
          <div className="skeleton h-32" />
        ) : health ? (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt style={{ color: 'var(--text-secondary)' }}>Status</dt>
            <dd>
              <span className={health.status === 'ok' ? 'badge-gain' : 'badge-loss'}>
                {health.status}
              </span>
            </dd>
            <dt style={{ color: 'var(--text-secondary)' }}>Version</dt>
            <dd style={{ color: 'var(--text-primary)' }}>{health.version}</dd>
            <dt style={{ color: 'var(--text-secondary)' }}>DB</dt>
            <dd style={{ color: 'var(--text-primary)' }}>
              {health.db.status} · {health.db.latency_ms}ms
            </dd>
            <dt style={{ color: 'var(--text-secondary)' }}>Portfolios</dt>
            <dd style={{ color: 'var(--text-primary)' }}>{health.counts.portfolios ?? '—'}</dd>
            <dt style={{ color: 'var(--text-secondary)' }}>Transactions</dt>
            <dd style={{ color: 'var(--text-primary)' }}>{health.counts.transactions ?? '—'}</dd>
            <dt style={{ color: 'var(--text-secondary)' }}>Candles</dt>
            <dd style={{ color: 'var(--text-primary)' }}>{health.counts.candles ?? '—'}</dd>
            <dt style={{ color: 'var(--text-secondary)' }}>News rows</dt>
            <dd style={{ color: 'var(--text-primary)' }}>{health.counts.news ?? '—'}</dd>
          </dl>
        ) : (
          <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
            backend unreachable
          </p>
        )}
      </section>

      {/* Data providers (env-key presence is server-side; we just list what they do) */}
      <section className="card">
        <h2 className="text-sm font-medium mb-1" style={{ color: 'var(--text-primary)' }}>
          Data providers
        </h2>
        <p className="text-xs mb-3" style={{ color: 'var(--text-tertiary)' }}>
          Per-provider API keys live in the backend{' '}
          <code className="px-1 rounded" style={{ backgroundColor: 'var(--bg-elev-hi)' }}>.env</code>.
          Missing keys cause graceful degradation — no crash, per-call error reported in the
          relevant sync flow.
        </p>
        <ul className="space-y-1 text-sm">
          {PROVIDERS.map(p => (
            <li key={p.key} className="flex items-center justify-between gap-3">
              <span style={{ color: 'var(--text-primary)' }}>{p.label}</span>
              <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                {p.tier}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
