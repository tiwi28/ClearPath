import { useEffect, useMemo, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import type { GeoJSONSource, Map as MapInstance } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { FeatureCollection } from 'geojson'
import 'maplibre-gl/dist/maplibre-gl.css'
import { RISK_STOPS } from '../format'
import { line, selectedLines, stationStatus } from '../mapData'
import type { Barriers, Choice, LngLat, Plan, RiskMap, RiskProperties, Station } from '../types'

maplibregl.setWorkerUrl(workerUrl)

export type Layers = { risk: boolean; stations: boolean; barriers: boolean }
export type Hover = { kind: 'risk'; cell: RiskProperties } | { kind: 'station'; station: Station }
type Props = {
  barriers: Barriers | null
  risk?: RiskMap | null
  stations?: Station[] | null
  plan: Plan | null
  choice?: Choice
  layers?: Layers
  start: LngLat | null
  destination: LngLat | null
  onPoint: (point: LngLat) => void
  onViewport: (bbox: string) => void
  onHover?: (hover: Hover | null) => void
}
const empty: FeatureCollection = { type: 'FeatureCollection', features: [] }
const allLayers: Layers = { risk: true, stations: true, barriers: true }
const LAYER_GROUPS: Record<keyof Layers, string[]> = {
  risk: ['risk-fill', 'risk-outline'],
  stations: ['stations'],
  barriers: ['barrier-areas', 'barrier-outlines', 'barrier-points'],
}

export default function MapView(props: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapInstance | null>(null)
  const callbacks = useRef(props)
  const [readyMap, setReadyMap] = useState<MapInstance | null>(null)
  const [error, setError] = useState('')
  const choice = props.choice ?? 'accessible'
  const layers = props.layers ?? allLayers
  const route = useMemo(() => selectedLines(props.plan, choice), [props.plan, choice])

  useEffect(() => { callbacks.current = props }, [props])

  useEffect(() => {
    if (!container.current) return
    let cancelled = false
    let map: MapInstance
    try {
      map = new maplibregl.Map({
        container: container.current, center: [-79.383, 43.658], zoom: 13.2,
        minZoom: 9, maxZoom: 19, maxBounds: [[-79.75, 43.5], [-79, 44]],
        style: {
          version: 8,
          sources: { streets: {
            type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
          } },
          layers: [{ id: 'streets', type: 'raster', source: 'streets', paint: { 'raster-saturation': -0.85, 'raster-contrast': -0.1 } }],
        },
      })
    } catch {
      queueMicrotask(() => { if (!cancelled) setError('The map could not load. Search addresses to plan your trip; directions appear in the panel.') })
      return () => { cancelled = true }
    }
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl(), 'top-right')
    const viewport = () => {
      const bounds = map.getBounds()
      callbacks.current.onViewport([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()]
        .map((value) => value.toFixed(6)).join(','))
    }
    map.on('load', () => {
      for (const name of ['risk', 'barriers', 'stations', 'ideal', 'stairs', 'route']) {
        map.addSource(name, { type: 'geojson', data: empty })
      }
      map.addLayer({ id: 'risk-fill', type: 'fill', source: 'risk',
        paint: { 'fill-color': ['interpolate', ['linear'], ['get', 'risk'], ...RISK_STOPS.flat()],
          'fill-opacity': ['interpolate', ['linear'], ['get', 'risk'], 0, 0.06, 0.1, 0.3, 0.3, 0.45] } })
      map.addLayer({ id: 'risk-outline', type: 'line', source: 'risk',
        paint: { 'line-color': '#ffffff', 'line-width': 0.6, 'line-opacity': 0.6 } })
      map.addLayer({ id: 'barrier-areas', type: 'fill', source: 'barriers',
        filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': '#1d2433', 'fill-opacity': .35 } })
      map.addLayer({ id: 'barrier-outlines', type: 'line', source: 'barriers',
        filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'line-color': '#1d2433', 'line-width': 2, 'line-dasharray': [2, 1] } })
      map.addLayer({ id: 'barrier-points', type: 'circle', source: 'barriers',
        filter: ['==', ['geometry-type'], 'Point'],
        paint: { 'circle-radius': 6, 'circle-color': '#1d2433', 'circle-stroke-color': '#fff', 'circle-stroke-width': 2 } })
      map.addLayer({ id: 'ideal-line', type: 'line', source: 'ideal', layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#4b5568', 'line-width': 4, 'line-dasharray': [1.5, 1.5], 'line-opacity': .85 } })
      map.addLayer({ id: 'route-casing', type: 'line', source: 'route', filter: ['!=', ['get', 'kind'], 'gap'],
        layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': 10 } })
      map.addLayer({ id: 'route-street', type: 'line', source: 'route', filter: ['==', ['get', 'kind'], 'street'],
        layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#1d4fa3', 'line-width': 6 } })
      map.addLayer({ id: 'route-typical', type: 'line', source: 'route', filter: ['==', ['get', 'kind'], 'typical'],
        layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#4b5568', 'line-width': 6 } })
      map.addLayer({ id: 'route-ride', type: 'line', source: 'route', filter: ['==', ['get', 'kind'], 'ride'],
        layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': ['get', 'color'], 'line-width': 7 } })
      map.addLayer({ id: 'route-walk', type: 'line', source: 'route', filter: ['==', ['get', 'kind'], 'walk'],
        layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#1d4fa3', 'line-width': 5, 'line-dasharray': [0.6, 1.6] } })
      map.addLayer({ id: 'route-gap', type: 'line', source: 'route', filter: ['==', ['get', 'kind'], 'gap'],
        layout: { 'line-cap': 'round' }, paint: { 'line-color': '#c2410c', 'line-width': 5, 'line-dasharray': [0.8, 1.4] } })
      map.addLayer({ id: 'stairs-line', type: 'line', source: 'stairs', filter: ['==', ['geometry-type'], 'LineString'],
        paint: { 'line-color': '#b42318', 'line-width': 7 } })
      map.addLayer({ id: 'stairs-points', type: 'circle', source: 'stairs', filter: ['==', ['geometry-type'], 'Point'],
        paint: { 'circle-radius': 7, 'circle-color': '#b42318', 'circle-stroke-color': '#fff', 'circle-stroke-width': 2 } })
      map.addLayer({ id: 'stations', type: 'circle', source: 'stations',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, 4, 15, 8],
          'circle-color': ['match', ['get', 'status'], 'ok', '#1f7a4d', 'outage', '#c2410c', '#6b7280'],
          'circle-stroke-color': '#fff', 'circle-stroke-width': 2 } })
      setReadyMap(map)
      viewport()
    })
    map.on('moveend', viewport)
    map.on('click', (event) => callbacks.current.onPoint([event.lngLat.lng, event.lngLat.lat]))
    map.on('mousemove', 'risk-fill', (event) => {
      const cell = event.features?.[0]?.properties as RiskProperties | undefined
      if (cell) callbacks.current.onHover?.({ kind: 'risk', cell: { cell: cell.cell, risk: Number(cell.risk), reports_last_year: Number(cell.reports_last_year) } })
    })
    map.on('mousemove', 'stations', (event) => {
      const index = Number(event.features?.[0]?.properties?.index)
      const station = callbacks.current.stations?.[index]
      if (station) { map.getCanvas().style.cursor = 'pointer'; callbacks.current.onHover?.({ kind: 'station', station }) }
    })
    for (const id of ['risk-fill', 'stations']) {
      map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; callbacks.current.onHover?.(null) })
    }
    map.on('error', () => setError('Some map layers could not load. Address search and directions still work.'))
    return () => { cancelled = true; map.remove(); mapRef.current = null }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || readyMap !== map) return
    ;(map.getSource('risk') as GeoJSONSource).setData(props.risk || empty)
  }, [readyMap, props.risk])

  useEffect(() => {
    const map = mapRef.current
    if (!map || readyMap !== map) return
    ;(map.getSource('barriers') as GeoJSONSource).setData({ type: 'FeatureCollection', features: props.barriers?.features || [] })
  }, [readyMap, props.barriers])

  useEffect(() => {
    const map = mapRef.current
    if (!map || readyMap !== map) return
    ;(map.getSource('stations') as GeoJSONSource).setData({ type: 'FeatureCollection', features: (props.stations || []).map((station, index) => ({
      type: 'Feature', geometry: { type: 'Point', coordinates: station.coordinates },
      properties: { index, name: station.name, status: stationStatus(station) },
    })) })
  }, [readyMap, props.stations])

  useEffect(() => {
    const map = mapRef.current
    if (!map || readyMap !== map) return
    for (const [layer, ids] of Object.entries(LAYER_GROUPS) as [keyof Layers, string[]][]) {
      ids.forEach((id) => map.setLayoutProperty(id, 'visibility', layers[layer] ? 'visible' : 'none'))
    }
  }, [readyMap, layers])

  useEffect(() => {
    const map = mapRef.current
    if (!map || readyMap !== map) return
    const ideal = props.plan?.ideal
    ;(map.getSource('ideal') as GeoJSONSource).setData(ideal && choice !== 'ideal' ? line(ideal.geometry) : empty)
    ;(map.getSource('stairs') as GeoJSONSource).setData({ type: 'FeatureCollection', features: (ideal?.stairs ?? []).flatMap((stairs) => [
      line(stairs),
      { type: 'Feature', geometry: { type: 'Point', coordinates: stairs.coordinates[Math.floor(stairs.coordinates.length / 2)] }, properties: {} },
    ]) })
    ;(map.getSource('route') as GeoJSONSource).setData(route)
    const lines = [...route.features.map((feature) => feature.geometry), ...(ideal ? [ideal.geometry] : [])]
    if (lines.length) {
      const bounds = new maplibregl.LngLatBounds()
      lines.forEach((geometry) => geometry.coordinates.forEach((point) => bounds.extend([point[0], point[1]])))
      // Keep the route clear of the legend: bottom edge on phones, bottom-left corner on wider screens.
      const narrow = (container.current?.clientWidth ?? 0) < 600
      const padding = narrow ? { top: 60, right: 50, bottom: 120, left: 30 } : { top: 70, right: 70, bottom: 60, left: 360 }
      map.fitBounds(bounds, { padding, maxZoom: 17, duration: 400 })
    }
  }, [readyMap, props.plan, route, choice])

  useEffect(() => {
    const map = mapRef.current
    if (!map || readyMap !== map) return
    const markers = [props.start, props.destination].flatMap((point, index) => {
      if (!point) return []
      const element = document.createElement('div')
      element.className = `endpoint-marker endpoint-${index}`
      element.textContent = index === 0 ? 'A' : 'B'
      element.setAttribute('aria-label', index === 0 ? 'Start point' : 'Destination point')
      return [new maplibregl.Marker({ element }).setLngLat(point).addTo(map)]
    })
    return () => { markers.forEach((marker) => marker.remove()) }
  }, [readyMap, props.start, props.destination])

  return <>
    <div ref={container} className="map-canvas" role="region" aria-label="Toronto route map" />
    {error && <p className="map-notice" role="status">{error}</p>}
  </>
}
