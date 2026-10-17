import { useEffect, useState } from 'react'
import { getWard } from '../api'
import type { WardCard as Card } from '../types'
import WardCard from './WardCard'

export default function WardPage({ wardId }: { wardId: number | null }) {
  const [card, setCard] = useState<Card | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (wardId === null) return
    const pending = new AbortController()
    getWard(wardId, pending.signal).then(setCard).catch((failure) => {
      if (!pending.signal.aborted) setError(failure instanceof Error ? failure.message : String(failure))
    })
    return () => pending.abort()
  }, [wardId])

  return <section className="ward-main" aria-label="Ward report card" aria-busy={wardId !== null && !card && !error}>
    {wardId === null && <div className="ward-empty">
      <h2>Choose a ward</h2>
      <p>Pick a ward from the list, or search an address to find yours. Each report card shows City of Toronto data about sidewalks, curbs, snow clearing and TTC elevators.</p>
    </div>}
    {error && <p className="error" role="alert">{error}</p>}
    {wardId !== null && !card && !error && <p className="loading ward-loading" role="status">Loading the ward report card…</p>}
    {card && <WardCard card={card} />}
  </section>
}
