import { useTheme, type Theme } from '../state/theme'

const OPTIONS: { value: Theme; label: string; icon: string }[] = [
  { value: 'dark',   label: 'Dark',   icon: '🌙' },
  { value: 'light',  label: 'Light',  icon: '☀️' },
  { value: 'system', label: 'System', icon: '🖥️' },
]

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  return (
    <div
      className="inline-flex rounded-md p-0.5 text-xs"
      style={{ backgroundColor: 'var(--bg-elev-hi)' }}
      role="radiogroup"
      aria-label="Theme"
    >
      {OPTIONS.map(opt => {
        const active = theme === opt.value
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setTheme(opt.value)}
            title={opt.label}
            className="rounded px-2 py-0.5 transition-colors"
            style={{
              backgroundColor: active ? 'var(--accent)' : 'transparent',
              color: active ? '#ffffff' : 'var(--text-secondary)',
            }}
          >
            <span aria-hidden>{opt.icon}</span>
          </button>
        )
      })}
    </div>
  )
}
