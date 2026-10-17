import type { Barriers, Place, Plan, PlanRequest, RiskMap, Stations } from './types'

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
