import type { Feature, FeatureCollection, LineString } from 'geojson'
import type { Choice, Plan, Station } from './types'

export function line(geometry: LineString, properties: Record<string, string> = {}): Feature<LineString> {
  return { type: 'Feature', geometry, properties }
}

/** Lines for the selected option: a street route, the typical route, or transit legs. */
export function selectedLines(plan: Plan | null, choice: Choice): FeatureCollection<LineString> {
  if (!plan) return { type: 'FeatureCollection', features: [] }
  if (choice === 'ideal') {
    return { type: 'FeatureCollection', features: plan.ideal ? [line(plan.ideal.geometry, { kind: 'typical' })] : [] }
  }
  if (choice === 'accessible') {
    const route = plan.accessible
    return { type: 'FeatureCollection', features: route ? [
      line(route.geometry, { kind: 'street' }),
      ...route.unverified.map((gap) => line(gap.geometry, { kind: 'gap' })),
    ] : [] }
  }
  const option = plan.transit[Number(choice.split('-')[1])]
  return { type: 'FeatureCollection', features: (option?.legs ?? []).flatMap((leg) => leg.geometry
    ? [line(leg.geometry, { kind: leg.mode === 'WALK' ? 'walk' : 'ride', color: leg.color || '#da251d' })] : []) }
}

export function stationStatus(station: Station) {
  if (!station.has_elevator) return 'none'
  return station.outages.some((outage) => outage.kind === 'elevator') ? 'outage' : 'ok'
}
