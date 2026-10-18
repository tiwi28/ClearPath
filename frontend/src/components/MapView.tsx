import { useEffect, useMemo, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import type { GeoJSONSource, Map as MapInstance, StyleSpecification } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { FeatureCollection } from 'geojson'
import 'maplibre-gl/dist/maplibre-gl.css'
import elevatorWorkingUrl from '../assets/elevator-working.png'
import elevatorOutUrl from '../assets/elevator-out.png'
import elevatorNoneUrl from '../assets/elevator-none.png'
import { RISK_STOPS } from '../format'
import { line, selectedLines, stationStatus } from '../mapData'
import type { Barriers, Choice, Hazard, LngLat, Plan, RiskMap, RiskProperties, Station } from '../types'
import type { Position } from '../trip/sources'

maplibregl.setWorkerUrl(workerUrl)

// A calm vector basemap (no key). Set VITE_MAP_STYLE to https://tiles.openfreemap.org/styles/liberty for a more colourful one.
const MAP_STYLE: string = import.meta.env.VITE_MAP_STYLE || 'https://tiles.openfreemap.org/styles/positron'
// Used only if the vector style can't load, so the map is never blank.
const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: { streets: {
    type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
  } },
  layers: [{ id: 'streets', type: 'raster', source: 'streets', paint: { 'raster-saturation': -0.85, 'raster-contrast': -0.1 } }],
}

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
  /** While a trip runs: where the rider is, the part already travelled, and alerts on the route. */
  trip?: { position: Position | null; travelled: LngLat[]; hazards: Hazard[] } | null
}
const empty: FeatureCollection = { type: 'FeatureCollection', features: [] }
const allLayers: Layers = { risk: true, stations: true, barriers: true }
const LAYER_GROUPS: Record<keyof Layers, string[]> = {
  risk: ['risk-fill'],
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
  const trip = props.trip ?? null
  const onTrip = trip !== null
  const position = trip?.position ?? null
  const travelledLine = trip?.travelled
  const hazards = trip?.hazards

  useEffect(() => { callbacks.current = props }, [props])

  useEffect(() => {
    if (!container.current) return
    let cancelled = false
    let map: MapInstance
    try {
      map = new maplibregl.Map({
        container: container.current, center: [-79.383, 43.658], zoom: 13.2,
        minZoom: 9, maxZoom: 19, maxBounds: [[-79.75, 43.5], [-79, 44]], style: MAP_STYLE,
        attributionControl: { customAttribution: '<a href="https://icons8.com" target="_blank" rel="noreferrer">Icons by Icons8</a>' },
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
    const clearHoverOn = (id: string) => map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; callbacks.current.onHover?.(null) })
    const hoverStations = (id: string) => {
      map.on('mousemove', id, (event) => {
        const index = Number(event.features?.[0]?.properties?.index)
        const station = callbacks.current.stations?.[index]
        if (station) { map.getCanvas().style.cursor = 'pointer'; callbacks.current.onHover?.({ kind: 'station', station }) }
      })
      clearHoverOn(id)
    }
    let overlaysAdded = false
    let fellBack = false
    // 'style.load' rather than 'load', so the overlays also arrive after a fallback setStyle().
    map.on('style.load', () => {
      if (overlaysAdded) return
      overlaysAdded = true
      for (const name of ['risk', 'barriers', 'stations', 'ideal', 'stairs', 'route', 'trip-done', 'hazards']) {
        map.addSource(name, { type: 'geojson', data: empty })
      }
      // Area layers sit under the basemap's labels so street names stay readable; lines and points go on top.
      const labels = map.getStyle().layers.find((layer) => layer.type === 'symbol')?.id
      map.addLayer({ id: 'risk-fill', type: 'fill', source: 'risk',
        paint: { 'fill-color': ['interpolate', ['linear'], ['get', 'risk'], ...RISK_STOPS.flat()],
          'fill-opacity': ['interpolate', ['linear'], ['get', 'risk'], 0, 0.04, 0.1, 0.2, 0.3, 0.5] } }, labels)
      map.addLayer({ id: 'barrier-areas', type: 'fill', source: 'barriers',
        filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': '#262626', 'fill-opacity': .35 } }, labels)
      map.addLayer({ id: 'barrier-outlines', type: 'line', source: 'barriers',
        filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'line-color': '#262626', 'line-width': 2, 'line-dasharray': [2, 1] } }, labels)
      map.addLayer({ id: 'barrier-points', type: 'circle', source: 'barriers',
        filter: ['==', ['geometry-type'], 'Point'],
        paint: { 'circle-radius': 6, 'circle-color': '#262626', 'circle-stroke-color': '#f5c400', 'circle-stroke-width': 2 } })
      map.addLayer({ id: 'ideal-line', type: 'line', source: 'ideal', layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#5a5852', 'line-width': 4, 'line-dasharray': [1.5, 1.5], 'line-opacity': .85 } })
      map.addLayer({ id: 'route-casing', type: 'line', source: 'route', filter: ['!=', ['get', 'kind'], 'gap'],
        layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': 10 } })
      map.addLayer({ id: 'route-street', type: 'line', source: 'route', filter: ['==', ['get', 'kind'], 'street'],
        layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#1d4fa3', 'line-width': 6 } })
      map.addLayer({ id: 'route-typical', type: 'line', source: 'route', filter: ['==', ['get', 'kind'], 'typical'],
        layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#5a5852', 'line-width': 6 } })
      map.addLayer({ id: 'route-ride', type: 'line', source: 'route', filter: ['==', ['get', 'kind'], 'ride'],
        layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': ['get', 'color'], 'line-width': 7 } })
      map.addLayer({ id: 'route-walk', type: 'line', source: 'route', filter: ['==', ['get', 'kind'], 'walk'],
        layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#1d4fa3', 'line-width': 5, 'line-dasharray': [0.6, 1.6] } })
      map.addLayer({ id: 'route-gap', type: 'line', source: 'route', filter: ['==', ['get', 'kind'], 'gap'],
        layout: { 'line-cap': 'round' }, paint: { 'line-color': '#c25e00', 'line-width': 5, 'line-dasharray': [0.8, 1.4] } })
      map.addLayer({ id: 'stairs-line', type: 'line', source: 'stairs', filter: ['==', ['geometry-type'], 'LineString'],
        paint: { 'line-color': '#b42318', 'line-width': 7 } })
      map.addLayer({ id: 'stairs-points', type: 'circle', source: 'stairs', filter: ['==', ['geometry-type'], 'Point'],
        paint: { 'circle-radius': 7, 'circle-color': '#b42318', 'circle-stroke-color': '#fff', 'circle-stroke-width': 2 } })
      // Station icons: green elevator working, red elevator out, grey no elevator. Added once the images load.
      void Promise.all([elevatorWorkingUrl, elevatorOutUrl, elevatorNoneUrl].map((url) => map.loadImage(url))).then(([working, out, none]) => {
        if (cancelled || map.getLayer('stations')) return
        map.addImage('elevator-ok', working.data, { pixelRatio: 2 })
        map.addImage('elevator-outage', out.data, { pixelRatio: 2 })
        map.addImage('elevator-none', none.data, { pixelRatio: 2 })
        map.addLayer({ id: 'stations', type: 'symbol', source: 'stations', minzoom: 13,
          layout: { 'icon-image': ['match', ['get', 'status'], 'outage', 'elevator-outage', 'none', 'elevator-none', 'elevator-ok'],
            'icon-size': ['interpolate', ['linear'], ['zoom'], 13, 0.4, 16, 0.6],
            'icon-allow-overlap': true, 'icon-ignore-placement': true,
            visibility: callbacks.current.layers?.stations === false ? 'none' : 'visible' } }, 'trip-done')
        hoverStations('stations')
      }).catch(() => setError('Station icons could not load. Address search and directions still work.'))
      map.addLayer({ id: 'trip-done', type: 'line', source: 'trip-done', layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#9a978f', 'line-width': 6 } })
      map.addLayer({ id: 'hazards', type: 'circle', source: 'hazards',
        paint: { 'circle-radius': 8, 'circle-stroke-width': 3, 'circle-stroke-color': '#262626',
          'circle-color': ['match', ['get', 'severity'], 'blocker', '#b42318', 'warning', '#c25e00', '#f5c400'] } })
      setReadyMap(map)
      viewport()
    })
    map.on('moveend', viewport)
    map.on('click', (event) => callbacks.current.onPoint([event.lngLat.lng, event.lngLat.lat]))
    map.on('mousemove', 'risk-fill', (event) => {
      const cell = event.features?.[0]?.properties as RiskProperties | undefined
      if (cell) callbacks.current.onHover?.({ kind: 'risk', cell: { cell: cell.cell, risk: Number(cell.risk), reports_last_year: Number(cell.reports_last_year) } })
    })
    clearHoverOn('risk-fill')
    map.on('error', () => {
      if (!overlaysAdded && !fellBack) { fellBack = true; map.setStyle(FALLBACK_STYLE); return }
      setError('Some map layers could not load. Address search and directions still work.')
    })
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
      ids.forEach((id) => { if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', layers[layer] ? 'visible' : 'none') })
    }
  }, [readyMap, layers])

  useEffect(() => {
    const map = mapRef.current
    if (!map || readyMap !== map) return
    const ideal = props.plan?.ideal
    ;(map.getSource('ideal') as GeoJSONSource).setData(ideal && choice !== 'ideal' && !onTrip ? line(ideal.geometry) : empty)
    ;(map.getSource('stairs') as GeoJSONSource).setData({ type: 'FeatureCollection', features: (ideal?.stairs ?? []).flatMap((stairs) => [
      line(stairs),
      { type: 'Feature', geometry: { type: 'Point', coordinates: stairs.coordinates[Math.floor(stairs.coordinates.length / 2)] }, properties: {} },
    ]) })
    ;(map.getSource('route') as GeoJSONSource).setData(route)
    const lines = [...route.features.map((feature) => feature.geometry), ...(ideal ? [ideal.geometry] : [])]
    if (lines.length && !onTrip) {
      const bounds = new maplibregl.LngLatBounds()
      lines.forEach((geometry) => geometry.coordinates.forEach((point) => bounds.extend([point[0], point[1]])))
      // Keep the route clear of the legend: bottom edge on phones, bottom-left corner on wider screens.
      const narrow = (container.current?.clientWidth ?? 0) < 600
      const padding = narrow ? { top: 60, right: 50, bottom: 120, left: 30 } : { top: 70, right: 70, bottom: 60, left: 400 }
      map.fitBounds(bounds, { padding, maxZoom: 17, duration: 400 })
    }
  }, [readyMap, props.plan, route, choice, onTrip])

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

  useEffect(() => {
    const map = mapRef.current
    if (!map || readyMap !== map) return
    ;(map.getSource('trip-done') as GeoJSONSource).setData(travelledLine && travelledLine.length > 1
      ? { type: 'FeatureCollection', features: [line({ type: 'LineString', coordinates: travelledLine })] } : empty)
  }, [readyMap, travelledLine])

  // Alerts change about once a minute, so they are not redrawn on every position update.
  useEffect(() => {
    const map = mapRef.current
    if (!map || readyMap !== map) return
    ;(map.getSource('hazards') as GeoJSONSource).setData({ type: 'FeatureCollection', features: (hazards ?? []).map((hazard) => ({
      type: 'Feature', geometry: { type: 'Point', coordinates: hazard.lnglat }, properties: { severity: hazard.severity, label: hazard.label },
    })) })
  }, [readyMap, hazards])

  // The rider's dot, with a pointer for the direction of travel.
  const rider = useRef<maplibregl.Marker | null>(null)
  useEffect(() => {
    const map = mapRef.current
    if (!map || readyMap !== map || !position) { rider.current?.remove(); rider.current = null; return }
    if (!rider.current) {
      const element = document.createElement('div')
      element.className = 'rider-dot'
      element.setAttribute('aria-label', 'Your position')
      rider.current = new maplibregl.Marker({ element, rotationAlignment: 'map' }).setLngLat(position.lnglat).addTo(map)
    }
    rider.current.setLngLat(position.lnglat).setRotation(position.heading ?? 0)
  }, [readyMap, position])
  useEffect(() => () => { rider.current?.remove(); rider.current = null }, [])

  // Follow the rider, turning the map gently with the direction of travel; level it again when the trip ends.
  const lastMove = useRef(0)
  useEffect(() => {
    const map = mapRef.current
    if (!map || readyMap !== map) return
    if (!onTrip) { if (map.getBearing() !== 0) map.easeTo({ bearing: 0, duration: 500 }); return }
    if (!position || Date.now() - lastMove.current < 900) return
    lastMove.current = Date.now()
    map.easeTo({ center: position.lnglat, zoom: Math.max(map.getZoom(), 16.5), bearing: position.heading ?? map.getBearing(),
      duration: 800, padding: { top: 0, bottom: 0, left: 0, right: 0 } })
  }, [readyMap, onTrip, position])

  return <>
    <div ref={container} className="map-canvas" role="region" aria-label="Toronto route map" />
    {error && <p className="map-notice" role="status">{error}</p>}
  </>
}
