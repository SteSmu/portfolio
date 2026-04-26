import { NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import PortfolioPicker from './PortfolioPicker'

const NAV = [
  { to: '/',             label: 'Dashboard' },
  { to: '/holdings',     label: 'Holdings' },
  { to: '/transactions', label: 'Transactions' },
  { to: '/performance',  label: 'Performance' },
]

export default function Layout() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 30_000,
  })

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-zinc-800 bg-zinc-900/60 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto flex items-center justify-between px-6 py-3">
          <div className="flex items-center gap-6">
            <div className="font-bold text-lg">📊 Portfolio</div>
            <nav className="flex items-center gap-4">
              {NAV.map(item => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    `text-sm px-2 py-1 rounded transition-colors ${
                      isActive
                        ? 'bg-zinc-800 text-white'
                        : 'text-zinc-400 hover:text-zinc-100'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <PortfolioPicker />
            <span className={`text-xs px-2 py-1 rounded ${
              health?.db === 'ok'
                ? 'bg-emerald-900/40 text-emerald-300'
                : 'bg-rose-900/40 text-rose-300'
            }`}>
              {health ? `db: ${health.db}` : '...'}
            </span>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-6">
        <Outlet />
      </main>

      <footer className="border-t border-zinc-800 text-xs text-zinc-500 px-6 py-3">
        Portfolio Tracker — read-only · multi-asset · korrekte Zahlen
      </footer>
    </div>
  )
}
