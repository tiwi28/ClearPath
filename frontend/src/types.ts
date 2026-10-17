import type { FeatureCollection, Geometry, LineString, Polygon } from 'geojson'

export type LngLat = [number, number]
export type BarrierProperties = {
  id: number
  source: string
  kind: string
  status: string
  verification: 'verified' | 'reported'
  blocks_route: boolean
  label?: string
  source_url?: string
  opened_at?: string
}
export type Barriers = FeatureCollection<Geometry, BarrierProperties> & {
  data_source: 'fixtures' | 'postgres'
}
export type RiskProperties = {
  cell: string
  risk: number
  reports_last_year: number
}
export type RiskMap = FeatureCollection<Polygon, RiskProperties> & {
  date: string
  reports_through: string
  weather: Record<string, number | null>
  weather_source: string
  model: { roc_auc: number; pr_auc: number; top10_capture: number; lag_days: number }
  warnings: string[]
}
export type Outage = { kind: 'elevator' | 'escalator'; code: string | null; text: string; since: string | null }
export type Station = {
  name: string
  lines: string[]
  coordinates: LngLat
  has_elevator: boolean
  outages: Outage[]
}
export type Stations = {
  alerts_available: boolean
  alerts_updated: string | null
  closures: { line: string; from_station: string; to_station: string | null; text: string }[]
  stations: Station[]
}
export type Place = {
  label: string
  coordinates: LngLat
}

export type ProfileName = 'manual_wheelchair' | 'power_wheelchair' | 'walker' | 'limited_stamina'
export type PlanRequest = {
  from: LngLat
  to: LngLat
  profile: ProfileName
  include_transit: boolean
  avoid_risk: boolean
  day: string | null
}
export type RouteRisk = {
  max: number
  mean: number
  cells_crossed: number
  high_risk_cells: number
  high_risk_share: number
}
export type Gap = { end: 'start' | 'destination'; geometry: LineString; length_m: number; uses_stairs: boolean }
export type Step = { instruction: string; distance_m: number }
export type RouteOption = {
  geometry: LineString
  distance_m: number
  duration_s: number
  steps: Step[]
  risk: RouteRisk | null
  stairs: LineString[]
  unverified: Gap[]
}
export type AccessibleRoute = RouteOption & {
  risk_avoided: boolean
  standard: RouteOption | null
  avoided_barrier_ids: number[]
}
export type TransitIssue = { severity: 'blocker' | 'warning'; station: string; kind: string; text: string }
export type TransitLeg = {
  mode: string
  line: string | null
  headsign: string | null
  color: string | null
  from_name: string
  to_name: string
  start: string
  end: string
  duration_s: number
  distance_m: number
  geometry: LineString | null
  risk: RouteRisk | null
}
export type TransitOption = {
  start: string
  end: string
  duration_s: number
  transfers: number
  walk_m: number
  legs: TransitLeg[]
  issues: TransitIssue[]
  step_free: boolean
}
export type Plan = {
  profile: ProfileName
  ideal: RouteOption | null
  accessible: AccessibleRoute | null
  transit: TransitOption[]
  risk: { available: boolean; date: string | null; reports_through: string | null }
  warnings: string[]
  barrier_source: 'fixtures' | 'postgres'
}
/** Which option card is selected: the street route, the typical route, or a transit option by index. */
export type Choice = 'accessible' | 'ideal' | `transit-${number}`
