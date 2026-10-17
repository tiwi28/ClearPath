import type { LngLat } from '../types'

/** Route geometry in local metres (Toronto), with the distance from the start to each vertex. */
export type Track = { coords: LngLat[]; xy: [number, number][]; cum: number[]; total: number }

const KX = 111_320 * Math.cos(43.7 * Math.PI / 180)
const KY = 110_540
export const OFF_ROUTE_M = 30
export const OFF_ROUTE_READINGS = 3
export const ARRIVE_M = 20

const toXY = ([lng, lat]: LngLat): [number, number] => [lng * KX, lat * KY]
const toLngLat = ([x, y]: [number, number]): LngLat => [x / KX, y / KY]

export function makeTrack(coords: LngLat[]): Track {
  const xy = coords.map(toXY)
  const cum = [0]
  for (let i = 1; i < xy.length; i += 1) cum.push(cum[i - 1] + Math.hypot(xy[i][0] - xy[i - 1][0], xy[i][1] - xy[i - 1][1]))
  return { coords, xy, cum, total: cum[cum.length - 1] ?? 0 }
}

/** Snap a position to the route: how far along it is, and how far off it. */
export function project(track: Track, point: LngLat): { along: number; off: number } {
  const [px, py] = toXY(point)
  let best = { along: 0, off: Infinity }
  for (let i = 1; i < track.xy.length; i += 1) {
    const [ax, ay] = track.xy[i - 1]
    const [bx, by] = track.xy[i]
    const dx = bx - ax, dy = by - ay
    const length2 = dx * dx + dy * dy
    const t = length2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / length2)) : 0
    const off = Math.hypot(px - (ax + t * dx), py - (ay + t * dy))
    if (off < best.off) best = { along: track.cum[i - 1] + t * Math.sqrt(length2), off }
  }
  return best
}

/** The point `along` metres from the start, and the direction of travel there (degrees from north). */
export function pointAt(track: Track, along: number): { lnglat: LngLat; heading: number } {
  const distance = Math.max(0, Math.min(track.total, along))
  let i = 1
  while (i < track.cum.length - 1 && track.cum[i] < distance) i += 1
  const [ax, ay] = track.xy[i - 1]
  const [bx, by] = track.xy[i] ?? track.xy[i - 1]
  const length = track.cum[i] - track.cum[i - 1] || 1
  const t = (distance - track.cum[i - 1]) / length
  const heading = (Math.atan2(bx - ax, by - ay) * 180 / Math.PI + 360) % 360
  return { lnglat: toLngLat([ax + t * (bx - ax), ay + t * (by - ay)]), heading }
}

/** A point `metres` to the right of the route at `along`; the simulator uses it for "take a wrong turn". */
export function offsetAt(track: Track, along: number, metres: number): LngLat {
  const { lnglat, heading } = pointAt(track, along)
  const [x, y] = toXY(lnglat)
  const angle = (heading + 90) * Math.PI / 180
  return toLngLat([x + Math.sin(angle) * metres, y + Math.cos(angle) * metres])
}

/** The travelled part of the route, for drawing it grey. */
export function travelled(track: Track, along: number): LngLat[] {
  const points = track.coords.filter((_, i) => track.cum[i] < along)
  return points.length ? [...points, pointAt(track, along).lnglat] : []
}


/** Count readings in a row that are off the route; GPS accuracy widens the allowance. */
export function offRouteCount(previous: number, off: number, accuracy = 0): number {
  return off > Math.max(OFF_ROUTE_M, accuracy) ? previous + 1 : 0
}

export function arrived(track: Track, along: number, point: LngLat): boolean {
  const [ex, ey] = track.xy[track.xy.length - 1]
  const [px, py] = toXY(point)
  return track.total - along <= ARRIVE_M || Math.hypot(ex - px, ey - py) <= ARRIVE_M
}

export function formatMetres(metres: number) {
  if (metres < 1000) return `${Math.max(0, Math.round(metres / 10) * 10)} m`
  return `${(metres / 1000).toFixed(1)} km`
}
