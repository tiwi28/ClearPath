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

// Several ticks inside one act() render once, so step the clock when each reading must be seen.
async function readings(count: number) {
  for (let i = 0; i < count; i += 1) await advance(300)
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
  expect(screen.getByRole('heading', { name: 'Where are you going?' })).toBeTruthy()
})

async function planAndSimulate() {
  fireEvent.click(screen.getByRole('button', { name: /Try an example/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Next: how you get around' }))
  fireEvent.click(screen.getByRole('button', { name: 'Find routes' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Simulate' }))
}

const planCalls = () => vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith('/plan')).length

it('starts a second trip fresh: directions are spoken and spots are asked about again', async () => {
  const spoken: string[] = []
  vi.stubGlobal('speechSynthesis', { cancel() {}, speak(utterance: { text: string }) { spoken.push(utterance.text) } })
  vi.stubGlobal('SpeechSynthesisUtterance', class { text: string; constructor(text: string) { this.text = text } })
  render(<App />)
  await planAndSimulate()
  await advance(13_000)
  fireEvent.click(await screen.findByRole('button', { name: 'Blocked' }))
  fireEvent.click(screen.getByRole('button', { name: 'End trip' }))

  spoken.length = 0
  fireEvent.click(await screen.findByRole('button', { name: 'Simulate' }))
  await advance(1000)
  expect(spoken).toContain('Head west on Front St')
  await advance(12_000)
  expect(await screen.findByRole('button', { name: 'Blocked' })).toBeTruthy()
  expect(screen.queryByText(/Thanks\. Other riders/)).toBeNull()
})

it('ignores a re-route that answers after the trip has ended', async () => {
  let answer: (value: Response) => void = () => {}
  const base = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (input) => String(input).endsWith('/plan') && planCalls() > 1
    ? new Promise<Response>((resolve) => { answer = resolve }) : base(input as string))
  render(<App />)
  await planAndSimulate()
  await advance(1000)
  fireEvent.click(screen.getByRole('button', { name: 'Take a wrong turn' }))
  await readings(4)
  expect(planCalls()).toBe(2)
  fireEvent.click(screen.getByRole('button', { name: 'End trip' }))
  await act(async () => { answer(reply({ ...plan, warnings: ['late'] })) })
  expect(screen.getByRole('heading', { name: 'Your options' })).toBeTruthy()
  expect(screen.queryByText('Your location')).toBeNull()
})

it('tries a failed re-route again after a pause', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
  const base = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (input) => String(input).endsWith('/plan') && planCalls() > 1
    ? reply({ detail: { code: 'routing_unavailable', message: 'The routing service is unavailable.' } }, 502) : base(input as string))
  render(<App />)
  await planAndSimulate()
  await advance(1000)
  fireEvent.click(screen.getByRole('button', { name: 'Take a wrong turn' }))
  await readings(4)
  expect(planCalls()).toBe(2)
  expect(await screen.findByText('The routing service is unavailable.')).toBeTruthy()
  await readings(10)
  expect(planCalls()).toBe(2)
  await advance(20_000)
  await readings(4)
  expect(planCalls()).toBe(3)
})

it('re-routes after every wrong turn, even on a new route that doubles back', async () => {
  // Like ORS, each new route starts where the rider strayed and heads back to Front St before going west.
  const base = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    if (!String(input).endsWith('/plan') || planCalls() === 1) return base(input as string)
    const from = JSON.parse(init!.body as string).from as number[]
    const coordinates = [from, [from[0], 43.6453], [-79.3872, 43.6453]]
    return reply({ ...plan, accessible: { ...plan.accessible, geometry: line(coordinates),
      steps: [{ instruction: 'Head back to Front St', distance_m: 60, way_points: [0, 1], type: 11 },
        { instruction: 'Head west on Front St', distance_m: 470, way_points: [1, 2], type: 11 }] } })
  })
  render(<App />)
  await planAndSimulate()
  await advance(1000)
  for (const expected of [2, 3, 4]) {
    fireEvent.click(screen.getByRole('button', { name: 'Take a wrong turn' }))
    await readings(4)
    expect(planCalls()).toBe(expected)
    await advance(5000) // about 40 m along the new route: partway back to Front St
  }
})

it('says so when turn-by-turn is not available for an option', async () => {
  const leg = { mode: 'BUS', line: '6', headsign: null, color: null, from_name: 'START', to_name: 'END', start: '2026-10-17T10:00:00Z',
    end: '2026-10-17T10:10:00Z', duration_s: 600, distance_m: 900, geometry: null, risk: null }
  const transitOnly = { ...plan, accessible: null,
    transit: [{ start: leg.start, end: leg.end, duration_s: 600, transfers: 0, walk_m: 0, legs: [leg], issues: [], step_free: true }] }
  const base = vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async (input) => String(input).endsWith('/plan') ? reply(transitOnly) : base(input as string))
  render(<App />)
  await planAndSimulate()
  expect(screen.getByRole('alert').textContent).toMatch(/Turn-by-turn isn't available/)
  expect(screen.queryByRole('heading', { name: 'On your way' })).toBeNull()
})
