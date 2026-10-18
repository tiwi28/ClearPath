import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { getBarriers, getPlan, getRisk, getStations } from './api'
import type { Field } from './components/AddressInput'
import { LayerPanel, Legend } from './components/MapOverlays'
import type { Hover, Layers } from './components/MapView'
import { forecastDays, pointText } from './format'
import OptionsStep from './steps/OptionsStep'
import ProfileStep from './steps/ProfileStep'
import WhereStep from './steps/WhereStep'
import type { Target } from './steps/WhereStep'
import type { Barriers, Choice, LngLat, Plan, ProfileName, RiskMap, Station } from './types'
import iconUrl from './assets/clearpath-icon-dark-bg.png'
import logoUrl from './assets/clearpath-logo-dark-bg.png'
import { travelled } from './trip/progress'
import { tripRoute } from './trip/route'
import type { TripRoute } from './trip/route'
import TripPanel from './trip/TripPanel'
import { useTrip } from './trip/useTrip'
import type { TripMode } from './trip/useTrip'
import WardList from './wards/WardList'
import WardPage from './wards/WardPage'
import './App.css'

const MapView = lazy(() => import('./components/MapView'))
const PREFERENCES_KEY = 'clearpath.preferences'
const STEPS = ['Where', 'How', 'Options'] as const
type StepName = typeof STEPS[number]
type Preferences = { profile: ProfileName; includeTransit: boolean; avoidRisk: boolean }
const TITLES: Record<StepName, { id: string; text: string }> = {
  Where: { id: 'where-title', text: 'Where are you going?' },
  How: { id: 'how-title', text: 'How do you get around?' },
  Options: { id: 'options-title', text: 'Your options' },
}
const defaults: Preferences = { profile: 'manual_wheelchair', includeTransit: true, avoidRisk: true }

type View = { name: 'trip' } | { name: 'wards'; ward: number | null }

/** #wards or #wards/10 opens the ward report cards; anything else is the trip planner. */
function readHash(): View {
  const match = window.location.hash.match(/^#wards(?:\/(\d{1,2}))?$/)
  return match ? { name: 'wards', ward: match[1] ? Number(match[1]) : null } : { name: 'trip' }
}

function message(error: unknown) { return error instanceof Error ? error.message : String(error) }

function loadPreferences(): Preferences {
  try { return { ...defaults, ...JSON.parse(localStorage.getItem(PREFERENCES_KEY) || '{}') } } catch { return defaults }
}

export default function App() {
  const [view, setView] = useState<View>(readHash)
  const [step, setStep] = useState<StepName>('Where')
  const [start, setStart] = useState<Field>({ text: '', point: null })
  const [destination, setDestination] = useState<Field>({ text: '', point: null })
  const [target, setTarget] = useState<Target>('start')
  const [preferences, setPreferences] = useState<Preferences>(loadPreferences)
  const [day, setDay] = useState(() => forecastDays()[0].value)
  const [layers, setLayers] = useState<Layers>({ risk: true, stations: true, barriers: false })
  const [bbox, setBbox] = useState('-79.40,43.64,-79.36,43.67')
  const [barriers, setBarriers] = useState<Barriers | null>(null)
  const [risk, setRisk] = useState<RiskMap | null>(null)
  const [riskError, setRiskError] = useState('')
  const [stations, setStations] = useState<Station[] | null>(null)
  const [hover, setHover] = useState<Hover | null>(null)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [choice, setChoice] = useState<Choice>('accessible')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [trip, setTrip] = useState<{ id: number; mode: TripMode; route: TripRoute } | null>(null)
  const [rerouting, setRerouting] = useState(false)
  const [rerouteError, setRerouteError] = useState('')
  const requestId = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const tripCount = useRef(0)
  const rerouteRun = useRef<AbortController | null>(null)
  const planRequest = start.point && destination.point ? {
    from: start.point, to: destination.point, profile: preferences.profile,
    include_transit: preferences.includeTransit, avoid_risk: preferences.avoidRisk, day,
  } : null

  useEffect(() => {
    try { localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences)) } catch { /* private mode */ }
  }, [preferences])
  useEffect(() => {
    const pending = new AbortController()
    getBarriers(bbox, pending.signal).then((body) => { if (!pending.signal.aborted) setBarriers(body) }).catch(() => {})
    return () => pending.abort()
  }, [bbox])
  useEffect(() => {
    const pending = new AbortController()
    getRisk(day, pending.signal).then((body) => {
      if (!pending.signal.aborted) { setRisk(body); setRiskError('') }
    }).catch((failure) => {
      if (!pending.signal.aborted) { setRisk(null); setRiskError(message(failure)) }
    })
    return () => pending.abort()
  }, [day])
  useEffect(() => {
    const pending = new AbortController()
    getStations(pending.signal).then((body) => { if (!pending.signal.aborted) setStations(body.stations) }).catch(() => {})
    return () => pending.abort()
  }, [])
  useEffect(() => () => { controller.current?.abort(); requestId.current += 1 }, [])
  useEffect(() => {
    const sync = () => setView(readHash())
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  const showWard = useCallback((id: number | null) => { window.location.hash = id === null ? 'wards' : `wards/${id}` }, [])

  function clearPlan() {
    controller.current?.abort()
    requestId.current += 1
    setPlan(null); setError(''); setLoading(false)
  }

  async function findRoutes(forDay = day) {
    clearPlan()
    setStep('Options')
    if (!start.point || !destination.point) { setStep('Where'); return }
    const pending = new AbortController()
    controller.current = pending
    const id = requestId.current
    setLoading(true)
    try {
      const body = await getPlan({ from: start.point, to: destination.point, profile: preferences.profile,
        include_transit: preferences.includeTransit, avoid_risk: preferences.avoidRisk, day: forDay }, pending.signal)
      if (id === requestId.current && !pending.signal.aborted) {
        setPlan(body)
        setChoice(body.accessible ? 'accessible' : body.transit.length ? 'transit-0' : 'ideal')
      }
    } catch (failure) {
      if (id === requestId.current && !pending.signal.aborted) {
        setError(message(failure))
      }
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }

  function cancelReroute() {
    rerouteRun.current?.abort()
    rerouteRun.current = null
    setRerouting(false); setRerouteError('')
  }

  function startTrip(mode: TripMode) {
    const route = plan && tripRoute(plan, choice, destination.text || 'your destination')
    if (!route) {
      setError("Turn-by-turn isn't available for this option. Try another option, or follow the directions above.")
      return
    }
    cancelReroute(); setError('')
    tripCount.current += 1
    setTrip({ id: tripCount.current, mode, route })
  }

  function endTrip() {
    cancelReroute()
    setTrip(null)
  }

  // Plan again from where the rider is now, keeping the kind of option they chose. Resolves to whether
  // a new route was found. One re-plan at a time; ending the trip cancels it, so a late answer changes nothing.
  const reroute = useCallback(async (from: LngLat): Promise<boolean> => {
    if (!trip || !destination.point || rerouteRun.current) return false
    const run = new AbortController()
    rerouteRun.current = run
    setRerouting(true); setRerouteError('')
    try {
      const next = await getPlan({ from, to: destination.point, profile: preferences.profile,
        include_transit: preferences.includeTransit, avoid_risk: preferences.avoidRisk, day }, run.signal)
      if (rerouteRun.current !== run) return false
      const kind: Choice = trip.route.choice.startsWith('transit-') && next.transit.length ? 'transit-0'
        : trip.route.choice === 'ideal' && next.ideal ? 'ideal' : next.accessible ? 'accessible' : next.transit.length ? 'transit-0' : 'ideal'
      const route = tripRoute(next, kind, trip.route.destination)
      if (!route) throw new Error('No new route was found from here. Head back toward the blue line.')
      setPlan(next); setChoice(kind)
      setStart({ text: 'Your location', point: from })
      setTrip((current) => current && current.id === trip.id ? { ...current, route } : current)
      return true
    } catch (failure) {
      if (rerouteRun.current === run) setRerouteError(message(failure))
      return false
    } finally {
      if (rerouteRun.current === run) { rerouteRun.current = null; setRerouting(false) }
    }
  }, [trip, destination.point, preferences, day])

  const live = useTrip({ tripId: trip?.id ?? 0, route: trip?.route ?? null, mode: trip?.mode ?? 'sim', profile: preferences.profile, day, onReroute: reroute })

  function placePoint(point: LngLat) {
    if (step !== 'Where' || trip) return  // the map only sets points while choosing them
    const field = { text: pointText(point), point }
    if (target === 'start') { setStart(field); setTarget('destination') }
    else setDestination(field)
  }

  function changeDay(value: string) {
    setDay(value)
    if (step === 'Options' && planRequest) void findRoutes(value)
  }

  const stepIndex = STEPS.indexOf(step)
  const reachable: Record<StepName, boolean> = { Where: true, How: Boolean(planRequest), Options: Boolean(plan) }

  function goTo(name: StepName) {
    if (name === step || !reachable[name]) return
    if (name !== 'Options') clearPlan()
    setStep(name)
  }

  const wards = view.name === 'wards'

  return <main className={`app${wards ? ' app-wards' : ''}${trip ? ' app-trip' : ''}`}>
    <nav className="rail" aria-label="ClearPath">
      <span className="rail-brand">
        <img className="rail-icon" src={iconUrl} alt="ClearPath" width="512" height="512" />
        <img className="rail-logo" src={logoUrl} alt="ClearPath" width="1322" height="368" />
      </span>
      <ul className="views">
        <li><button type="button" className={`view-tab${wards ? '' : ' current'}`} aria-current={wards ? undefined : 'page'}
          onClick={() => { if (wards) window.location.hash = '' }}>
          Trip<span className="visually-hidden">: plan a trip</span></button></li>
        <li><button type="button" className={`view-tab${wards ? ' current' : ''}`} aria-current={wards ? 'page' : undefined}
          onClick={() => { if (!wards) showWard(null) }}>
          Wards<span className="visually-hidden">: ward report cards</span></button></li>
      </ul>
      {!wards && <ol className="stepper" aria-label="Trip planner steps">
        {STEPS.map((name, index) => <li key={name}>
          <button type="button" className={`rail-step${index === stepIndex ? ' current' : index < stepIndex ? ' done' : ''}`}
            aria-current={index === stepIndex ? 'step' : undefined} disabled={Boolean(trip) || (!reachable[name] && index !== stepIndex)}
            onClick={() => goTo(name)}>
            <span className="rail-number">{index + 1}</span>
            <span className="rail-label">{name}</span>
            <span className="visually-hidden">: {TITLES[name].text}</span>
          </button>
        </li>)}
      </ol>}
    </nav>

    {wards && <section className="panel" aria-label="Wards">
      <header className="band">
        <span className="band-domes" aria-hidden="true" />
        <h1 className="visually-hidden">ClearPath</h1>
        <h2>Ward report cards</h2>
      </header>
      <WardList selected={view.ward} onSelect={showWard} />
    </section>}
    {wards && <WardPage key={view.ward ?? 'none'} wardId={view.ward} />}

    {!wards && <section className="panel" aria-label="Trip planner">
      <header className={`band${loading ? ' band-loading' : ''}`}>
        <span className="band-domes" aria-hidden="true" />
        <h1 className="visually-hidden">ClearPath</h1>
        {trip ? <h2 id="trip-title">On your way</h2> : <h2 id={TITLES[step].id}>{TITLES[step].text}</h2>}
      </header>
      {trip && <TripPanel trip={live} route={trip.route} mode={trip.mode} rerouting={rerouting} rerouteError={rerouteError}
        onFindWayAround={() => { if (live.position) void reroute(live.position.lnglat) }}
        onEnd={endTrip}
        onDone={() => {
          endTrip(); clearPlan()
          setStart({ text: '', point: null }); setDestination({ text: '', point: null }); setTarget('start'); setStep('Where')
        }} />}
      {!trip && step === 'Where' && <p className="intro">Toronto routes for wheelchairs, walkers and limited stamina, checked for stairs, station elevators and likely sidewalk barriers.</p>}

      {!trip && step === 'Where' && <WhereStep start={start} destination={destination} target={target}
        onStart={(field) => { clearPlan(); setStart(field) }} onDestination={(field) => { clearPlan(); setDestination(field) }}
        onTarget={setTarget} onNext={() => setStep('How')} />}
      {!trip && step === 'How' && <ProfileStep profile={preferences.profile} includeTransit={preferences.includeTransit} avoidRisk={preferences.avoidRisk}
        onProfile={(profile) => setPreferences({ ...preferences, profile })}
        onIncludeTransit={(includeTransit) => setPreferences({ ...preferences, includeTransit })}
        onAvoidRisk={(avoidRisk) => setPreferences({ ...preferences, avoidRisk })}
        onBack={() => setStep('Where')} onNext={() => void findRoutes()} />}
      {!trip && step === 'Options' && <OptionsStep plan={plan} loading={loading} error={error} choice={choice}
        fromLabel={start.text || 'Start'} toLabel={destination.text || 'Destination'} onChoice={setChoice} onStart={startTrip}
        onEditTrip={() => { clearPlan(); setStep('Where') }} onEditProfile={() => { clearPlan(); setStep('How') }} />}
    </section>}

    {!wards && <section className="map-panel" aria-label="Map">
      <Suspense fallback={<div className="map-canvas map-loading">Loading map…</div>}>
        <MapView barriers={barriers} risk={risk} stations={stations} plan={plan} choice={choice} layers={layers}
          start={start.point} destination={destination.point} onViewport={setBbox} onPoint={placePoint} onHover={setHover}
          trip={trip ? { position: live.position, travelled: live.progress ? travelled(trip.route.track, live.progress.along) : [],
            hazards: live.hazards } : null} />
      </Suspense>
      <LayerPanel layers={layers} day={day} onLayers={setLayers} onDay={changeDay} />
      {!trip && <Legend risk={risk} riskError={riskError} hover={hover} layers={layers} />}
    </section>}
  </main>
}
