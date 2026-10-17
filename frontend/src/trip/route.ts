import { formatDistance } from '../format'
import type { Choice, Gap, LngLat, Plan, RouteOption, TransitLeg } from '../types'
import { makeTrack } from './progress'
import type { Track } from './progress'

/** One instruction on a trip, placed by distance along the whole route. */
export type TripStep = {
  instruction: string
  start_m: number
  end_m: number
  type: number | null
  ride: { line: string; color: string | null; from: string; to: string } | null
}

/** Everything the trip needs from the chosen option, flattened to one line. */
export type TripRoute = {
  choice: Choice
  track: Track
  steps: TripStep[]
  duration_s: number
  stations: { name: string; at_m: number }[]
  unverified: Gap[]
  destination: string
}

const RAPID = new Set(['SUBWAY', 'TRAM', 'METRO', 'RAIL', 'REGIONAL_RAIL', 'LIGHT_RAIL'])

function lineName(leg: TransitLeg) {
  if (leg.mode === 'SUBWAY' || (leg.mode === 'TRAM' && ['5', '6'].includes(leg.line ?? ''))) return `Line ${leg.line}`
  if (leg.mode === 'TRAM') return `Streetcar ${leg.line}`
  if (leg.mode === 'BUS') return `Bus ${leg.line}`
  return leg.line ? `${leg.mode.toLowerCase()} ${leg.line}` : leg.mode.toLowerCase()
}

function place(name: string, destination: string) {
  return name === 'START' ? 'your start' : name === 'END' ? destination : name
}

function streetRoute(route: RouteOption, choice: Choice, destination: string): TripRoute {
  const track = makeTrack(route.geometry.coordinates.map(([lng, lat]) => [lng, lat] as LngLat))
  let running = 0
  const steps = route.steps.map((step) => {
    // ORS gives the coordinate range each step covers; fall back to step lengths if it's missing.
    const start = step.way_points ? track.cum[step.way_points[0]] ?? running : running
    const end = step.way_points ? track.cum[step.way_points[1]] ?? start + step.distance_m : start + step.distance_m
    running = end
    return { instruction: step.instruction, start_m: start, end_m: end, type: step.type ?? null, ride: null }
  })
  return { choice, track, steps, duration_s: route.duration_s, stations: [], unverified: route.unverified, destination }
}

function transitRoute(plan: Plan, choice: Choice, destination: string): TripRoute | null {
  const option = plan.transit[Number(choice.split('-')[1])]
  if (!option) return null
  const coords: LngLat[] = []
  const spans: [number, number][] = []
  for (const leg of option.legs) {
    const points = (leg.geometry?.coordinates ?? []).map(([lng, lat]) => [lng, lat] as LngLat)
    const from = Math.max(0, coords.length - 1)
    coords.push(...(coords.length ? points.slice(1) : points))
    spans.push([from, Math.max(from, coords.length - 1)])
  }
  if (coords.length < 2) return null
  const track = makeTrack(coords)
  const stations: TripRoute['stations'] = []
  const steps = option.legs.map((leg, index) => {
    const [a, b] = spans[index]
    const start = track.cum[a], end = track.cum[b]
    if (leg.mode === 'WALK') {
      return { instruction: `Walk or roll ${formatDistance(leg.distance_m)} to ${place(leg.to_name, destination)}`,
        start_m: start, end_m: end, type: null, ride: null }
    }
    if (RAPID.has(leg.mode)) stations.push({ name: leg.from_name, at_m: start }, { name: leg.to_name, at_m: end })
    const name = lineName(leg)
    return { instruction: `Take ${name}${leg.headsign ? ` (${leg.headsign})` : ''} to ${leg.to_name}`, start_m: start, end_m: end,
      type: null, ride: { line: name, color: leg.color, from: leg.from_name, to: leg.to_name } }
  })
  return { choice, track, steps, duration_s: option.duration_s, stations, unverified: [], destination }
}

export function tripRoute(plan: Plan, choice: Choice, destination: string): TripRoute | null {
  if (choice.startsWith('transit-')) return transitRoute(plan, choice, destination)
  const route = choice === 'ideal' ? plan.ideal : plan.accessible
  return route ? streetRoute(route, choice, destination) : null
}

export function stepAt(steps: TripStep[], along: number): number {
  const index = steps.findIndex((step) => along < step.end_m)
  return index === -1 ? steps.length - 1 : index
}
