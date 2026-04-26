export type Period = '1W' | '1M' | '3M' | 'YTD' | '1Y' | 'ALL'

const OPTIONS: Period[] = ['1W', '1M', '3M', 'YTD', '1Y', 'ALL']

/**
 * Resolve a Period code to an inclusive `start` date string (`YYYY-MM-DD`)
 * relative to today. Returns `null` for `ALL` (no lower bound).
 */
export function periodStart(p: Period, now: Date = new Date()): string | null {
  if (p === 'ALL') return null
  const d = new Date(now)
  switch (p) {
    case '1W':  d.setDate(d.getDate() - 7); break
    case '1M':  d.setMonth(d.getMonth() - 1); break
    case '3M':  d.setMonth(d.getMonth() - 3); break
    case 'YTD': d.setMonth(0); d.setDate(1); break
    case '1Y':  d.setFullYear(d.getFullYear() - 1); break
  }
  return d.toISOString().slice(0, 10)
}

type Props = {
  value: Period
  onChange: (p: Period) => void
  className?: string
}

export default function PeriodSelector({ value, onChange, className = '' }: Props) {
  return (
    <div
      className={`inline-flex rounded-md p-0.5 text-xs ${className}`}
      style={{ backgroundColor: 'var(--bg-elev-hi)', border: '1px solid var(--border-base)' }}
      role="radiogroup"
      aria-label="Time period"
    >
      {OPTIONS.map(opt => {
        const active = opt === value
        return (
          <button
            key={opt}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(opt)}
            className="rounded px-2.5 py-1 font-medium transition-colors"
            style={{
              backgroundColor: active ? 'var(--accent)' : 'transparent',
              color: active ? '#ffffff' : 'var(--text-secondary)',
            }}
          >
            {opt}
          </button>
        )
      })}
    </div>
  )
}
