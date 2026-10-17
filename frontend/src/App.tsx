import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { ApiError, getBarriers, getPlan, getRisk, getStations } from './api'
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

function message(error: unknown) { return error instanceof Error ? error.message : String(error) }

function loadPreferences(): Preferences {
  try { return { ...defaults, ...JSON.parse(localStorage.getItem(PREFERENCES_KEY) || '{}') } } catch { return defaults }
}

export default function App() {
  const [step, setStep] = useState<StepName>('Where')
  const [start, setStart] = useState<Field>({ text: '', point: null })
  const [destination, setDestination] = useState<Field>({ text: '', point: null })
  const [target, setTarget] = useState<Target>('start')
  const [preferences, setPreferences] = useState<Preferences>(loadPreferences)
  const [day, setDay] = useState(() => forecastDays()[0].value)
  const [layers, setLayers] = useState<Layers>({ risk: true, stations: true, barriers: false })
  const [bbox, setBbox] = useState('-79.40,43.64,-79.36,43.67')
  const [refresh, setRefresh] = useState(0)
  const [barriers, setBarriers] = useState<Barriers | null>(null)
  const [risk, setRisk] = useState<RiskMap | null>(null)
  const [riskError, setRiskError] = useState('')
  const [stations, setStations] = useState<Station[] | null>(null)
  const [hover, setHover] = useState<Hover | null>(null)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [choice, setChoice] = useState<Choice>('accessible')
  const [response, setResponse] = useState<unknown>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const requestId = useRef(0)
  const controller = useRef<AbortController | null>(null)
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
  }, [bbox, refresh])
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
  }, [refresh])
  useEffect(() => () => { controller.current?.abort(); requestId.current += 1 }, [])

  function clearPlan() {
    controller.current?.abort()
    requestId.current += 1
    setPlan(null); setResponse(null); setError(''); setLoading(false)
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
        setPlan(body); setResponse(body)
        setChoice(body.accessible ? 'accessible' : body.transit.length ? 'transit-0' : 'ideal')
      }
    } catch (failure) {
      if (id === requestId.current && !pending.signal.aborted) {
        setError(message(failure))
        setResponse(failure instanceof ApiError ? failure.body : { error: message(failure) })
      }
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }

  function placePoint(point: LngLat) {
    if (step !== 'Where') return  // the map only sets points while choosing them
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

  return <main className="app">
    <nav className="rail" aria-label="Trip planner steps">
      <span className="rail-brand">
        <img className="rail-icon" src={iconUrl} alt="ClearPath" width="512" height="512" />
        <img className="rail-logo" src={logoUrl} alt="ClearPath" width="1322" height="368" />
      </span>
      <ol className="stepper">
        {STEPS.map((name, index) => <li key={name}>
          <button type="button" className={`rail-step${index === stepIndex ? ' current' : index < stepIndex ? ' done' : ''}`}
            aria-current={index === stepIndex ? 'step' : undefined} disabled={!reachable[name] && index !== stepIndex}
            onClick={() => goTo(name)}>
            <span className="rail-number">{index + 1}</span>
            <span className="rail-label">{name}</span>
            <span className="visually-hidden">: {TITLES[name].text}</span>
          </button>
        </li>)}
      </ol>
    </nav>

    <section className="panel" aria-label="Trip planner">
      <header className={`band${loading ? ' band-loading' : ''}`}>
        <span className="band-domes" aria-hidden="true" />
        <h1 className="visually-hidden">ClearPath</h1>
        <h2 id={TITLES[step].id}>{TITLES[step].text}</h2>
      </header>
      {step === 'Where' && <p className="intro">Toronto routes for wheelchairs, walkers and limited stamina, checked for stairs, station elevators and likely sidewalk barriers.</p>}

      {step === 'Where' && <WhereStep start={start} destination={destination} target={target}
        onStart={(field) => { clearPlan(); setStart(field) }} onDestination={(field) => { clearPlan(); setDestination(field) }}
        onTarget={setTarget} onNext={() => setStep('How')} />}
      {step === 'How' && <ProfileStep profile={preferences.profile} includeTransit={preferences.includeTransit} avoidRisk={preferences.avoidRisk}
        onProfile={(profile) => setPreferences({ ...preferences, profile })}
        onIncludeTransit={(includeTransit) => setPreferences({ ...preferences, includeTransit })}
        onAvoidRisk={(avoidRisk) => setPreferences({ ...preferences, avoidRisk })}
        onBack={() => setStep('Where')} onNext={() => void findRoutes()} />}
      {step === 'Options' && <OptionsStep plan={plan} loading={loading} error={error} choice={choice}
        fromLabel={start.text || 'Start'} toLabel={destination.text || 'Destination'} onChoice={setChoice}
        onEditTrip={() => { clearPlan(); setStep('Where') }} onEditProfile={() => { clearPlan(); setStep('How') }} />}

      <details className="developer">
        <summary>Developer details</summary>
        <div className="developer-body">
          <div className="buttons">
            <button type="button" onClick={() => setRefresh((value) => value + 1)}>Refresh barriers and stations</button>
            <span>{barriers?.features.length ?? 0} barriers in view from {barriers?.data_source || 'unavailable source'}</span>
          </div>
          {risk && <p>Forecast model: ROC-AUC {risk.model.roc_auc}, 311 reports through {risk.reports_through} ({risk.model.lag_days}-day lag), weather from {risk.weather_source}.</p>}
          <h3>POST /plan request</h3>
          <pre aria-label="Request JSON">{JSON.stringify(planRequest, null, 2)}</pre>
          <h3>Plan response</h3>
          <pre aria-label="Response JSON">{response ? JSON.stringify(response, null, 2) : 'No response yet.'}</pre>
          <h3>Barrier GeoJSON</h3>
          <pre aria-label="Barrier JSON">{barriers ? JSON.stringify(barriers, null, 2) : 'No barrier response yet.'}</pre>
        </div>
      </details>
    </section>

    <section className="map-panel" aria-label="Map">
      <Suspense fallback={<div className="map-canvas map-loading">Loading map…</div>}>
        <MapView barriers={barriers} risk={risk} stations={stations} plan={plan} choice={choice} layers={layers}
          start={start.point} destination={destination.point} onViewport={setBbox} onPoint={placePoint} onHover={setHover} />
      </Suspense>
      <LayerPanel layers={layers} day={day} onLayers={setLayers} onDay={changeDay} />
      <Legend risk={risk} riskError={riskError} hover={hover} layers={layers} />
    </section>
  </main>
}
