import { useEffect, useRef, useState } from 'react'
import type { LngLat } from '../types'
import { moveFrom, pointAt, strayDirection } from './progress'
import type { Track } from './progress'

/** One location reading, from the phone's GPS or from the simulator. */
export type Position = { lnglat: LngLat; heading: number | null; accuracy: number; time: number }

const TICK_MS = 250
const STRAY_M = 60       // a wrong turn leads this far from the route, then waits there for the re-route
const STRAY_TICKS = 3    // ...getting there in under a second at any speed
export const SIM_RATES = [1, 4, 10] as const
export type SimRate = typeof SIM_RATES[number]

/** Moves a dot along the route at the rider's pace, so a trip can be shown indoors. */
export function useSimulation(track: Track | null, speedMps: number, active: boolean) {
  // A reading belongs to the route it was made on, so a new trip never starts from the last trip's dot.
  const [reading, setReading] = useState<{ track: Track; position: Position } | null>(null)
  const position = reading && reading.track === track ? reading.position : null
  const [playing, setPlaying] = useState(true)
  const [rate, setRate] = useState<SimRate>(4)
  // "Take a wrong turn" walks the dot straight away from the route it was pressed on, so it is clearly
  // off course even when the route doubles back; a re-route puts the dot back on course.
  const [stray, setStray] = useState<{ track: Track; from: LngLat; angle: number } | null>(null)
  const straying = stray && stray.track === track ? stray : null
  const along = useRef(0)
  const strayed = useRef(0)

  // A new route (start, or after a re-route) starts again from its beginning.
  useEffect(() => { along.current = 0 }, [track])

  useEffect(() => {
    if (!active || !track || !playing) return
    const timer = setInterval(() => {
      if (straying) {
        strayed.current = Math.min(STRAY_M, strayed.current + STRAY_M / STRAY_TICKS)
        setReading({ track, position: { lnglat: moveFrom(straying.from, straying.angle, strayed.current), heading: straying.angle,
          accuracy: 5, time: Date.now() } })
        return
      }
      along.current = Math.min(track.total, along.current + speedMps * rate * TICK_MS / 1000)
      const { lnglat, heading } = pointAt(track, along.current)
      setReading({ track, position: { lnglat, heading, accuracy: 5, time: Date.now() } })
      if (along.current >= track.total) clearInterval(timer)  // arrived: stop updating
    }, TICK_MS)
    return () => clearInterval(timer)
  }, [active, track, playing, rate, speedMps, straying])

  function takeWrongTurn() {
    if (!track) return
    const from = pointAt(track, along.current).lnglat
    strayed.current = 0
    setStray({ track, from, angle: strayDirection(track, from, STRAY_M) })
  }

  return { position: active ? position : null, playing, setPlaying, rate, setRate, wrongTurn: straying !== null, takeWrongTurn }
}

/** The phone's own location, kept awake while the trip runs. `session` identifies the trip. */
export function useGeolocation(active: boolean, session: number) {
  const [reading, setReading] = useState<{ session: number; position: Position } | null>(null)
  const position = reading && reading.session === session ? reading.position : null
  const [error, setError] = useState('')

  useEffect(() => {
    if (!active) return
    if (!('geolocation' in navigator)) {
      queueMicrotask(() => setError('This browser can’t share your location. Use Simulate to preview the trip.'))
      return
    }
    const watch = navigator.geolocation.watchPosition(
      (fix) => {
        setError('')
        setReading({ session, position: { lnglat: [fix.coords.longitude, fix.coords.latitude], heading: fix.coords.heading,
          accuracy: fix.coords.accuracy, time: fix.timestamp } })
      },
      (failure) => setError(failure.code === failure.PERMISSION_DENIED
        ? 'Location access is blocked. Allow it in your browser settings, or use Simulate.'
        : 'Waiting for a location fix. Move to an open area if this takes long.'),
      { enableHighAccuracy: true, maximumAge: 2000, timeout: 20_000 },
    )
    let lock: { release: () => Promise<void> } | null = null
    const wakeLock = (navigator as Navigator & { wakeLock?: { request: (type: 'screen') => Promise<{ release: () => Promise<void> }> } }).wakeLock
    wakeLock?.request('screen').then((sentinel) => { lock = sentinel }).catch(() => {})
    return () => { navigator.geolocation.clearWatch(watch); void lock?.release().catch(() => {}) }
  }, [active, session])

  return { position: active ? position : null, error: active ? error : '' }
}
