import type { Barriers, Gap, Hazard, LngLat, Place, Plan, PlanRequest, ProfileName, ReportKind, RiskMap, Stations, WardCard, WardSummary } from './types'

const baseUrl = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

export class ApiError extends Error {
  body: unknown
  constructor(message: string, body: unknown) { super(message); this.body = body }
}

async function request<T>(path: string, options: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, options)
  let body
  try { body = await response.json() } catch {
    throw new Error('The API returned an unreadable response. Try again.')
  }
  if (!response.ok) {
    const detail = body.detail
    const message = typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail.map((item: { msg: string }) => item.msg).join(' ')
        : detail?.message
    throw new ApiError(message || `Request failed (${response.status}). Try again.`, body)
  }
  return body as T
}

export function getBarriers(bbox: string, signal: AbortSignal): Promise<Barriers> {
  return request(`/barriers?${new URLSearchParams({ bbox })}`, { signal })
}

export function getRisk(day: string | null, signal: AbortSignal): Promise<RiskMap> {
  return request(`/risk${day ? `?${new URLSearchParams({ day })}` : ''}`, { signal })
}

export function getStations(signal: AbortSignal): Promise<Stations> {
  return request('/stations', { signal })
}

export async function searchPlaces(text: string, signal: AbortSignal): Promise<Place[]> {
  const body = await request<{ results: Place[] }>(`/geocode?${new URLSearchParams({ text })}`, { signal })
  return body.results
}

export function getPlan(body: PlanRequest, signal: AbortSignal): Promise<Plan> {
  return request('/plan', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body), signal,
  })
}

export async function getWards(signal: AbortSignal): Promise<WardSummary[]> {
  return (await request<{ wards: WardSummary[] }>('/wards', { signal })).wards
}

export function getWard(id: number, signal?: AbortSignal): Promise<WardCard> {
  return request(`/wards/${id}`, { signal })
}

export function locateWard(point: [number, number], signal: AbortSignal): Promise<WardSummary> {
  return request(`/wards/locate?${new URLSearchParams({ lng: String(point[0]), lat: String(point[1]) })}`, { signal })
}

export type HazardRequest = { route: { type: 'LineString'; coordinates: LngLat[] }; day: string | null; stations: { name: string; at_m: number }[]; unverified: Gap[] }

export async function getHazards(body: HazardRequest, signal: AbortSignal): Promise<Hazard[]> {
  const result = await request<{ hazards: Hazard[] }>('/trip/hazards', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal,
  })
  return result.hazards
}

export type ReportBody = { device_id: string; kind: ReportKind; state: 'blocked' | 'clear'; profile: ProfileName; location: LngLat }

export function postReport(body: ReportBody): Promise<{ id: number }> {
  return request('/reports', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
}
