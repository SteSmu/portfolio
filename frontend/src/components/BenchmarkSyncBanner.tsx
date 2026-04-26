import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

type Props = {
  symbol: string
  assetType: string
}

/**
 * Surfaces a tiny CTA above the equity curve when a benchmark is selected
 * but its candle history is empty. Clicking the button calls
 * `POST /benchmarks/{symbol}/sync?days=365` and invalidates the cached
 * candles so the overlay appears as soon as the rows land.
 *
 * Mounted by the parent (Dashboard / Performance) when
 * `benchmarkOverlay.series.length === 0` despite a non-null selection —
 * the picker itself stays minimal and only owns the manual refresh icon.
 */
export default function BenchmarkSyncBanner({ symbol, assetType }: Props) {
  const qc = useQueryClient()
  const sync = useMutation({
    mutationFn: () => api.syncBenchmark(symbol, 365),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['benchmark-candles', symbol, assetType] })
    },
  })

  return (
    <div
      className="rounded-md px-3 py-2 mb-3 flex items-center justify-between gap-3 text-xs flex-wrap"
      style={{
        backgroundColor: 'var(--bg-elev-hi)',
        border: '1px dashed var(--border-base)',
        color: 'var(--text-secondary)',
      }}
    >
      <span>
        No candles synced for <strong style={{ color: 'var(--text-primary)' }}>{symbol}</strong> yet
        — click <em>Sync benchmark</em> to backfill 365 days of history.
      </span>
      <div className="flex items-center gap-2">
        {sync.error && (
          <span style={{ color: 'var(--loss)' }}>
            {(sync.error as Error).message}
          </span>
        )}
        {sync.data?.ok === false && sync.data?.twelve_data_error && (
          <span style={{ color: 'var(--loss)' }} title={sync.data.twelve_data_error}>
            sync failed
          </span>
        )}
        <button
          type="button"
          className="btn-primary px-3 py-1 text-xs"
          disabled={sync.isPending}
          onClick={() => sync.mutate()}
        >
          {sync.isPending ? 'Syncing…' : 'Sync benchmark'}
        </button>
      </div>
    </div>
  )
}
