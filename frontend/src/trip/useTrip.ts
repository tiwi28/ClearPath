import { useEffect, useMemo, useRef, useState } from 'react'
import { getHazards, postReport } from '../api'
import type { Hazard, LngLat, ProfileName, ReportKind } from '../types'
import { arrived, formatMetres, offRouteCount, OFF_ROUTE_READINGS, project } from './progress'
import { stepAt } from './route'
import type { TripRoute } from './route'
import { useGeolocation, useSimulation } from './sources'

export type TripMode = 'gps' | 'sim'
const ANNOUNCE_M = 150   // alerts appear this far ahead
const ASK_AFTER_M = 20   // ask "was it blocked?" once this far past a spot
const ASK_UNTIL_M = 250  // ...and stop asking once well past it
const HAZARD_REFRESH_MS = 60_000
const DEVICE_KEY = 'clearpath.device'

export function deviceId(): string {
  try {
    const saved = localStorage.getItem(DEVICE_KEY)
    if (saved) return saved
    const created = crypto.randomUUID()
    localStorage.setItem(DEVICE_KEY, created)
    return created
  } catch { return 'anonymous-device' }
}

function speak(text: string, enabled: boolean) {
  if (!enabled || !('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  window.speechSynthesis.speak(new SpeechSynthesisUtterance(text))
}

type Options = {
  route: TripRoute | null
  mode: TripMode
  profile: ProfileName
  day: string | null
  onReroute: (from: LngLat) => void
}

export function useTrip({ route, mode, profile, day, onReroute }: Options) {
  const active = route !== null
  const speed = route ? Math.max(0.6, route.track.total / Math.max(route.duration_s, 1)) : 1
  const sim = useSimulation(route?.track ?? null, speed, active && mode === 'sim')
  const gps = useGeolocation(active && mode === 'gps')
  const position = mode === 'sim' ? sim.position : gps.position
  const [hazards, setHazards] = useState<Hazard[]>([])
  const [answered, setAnswered] = useState<Record<string, string>>({})
  const [sound, setSound] = useState(true)
  const [notice, setNotice] = useState('')
  const offCount = useRef(0)
  const rerouting = useRef(false)
  const spoken = useRef(new Set<string>())

  // Alerts ahead: fetched for each route, then refreshed so live feeds and rider reports stay current.
  useEffect(() => {
    if (!route) return
    const pending = new AbortController()
    const load = () => getHazards({
      route: { type: 'LineString', coordinates: route.track.coords }, day, stations: route.stations, unverified: route.unverified,
    }, pending.signal).then((list) => { if (!pending.signal.aborted) setHazards(list) }).catch(() => {})
    void load()
    const timer = setInterval(load, HAZARD_REFRESH_MS)
    rerouting.current = false
    offCount.current = 0
    return () => { pending.abort(); clearInterval(timer) }
  }, [route, day])

  const progress = useMemo(() => {
    if (!route || !position) return null
    const { along, off } = project(route.track, position.lnglat)
    const index = stepAt(route.steps, along)
    const remaining = Math.max(0, route.track.total - along)
    return {
      along, off, index, remaining,
      step: route.steps[index], next: route.steps[index + 1] ?? null,
      toTurn: Math.max(0, route.steps[index].end_m - along),
      eta: new Date(position.time + remaining / speed * 1000),
      share: route.track.total ? along / route.track.total : 0,
      arrived: arrived(route.track, along, position.lnglat),
    }
  }, [route, position, speed])

  const along = progress?.along ?? 0
  const ahead = hazards.filter((h) => h.at_m >= along - 5)
  const banner = ahead.find((h) => h.at_m - along <= ANNOUNCE_M) ?? null
  const prompt = hazards.find((h) => h.confirmable && !answered[h.id]
    && along - h.at_m >= ASK_AFTER_M && along - h.at_m <= ASK_UNTIL_M) ?? null

  // Off route for several readings in a row: plan again from here (once per route).
  useEffect(() => {
    if (!progress || !position || progress.arrived || rerouting.current) return
    offCount.current = offRouteCount(offCount.current, progress.off, mode === 'gps' ? position.accuracy : 0)
    if (offCount.current >= OFF_ROUTE_READINGS) {
      rerouting.current = true
      speak('Off route. Finding a new way.', sound)
      onReroute(position.lnglat)
    }
  }, [progress, position, mode, onReroute, sound])

  // Speak each new instruction and each alert once.
  useEffect(() => {
    if (!progress) return
    const key = `step-${progress.index}-${progress.step.instruction}`
    if (!spoken.current.has(key)) { spoken.current.add(key); speak(progress.step.instruction, sound) }
  }, [progress, sound])
  useEffect(() => {
    if (!banner || spoken.current.has(banner.id)) return
    spoken.current.add(banner.id)
    navigator.vibrate?.(banner.severity === 'blocker' ? [200, 100, 200] : 200)
    speak(`In ${formatMetres(banner.at_m - along)}: ${banner.label}`, sound)
  }, [banner, along, sound])

  async function send(kind: ReportKind, state: 'blocked' | 'clear', location: LngLat) {
    try {
      await postReport({ device_id: deviceId(), kind, state, profile, location })
      setNotice(state === 'clear' ? 'Thanks. We marked it clear for other riders.' : 'Thanks. Other riders will see this spot.')
    } catch (failure) {
      setNotice(failure instanceof Error ? failure.message : 'The report could not be sent.')
    }
  }

  function answer(hazard: Hazard, state: 'blocked' | 'clear' | 'skip') {
    setAnswered((previous) => ({ ...previous, [hazard.id]: state }))
    if (state === 'skip') return
    const kind: ReportKind = hazard.kind === 'closure' ? 'construction' : hazard.kind === 'elevator' ? 'elevator_out' : 'blocked_sidewalk'
    void send(kind, state, hazard.lnglat)
  }

  function report(kind: ReportKind) {
    if (position) void send(kind, 'blocked', position.lnglat)
  }

  return {
    position, progress, hazards, ahead, banner, prompt, answer, report, notice, dismissNotice: () => setNotice(''),
    sound, setSound, sim, gpsError: gps.error,
  }
}
