import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'

export default function EmptyPortfolio() {
  const { setActive } = useActivePortfolio()
  const qc = useQueryClient()
  const portfolios = useQuery({ queryKey: ['portfolios'], queryFn: () => api.listPortfolios() })

  const [name, setName] = useState('Real-Depot')
  const [currency, setCurrency] = useState('EUR')

  const create = useMutation({
    mutationFn: () => api.createPortfolio({ name, base_currency: currency }),
    onSuccess: (p) => {
      setActive(p.id)
      qc.invalidateQueries({ queryKey: ['portfolios'] })
    },
  })

  if (portfolios.data && portfolios.data.length > 0) {
    return (
      <div className="card max-w-md mx-auto mt-12 text-center">
        <h2 className="text-lg font-semibold mb-2">Pick a portfolio</h2>
        <p className="text-zinc-400 text-sm mb-3">
          Use the dropdown in the header to choose one of your portfolios.
        </p>
      </div>
    )
  }

  return (
    <div className="card max-w-md mx-auto mt-12">
      <h2 className="text-lg font-semibold mb-3">Create your first portfolio</h2>
      <p className="text-sm text-zinc-400 mb-4">
        Then add transactions manually or via PDF/CSV import (coming soon).
      </p>
      <div className="space-y-3">
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Name</label>
          <input className="input w-full" value={name}
                 onChange={e => setName(e.target.value)} />
        </div>
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Base currency</label>
          <input className="input w-full" value={currency}
                 onChange={e => setCurrency(e.target.value.toUpperCase())} />
        </div>
        <button className="btn-primary w-full"
                disabled={create.isPending || !name.trim()}
                onClick={() => create.mutate()}>
          {create.isPending ? 'Creating…' : 'Create portfolio'}
        </button>
        {create.error && (
          <p className="text-rose-400 text-xs">{(create.error as Error).message}</p>
        )}
      </div>
    </div>
  )
}
