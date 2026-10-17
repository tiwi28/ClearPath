import type { LngLat, ProfileName } from './types'

const TORONTO = 'America/Toronto'

/** Parse "longitude, latitude" typed or pasted into an address field. */
export function parsePoint(value: string): LngLat | null {
  const parts = value.split(',').map((part) => part.trim())
  if (parts.length !== 2 || parts.some((part) => !part)) return null
  const [longitude, latitude] = parts.map(Number)
  return Number.isFinite(longitude) && Number.isFinite(latitude)
    && longitude >= -180 && longitude <= 180 && latitude >= -90 && latitude <= 90
    ? [longitude, latitude] : null
}

export function pointText(point: LngLat) {
  return point.map((number) => number.toFixed(5)).join(', ')
}

export function formatDistance(meters: number) {
  return meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(1)} km`
}

export function formatDuration(seconds: number) {
  const minutes = Math.max(1, Math.round(seconds / 60))
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`
}

export function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString('en-CA', { hour: 'numeric', minute: '2-digit', timeZone: TORONTO })
}

export function percent(share: number) {
  return `${Math.round(share * 100)}%`
}

/** Today and the next two days in Toronto, as YYYY-MM-DD with a short label. */
export function forecastDays(now = new Date()): { value: string; label: string }[] {
  return [0, 1, 2].map((offset) => {
    const day = new Date(now.getTime() + offset * 86_400_000)
    const value = new Intl.DateTimeFormat('en-CA', { timeZone: TORONTO }).format(day)
    const label = offset === 0 ? 'Today' : offset === 1 ? 'Tomorrow'
      : day.toLocaleDateString('en-CA', { weekday: 'long', timeZone: TORONTO })
    return { value, label }
  })
}

export function formatDate(date: string) {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString('en-CA', { month: 'long', day: 'numeric', timeZone: 'UTC' })
}

// Sequential warm ramp for predicted risk (chance of a report in 3 days; base rate ~6%).
export const RISK_STOPS: [number, string][] = [[0.02, '#f6edc0'], [0.1, '#eea24a'], [0.3, '#d4512d'], [0.6, '#8e1d45']]

export const PROFILES: { value: ProfileName; label: string; detail: string }[] = [
  { value: 'manual_wheelchair', label: 'Manual wheelchair', detail: 'No stairs, gentle slopes, low curbs. Stations must have working elevators.' },
  { value: 'power_wheelchair', label: 'Power wheelchair or scooter', detail: 'No stairs or high curbs. Handles steeper slopes. Stations must have working elevators.' },
  { value: 'walker', label: 'Walker, cane or crutches', detail: 'No stairs, a slower pace. Escalators are fine, and we flag ones that are out.' },
  { value: 'limited_stamina', label: 'Limited stamina', detail: 'Shortest walking, a slower pace, and at most one transfer.' },
]
