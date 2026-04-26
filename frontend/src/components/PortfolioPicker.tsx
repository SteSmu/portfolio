import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'

export default function PortfolioPicker() {
  const { activeId, setActive } = useActivePortfolio()
  const { data: portfolios } = useQuery({
    queryKey: ['portfolios'],
    queryFn: () => api.listPortfolios(),
  })

  useEffect(() => {
    if (activeId == null && portfolios && portfolios.length > 0) {
      setActive(portfolios[0].id)
    }
  }, [activeId, portfolios, setActive])

  if (!portfolios || portfolios.length === 0) {
    return <span className="text-xs text-zinc-500">no portfolio</span>
  }

  return (
    <select
      value={activeId ?? portfolios[0].id}
      onChange={e => setActive(Number(e.target.value))}
      className="input text-xs"
    >
      {portfolios.map(p => (
        <option key={p.id} value={p.id}>
          {p.name} ({p.base_currency})
        </option>
      ))}
    </select>
  )
}
