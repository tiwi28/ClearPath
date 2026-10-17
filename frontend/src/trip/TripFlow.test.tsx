import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from '../App'

vi.mock('maplibre-gl', () => ({
  setWorkerUrl() {},
  Map: class { constructor() { throw new Error('WebGL unavailable in test') } },
}))

const line = (coordinates: number[][]) => ({ type: 'LineString', coordinates })
const risk = { type: 'FeatureCollection', features: [], date: '2026-10-17', reports_through: '2026-09-30', weather: {},
  weather_source: 'test', model: { roc_auc: 0.856, pr_auc: 0.39, top10_capture: 0.26, lag_days: 40 }, warnings: [] }
const routeRisk = { max: 0, mean: 0, cells_crossed: 0, high_risk_cells: 0, high_risk_share: 0 }
// About 530 m due west along Front St, covered at 2 m/s.
const geometry = line([[-79.3806, 43.6453], [-79.3872, 43.6453]])
const plan = {
  profile: 'manual_wheelchair', ideal: null, transit: [], warnings: [], barrier_source: 'fixtures',
  risk: { available: true, date: '2026-10-17', reports_through: '2026-09-30' },
  accessible: { geometry, distance_m: 530, duration_s: 265, risk: routeRisk, stairs: [], unverified: [],
    steps: [{ instruction: 'Head west on Front St', distance_m: 530, way_points: [0, 1], type: 11 },
      { instruction: 'Arrive at the CN Tower', distance_m: 0, way_points: [1, 1], type: 10 }],
    risk_avoided: false, standard: null, avoided_barrier_ids: [] },
}
const hazard = { id: 'barrier-7', kind: 'barrier', label: 'Construction hoarding on the sidewalk', severity: 'warning',
  source: 'city', confirmable: true, at_m: 60, lnglat: [-79.3813, 43.6453] }

function reply(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  localStorage.clear()
  vi.stubGlobal('fetch', vi.fn(async (input: string) => input.includes('/trip/hazards') ? reply({ hazards: [hazard] })
    : input.includes('/reports') ? reply({ id: 1 }, 201)
      : input.includes('/plan') ? reply(plan)
        : input.includes('/risk') ? reply(risk)
          : input.includes('/stations') ? reply({ alerts_available: true, alerts_updated: null, closures: [], stations: [] })
            : reply({ type: 'FeatureCollection', features: [], data_source: 'fixtures' })))
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals() })

async function advance(ms: number) {
  await act(async () => { vi.advanceTimersByTime(ms) })
}

it('simulates a trip: directions, an alert ahead, a rider report, and arrival', async () => {
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: /Try an example/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Next: how you get around' }))
  fireEvent.click(screen.getByRole('button', { name: 'Find routes' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Simulate' }))

  expect(screen.getByRole('heading', { name: 'On your way' })).toBeTruthy()
  await advance(1000)
  expect(screen.getByText('Head west on Front St')).toBeTruthy()
  expect((await screen.findByRole('alert')).textContent).toMatch(/Construction hoarding on the sidewalk/)

  await advance(12_000) // about 100 m at 4x: past the hoarding, so ClearPath asks about it
  fireEvent.click(await screen.findByRole('button', { name: 'Blocked' }))
  const report = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith('/reports'))!
  expect(JSON.parse(report[1]!.body as string)).toMatchObject({ kind: 'blocked_sidewalk', state: 'blocked', location: hazard.lnglat })

  fireEvent.click(screen.getByRole('radio', { name: '10×' }))
  await advance(30_000)
  expect(await screen.findByText("You've arrived")).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Done' }))
  expect(screen.getByRole('heading', { name: 'Your options' })).toBeTruthy()
})
