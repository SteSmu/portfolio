import { NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import PortfolioPicker from './PortfolioPicker'
import ThemeToggle from './ThemeToggle'

const NAV = [
  { to: '/',             label: 'Dashboard' },
  { to: '/holdings',     label: 'Holdings' },
  { to: '/allocation',   label: 'Allocation' },
  { to: '/performance',  label: 'Performance' },
  { to: '/transactions', label: 'Transactions' },
  { to: '/settings',     label: 'Settings' },
]

export default function Layout() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 30_000,
  })

  const dbOk = health?.db?.status === 'ok'

  return (
    <div className="min-h-screen flex flex-col">
      <header
        className="sticky top-0 z-10 backdrop-blur"
        style={{
          borderBottom: '1px solid var(--border-base)',
          backgroundColor: 'color-mix(in srgb, var(--bg-elev) 80%, transparent)',
        }}
      >
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3 px-4 sm:px-6 py-3">
          <div className="flex items-center gap-4 sm:gap-6 flex-wrap">
            <div className="font-bold text-lg" style={{ color: 'var(--text-primary)' }}>
              📊 Portfolio
            </div>
            <nav className="flex items-center gap-1 sm:gap-2 flex-wrap">
              {NAV.map(item => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    `text-sm px-2 py-1 rounded transition-colors ${
                      isActive ? 'nav-active' : 'nav-inactive'
                    }`
                  }
                  style={({ isActive }) => ({
                    backgroundColor: isActive ? 'var(--bg-elev-hi)' : 'transparent',
                    color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                  })}
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <PortfolioPicker />
            <ThemeToggle />
            <span
              className="text-xs px-2 py-1 rounded"
              style={{
                backgroundColor: dbOk ? 'var(--gain-soft)' : 'var(--loss-soft)',
                color: dbOk ? 'var(--gain)' : 'var(--loss)',
              }}
            >
              {health ? `db: ${health.db.status} · ${health.db.latency_ms}ms` : '...'}
            </span>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 py-6">
        <Outlet />
      </main>

      <footer
        className="text-xs px-6 py-3"
        style={{
          borderTop: '1px solid var(--border-base)',
          color: 'var(--text-tertiary)',
        }}
      >
        Portfolio Tracker — read-only · multi-asset · korrekte Zahlen
      </footer>
    </div>
  )
}
