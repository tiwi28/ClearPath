import { useEffect, useState } from 'react'
import type { WardCard as Card } from '../types'
import { cachedWard, loadWard } from './cache'
import WardCard from './WardCard'

export default function WardPage({ wardId }: { wardId: number | null }) {
  // Keyed by ward id in App, so a cached card is on screen from the first render.
  const [card, setCard] = useState<Card | null>(() => wardId === null ? null : cachedWard(wardId)?.card ?? null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (wardId === null) return
    const cached = cachedWard(wardId)
    if (cached?.fresh) return
    // The request is shared with any prefetch, so it is not aborted; a late answer is ignored instead.
    let current = true
    loadWard(wardId).then((next) => { if (current) setCard(next) }).catch((failure) => {
      if (current && !cached) setError(failure instanceof Error ? failure.message : String(failure))
    })
    return () => { current = false }
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
