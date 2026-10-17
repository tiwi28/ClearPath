import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from '../App'

vi.mock('maplibre-gl', () => ({
  setWorkerUrl() {},
  Map: class { constructor() { throw new Error('WebGL unavailable in test') } },
}))

const month = (m: string, snow: number, damage: number) => ({ month: m, snow_ice: snow, damage, ramps: 0 })
const card = {
  id: 10, name: 'Spadina-Fort York', snow_last_winter: 625, damage_12m: 511, ramps_12m: 35,
  reports_12m: 1171, reports_prior_12m: 1055, open_share_12m: 0.15,
  monthly: Array.from({ length: 24 }, (_, i) => month(`20${24 + Math.floor((i + 9) / 12)}-${String(((i + 9) % 12) + 1).padStart(2, '0')}`, i % 12 < 4 ? 100 : 0, 30)),
  monthly_prior_year: [],
  top_places: [{ place: 'Lake Shore Blvd W & Bathurst St', reports: 15 }],
  geometry: { type: 'Polygon', coordinates: [[[-79.42, 43.63], [-79.37, 43.63], [-79.37, 43.65], [-79.42, 43.65], [-79.42, 43.63]]] },
  meta: { reports_through: '2026-09-30', winter: ['2025-11-01', '2026-04-30'], year_from: '2025-10-01' },
  sources: { 311: 'https://open.toronto.ca/a', wards: 'https://open.toronto.ca/b', ttc: 'https://www.ttc.ca', closures: 'https://open.toronto.ca/c', forecast: 'https://open-meteo.com/' },
  generated_at: '2026-10-17T11:38-04:00',
  live: {
    elevators: { available: true, out: 1, outages: [{ station: 'Union', text: 'Elevator out' }], stations: 4, stations_with_elevator: 4 },
    closures: { available: false },
    forecast: { available: true, date: '2026-10-17', cells: 15, high: 2, elevated: 5 },
  },
  summary: 'Last winter, people in this ward filed 625 reports about sidewalks not cleared of snow or ice.',
  summary_source: 'template',
}

function reply(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: string) => input.endsWith('/wards') ? reply({ wards: [{ id: 9, name: 'Davenport' }, { id: 10, name: 'Spadina-Fort York' }] })
    : input.includes('/wards/10') ? reply(card)
      : input.includes('/risk') ? reply({ type: 'FeatureCollection', features: [], date: '2026-10-17', reports_through: '2026-09-30',
        weather: {}, weather_source: 'test', model: { roc_auc: 0.856, pr_auc: 0.39, top10_capture: 0.26, lag_days: 40 }, warnings: [] })
        : input.includes('/stations') ? reply({ alerts_available: true, alerts_updated: null, closures: [], stations: [] })
          : reply({ type: 'FeatureCollection', features: [], data_source: 'fixtures' })))
  window.location.hash = '#wards/10'
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); window.location.hash = '' })

it('opens a ward report card from the link and shows its numbers', async () => {
  render(<App />)
  expect(await screen.findByRole('heading', { name: /Spadina-Fort York/, level: 2 })).toBeTruthy()
  expect(screen.getByText(/does not mention candidates/)).toBeTruthy()
  expect(screen.getByText('625')).toBeTruthy()
  expect(screen.getByText('Summary of the numbers below')).toBeTruthy()
  expect(screen.getByText(/11% more than the year before/)).toBeTruthy()
})

it('says a live number is unavailable instead of showing zero', async () => {
  render(<App />)
  const label = await screen.findByText('Active road or sidewalk restrictions')
  expect(within(label.closest('.stat') as HTMLElement).getByText('Unavailable')).toBeTruthy()
})

it('lists wards by number and switches back to trip planning', async () => {
  render(<App />)
  expect(await screen.findByRole('button', { name: /Davenport/ })).toBeTruthy()
  expect(screen.getByText('Listed by ward number. Wards are not ranked.')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /Trip: plan a trip/ }))
  window.dispatchEvent(new HashChangeEvent('hashchange'))
  expect(await screen.findByRole('heading', { name: 'Where are you going?' })).toBeTruthy()
})
