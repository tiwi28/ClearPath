import { getWard } from '../api'
import type { WardCard } from '../types'

// Ward cards fetched this session. City numbers only change with a new export; the live numbers
// on a card are refetched once it is older than FRESH_MS, while the cached card stays on screen.
const FRESH_MS = 60_000
const cards = new Map<number, { card: WardCard; at: number }>()
const pending = new Map<number, Promise<WardCard>>()

export function cachedWard(id: number): { card: WardCard; fresh: boolean } | null {
  const entry = cards.get(id)
  return entry ? { card: entry.card, fresh: Date.now() - entry.at < FRESH_MS } : null
}

/** Fetch a card, sharing one request between a prefetch and the click that follows it. */
export function loadWard(id: number): Promise<WardCard> {
  let request = pending.get(id)
  if (!request) {
    request = getWard(id)
      .then((card) => { cards.set(id, { card, at: Date.now() }); return card })
      .finally(() => pending.delete(id))
    pending.set(id, request)
  }
  return request
}

export function prefetchWard(id: number) {
  if (!cachedWard(id)?.fresh) loadWard(id).catch(() => { /* the click will show the error */ })
}

export function clearWardCache() {
  cards.clear()
  pending.clear()
}
