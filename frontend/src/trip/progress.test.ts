import { expect, it } from 'vitest'
import { arrived, makeTrack, offRouteCount, offsetAt, pointAt, project, travelled } from './progress'
import { stepAt } from './route'
import type { LngLat } from '../types'

// About 400 m east along Front St, then 200 m north.
const corner: LngLat = [-79.3850, 43.6450]
const east: LngLat = [-79.3800, 43.6450]
const north: LngLat = [-79.3800, 43.6468]
const track = makeTrack([corner, east, north])

it('measures the route in metres', () => {
  expect(track.cum[1]).toBeGreaterThan(395)
  expect(track.cum[1]).toBeLessThan(410)
  expect(track.total).toBeGreaterThan(590)
})

it('snaps a position to the route and measures how far off it is', () => {
  const halfway = pointAt(track, 200).lnglat
  const { along, off } = project(track, halfway)
  expect(along).toBeCloseTo(200, 0)
  expect(off).toBeLessThan(0.5)
  const beside = project(track, offsetAt(track, 200, 50))
  expect(beside.off).toBeCloseTo(50, 0)
})

it('gives the heading of travel', () => {
  expect(pointAt(track, 100).heading).toBeCloseTo(90, 0)
  expect(pointAt(track, 500).heading).toBeCloseTo(0, 0)
})

it('needs three readings in a row before calling a trip off route', () => {
  let count = 0
  for (const off of [45, 45]) count = offRouteCount(count, off)
  expect(count).toBe(2)
  count = offRouteCount(count, 5)
  expect(count).toBe(0)
  expect(offRouteCount(0, 40, 60)).toBe(0) // poor GPS accuracy widens the allowance
})

it('arrives near the end and draws only the travelled part', () => {
  expect(arrived(track, track.total - 10, north)).toBe(true)
  expect(arrived(track, 300, pointAt(track, 300).lnglat)).toBe(false)
  expect(travelled(track, 0)).toEqual([])
  expect(travelled(track, 450).length).toBe(3)
})

it('finds the current step by distance along the route', () => {
  const steps = [{ end_m: 400 }, { end_m: 600 }].map((step, i) => ({ instruction: `${i}`, start_m: 0, type: null, ride: null, ...step }))
  expect(stepAt(steps, 10)).toBe(0)
  expect(stepAt(steps, 450)).toBe(1)
  expect(stepAt(steps, 700)).toBe(1)
})
