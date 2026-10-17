import { useEffect, useRef, useState } from 'react'
import type { LngLat } from '../types'
import { offsetAt, pointAt } from './progress'
import type { Track } from './progress'

/** One location reading, from the phone's GPS or from the simulator. */
export type Position = { lnglat: LngLat; heading: number | null; accuracy: number; time: number }

const TICK_MS = 250
export const SIM_RATES = [1, 4, 10] as const
export type SimRate = typeof SIM_RATES[number]

/** Moves a dot along the route at the rider's pace, so a trip can be shown indoors. */
export function useSimulation(track: Track | null, speedMps: number, active: boolean) {
  const [position, setPosition] = useState<Position | null>(null)
  const [playing, setPlaying] = useState(true)
  const [rate, setRate] = useState<SimRate>(4)
  // "Take a wrong turn" applies to the route it was pressed on; a re-route puts the dot back on course.
  const [wrongTurnOn, setWrongTurnOn] = useState<Track | null>(null)
  const wrongTurn = wrongTurnOn !== null && wrongTurnOn === track
  const along = useRef(0)

  // A new route (start, or after a re-route) starts again from its beginning.
  useEffect(() => { along.current = 0 }, [track])

  useEffect(() => {
    if (!active || !track || !playing) return
    const timer = setInterval(() => {
      along.current = Math.min(track.total, along.current + speedMps * rate * TICK_MS / 1000)
      const { lnglat, heading } = pointAt(track, along.current)
      setPosition({ lnglat: wrongTurn ? offsetAt(track, along.current, 60) : lnglat, heading, accuracy: 5, time: Date.now() })
    }, TICK_MS)
    return () => clearInterval(timer)
  }, [active, track, playing, rate, speedMps, wrongTurn])

  return { position: active ? position : null, playing, setPlaying, rate, setRate, wrongTurn, takeWrongTurn: () => setWrongTurnOn(track) }
}

/** The phone's own location, kept awake while the trip runs. */
export function useGeolocation(active: boolean) {
  const [position, setPosition] = useState<Position | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!active) return
    if (!('geolocation' in navigator)) {
      queueMicrotask(() => setError('This browser can’t share your location. Use Simulate to preview the trip.'))
      return
    }
    const watch = navigator.geolocation.watchPosition(
      (reading) => {
        setError('')
        setPosition({ lnglat: [reading.coords.longitude, reading.coords.latitude], heading: reading.coords.heading,
          accuracy: reading.coords.accuracy, time: reading.timestamp })
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
  }, [active])

  return { position: active ? position : null, error: active ? error : '' }
}
