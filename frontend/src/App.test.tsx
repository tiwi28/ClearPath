import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'
import { forecastDays } from './format'

vi.mock('maplibre-gl', () => ({
  setWorkerUrl() {},
  Map: class { constructor() { throw new Error('WebGL unavailable in test') } },
}))

const line = (coordinates: number[][]) => ({ type: 'LineString', coordinates })
const barriers = { type: 'FeatureCollection', features: [], data_source: 'fixtures' }
const risk = { type: 'FeatureCollection', features: [], date: '2026-10-17', reports_through: '2026-09-30', weather: {},
  weather_source: 'Open-Meteo', model: { roc_auc: 0.856, pr_auc: 0.39, top10_capture: 0.26, lag_days: 40 }, warnings: [] }
const stations = { alerts_available: true, alerts_updated: null, closures: [], stations: [] }
const places = { results: [{ label: 'Kensington Market, Toronto, ON, Canada', coordinates: [-79.4006, 43.6547] }] }
const routeRisk = { max: 0.05, mean: 0.04, cells_crossed: 2, high_risk_cells: 0, high_risk_share: 0 }
const plan = {
  profile: 'walker',
  ideal: { geometry: line([[-79.3806, 43.6453], [-79.3871, 43.6426]]), distance_m: 690, duration_s: 500,
    steps: [{ instruction: 'Take the stairs', distance_m: 40 }], risk: routeRisk,
    stairs: [line([[-79.381, 43.645], [-79.3812, 43.6449]]), line([[-79.385, 43.643], [-79.3852, 43.6429]])], unverified: [] },
  accessible: { geometry: line([[-79.3806, 43.6453], [-79.3871, 43.6426]]), distance_m: 789, duration_s: 877,
    steps: [{ instruction: 'Head west on Front St', distance_m: 300 }], risk: routeRisk, stairs: [],
    unverified: [{ end: 'destination', geometry: line([[-79.387, 43.6427], [-79.3871, 43.6426]]), length_m: 40, uses_stairs: false }],
    risk_avoided: false, standard: null, avoided_barrier_ids: [] },
  transit: [{ start: '2026-10-17T14:02:00Z', end: '2026-10-17T14:20:00Z', duration_s: 1080, transfers: 0, walk_m: 300, step_free: true, issues: [],
    legs: [
      { mode: 'WALK', line: null, headsign: null, color: null, from_name: 'START', to_name: 'Union Station - Northbound Platform',
        start: '2026-10-17T14:02:00Z', end: '2026-10-17T14:07:00Z', duration_s: 300, distance_m: 160, geometry: null, risk: null },
      { mode: 'SUBWAY', line: '1', headsign: 'Line 1 towards Finch', color: '#d5c82b', from_name: 'Union Station', to_name: 'St Andrew Station',
        start: '2026-10-17T14:07:00Z', end: '2026-10-17T14:10:00Z', duration_s: 180, distance_m: 900, geometry: null, risk: null },
    ] }],
  risk: { available: true, date: '2026-10-17', reports_through: '2026-09-30' },
  warnings: ['Predicted barrier risk is low along this trip.'],
  barrier_source: 'fixtures',
}

function reply(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}
function api(planReply: () => Response | Promise<Response> = () => reply(plan)) {
  return vi.fn(async (input: string) => input.includes('/barriers') ? reply(barriers)
    : input.includes('/risk') ? reply(risk) : input.includes('/stations') ? reply(stations)
      : input.includes('/geocode') ? reply(places) : planReply())
}
function planCalls() {
  return vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith('/plan'))
}
async function reachOptions(profile = 'Walker, cane or crutches') {
  fireEvent.click(screen.getByRole('button', { name: /Try an example/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Next: how you get around' }))
  fireEvent.click(screen.getByRole('radio', { name: new RegExp(profile) }))
  fireEvent.click(screen.getByRole('button', { name: 'Find routes' }))
}
beforeEach(() => { vi.stubGlobal('fetch', api()); localStorage.clear() })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('walks from places to profile to options and compares with the typical route', async () => {
  render(<App />)
  await reachOptions()
  await screen.findByText('Route without stairs')
  const body = JSON.parse(planCalls()[0][1]!.body as string)
  expect(body).toEqual({ from: [-79.3806, 43.6453], to: [-79.3871, 43.6426], profile: 'walker',
    include_transit: true, avoid_risk: true, day: forecastDays()[0].value })
  expect(screen.getByText(/Avoids 2 sets of stairs on the typical route for 99 m more/)).toBeTruthy()
  expect(screen.getByText(/Last 40 m not confirmed step-free/)).toBeTruthy()
  expect(screen.getByText('Line 1')).toBeTruthy()
  expect(screen.getByText('Stations have working elevators')).toBeTruthy()
  expect(screen.getByText(/Uses stairs in 2 places/)).toBeTruthy()
  expect(screen.getByText('Head west on Front St')).toBeTruthy()
})

it('shows transit directions when a TTC option is chosen', async () => {
  render(<App />)
  await reachOptions()
  fireEvent.click(await screen.findByRole('radio', { name: /TTC, arrive/ }))
  expect(screen.getByText(/Take Line 1 \(Line 1 towards Finch\) from Union Station to St Andrew Station/)).toBeTruthy()
})

it('needs both places before moving on', () => {
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Next: how you get around' }))
  expect(screen.getByRole('alert').textContent).toMatch(/Choose a start from the suggestions/)
  expect(screen.getByRole('heading', { name: 'Where are you going?' })).toBeTruthy()
})

it('fills a field from address suggestions', async () => {
  render(<App />)
  fireEvent.change(screen.getByLabelText('From'), { target: { value: 'kensington' } })
  fireEvent.mouseDown(await screen.findByRole('option', { name: /Kensington Market/ }))
  expect((screen.getByLabelText('From') as HTMLInputElement).value).toBe('Kensington Market, Toronto, ON, Canada')
})

it('remembers how the person gets around', async () => {
  render(<App />)
  await reachOptions('Limited stamina')
  await screen.findByText('Route without stairs')
  cleanup()
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: /Try an example/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Next: how you get around' }))
  expect((screen.getByRole('radio', { name: /Limited stamina/ }) as HTMLInputElement).checked).toBe(true)
})

it('re-plans when the forecast day changes', async () => {
  render(<App />)
  await reachOptions()
  await screen.findByText('Route without stairs')
  fireEvent.change(screen.getByRole('combobox', { name: 'Forecast for' }), { target: { value: forecastDays()[1].value } })
  await waitFor(() => expect(planCalls()).toHaveLength(2))
  expect(JSON.parse(planCalls()[1][1]!.body as string).day).toBe(forecastDays()[1].value)
})

it('keeps the full error response for debugging', async () => {
  const failure = { detail: { code: 'no_route', message: 'No accessible way to make this trip was found.' } }
  vi.stubGlobal('fetch', api(() => reply(failure, 404)))
  render(<App />)
  await reachOptions()
  expect((await screen.findByRole('alert')).textContent).toBe('No accessible way to make this trip was found.')
  expect(JSON.parse(screen.getByLabelText('Response JSON').textContent!)).toEqual(failure)
})

it('discards a late response after the trip changes', async () => {
  let finish: ((response: Response) => void) | undefined
  vi.stubGlobal('fetch', api(() => new Promise<Response>((resolve) => { finish = resolve })))
  render(<App />)
  await reachOptions()
  await waitFor(() => expect(finish).toBeDefined())
  fireEvent.click(screen.getByRole('button', { name: 'Change trip' }))
  await act(async () => { finish!(reply(plan)) })
  expect(screen.getByLabelText('Response JSON').textContent).toBe('No response yet.')
  expect(screen.getByRole('heading', { name: 'Where are you going?' })).toBeTruthy()
})
