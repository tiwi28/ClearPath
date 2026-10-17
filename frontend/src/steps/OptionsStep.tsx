import type { ReactNode } from 'react'
import { formatDistance, formatDuration, formatTime, percent, PROFILES } from '../format'
import type { AccessibleRoute, Choice, Plan, RouteOption, TransitLeg, TransitOption } from '../types'

type Props = {
  plan: Plan | null
  loading: boolean
  error: string
  choice: Choice
  fromLabel: string
  toLabel: string
  onChoice: (choice: Choice) => void
  onEditTrip: () => void
  onEditProfile: () => void
  onStart: (mode: 'gps' | 'sim') => void
}

function legLabel(leg: TransitLeg) {
  if (leg.mode === 'WALK') return `Walk ${formatDuration(leg.duration_s)}`
  if (leg.mode === 'SUBWAY' || (leg.mode === 'TRAM' && ['5', '6'].includes(leg.line ?? ''))) return `Line ${leg.line}`
  if (leg.mode === 'TRAM') return `Streetcar ${leg.line}`
  if (leg.mode === 'BUS') return `Bus ${leg.line}`
  return leg.line ? `${leg.mode.toLowerCase()} ${leg.line}` : leg.mode.toLowerCase()
}

function place(name: string) {
  return name === 'START' ? 'your start' : name === 'END' ? 'your destination' : name
}

function Exposure({ route }: { route: RouteOption }) {
  if (!route.risk) return null
  const share = route.risk.high_risk_share
  return <div className="exposure">
    <div className="exposure-track" role="img" aria-label={`${percent(share)} of this route is in areas likely to have sidewalk barriers`}>
      <div className="exposure-fill" style={{ width: `${Math.max(share * 100, share ? 3 : 0)}%` }} />
    </div>
    <p className="exposure-caption">{share
      ? <><strong>{percent(share)}</strong> in areas likely to have sidewalk barriers</>
      : 'No areas with a high chance of sidewalk barriers'}</p>
  </div>
}

function AccessibleCard({ route, plan, label }: { route: AccessibleRoute; plan: Plan; label: string }) {
  const ideal = plan.ideal
  const extra = ideal ? route.distance_m - ideal.distance_m : 0
  const gap = route.unverified.reduce((total, item) => total + item.length_m, 0)
  return <>
    <span className="card-title">{label}</span>
    <span className="card-figures">{formatDuration(route.duration_s)}<span className="card-sub">{formatDistance(route.distance_m)}</span></span>
    {ideal && ideal.stairs.length > 0 && <span className="card-win">
      Avoids {ideal.stairs.length === 1 ? 'a set of stairs' : `${ideal.stairs.length} sets of stairs`} on the typical route
      {Math.abs(extra) >= 20 ? ` for ${extra > 0 ? formatDistance(extra) + ' more' : formatDistance(-extra) + ' less'}` : ''}.
    </span>}
    {route.risk_avoided && route.standard && <span className="card-win">
      Steers around likely sidewalk barriers for {formatDistance(Math.max(0, route.distance_m - route.standard.distance_m))} more.
    </span>}
    {gap > 0 && <span className="card-caution">Last {formatDistance(gap)} not confirmed free of stairs. Check the entrance.</span>}
    <Exposure route={route} />
  </>
}

function usesStations(option: TransitOption) {
  return option.legs.some((leg) => leg.mode === 'SUBWAY' || (leg.mode === 'TRAM' && ['5', '6'].includes(leg.line ?? '')))
}

function TransitCard({ option }: { option: TransitOption }) {
  return <>
    <span className="card-title">TTC, arrive {formatTime(option.end)}</span>
    <span className="card-figures">{formatDuration(option.duration_s)}<span className="card-sub">{formatDistance(option.walk_m)} walking or rolling</span></span>
    <span className="legs">
      {option.legs.filter((leg) => leg.mode !== 'WALK' || leg.duration_s >= 60).map((leg, index) => <span key={index}
        className={`leg leg-${leg.mode === 'WALK' ? 'walk' : 'ride'}`}
        style={leg.mode === 'WALK' ? undefined : { borderColor: leg.color || '#da251d' }}>{legLabel(leg)}</span>)}
    </span>
    {option.issues.length === 0
      ? <span className="badge badge-ok">{usesStations(option) ? 'Stations have working elevators' : 'Ramp-equipped buses and streetcars'}</span>
      : option.issues.map((issue) => <span key={issue.text} className={`badge badge-${issue.severity}`}>{issue.text}</span>)}
  </>
}

function TypicalCard({ ideal }: { ideal: RouteOption }) {
  return <>
    <span className="card-title">Typical route</span>
    <span className="card-figures">{formatDuration(ideal.duration_s)}<span className="card-sub">{formatDistance(ideal.distance_m)}</span></span>
    <span className={ideal.stairs.length ? 'card-caution' : 'card-sub'}>
      {ideal.stairs.length ? `What most map apps suggest. Uses stairs in ${ideal.stairs.length} ${ideal.stairs.length === 1 ? 'place' : 'places'}.`
        : 'What most map apps suggest. No stairs found, but curbs and slopes aren’t checked.'}
    </span>
  </>
}

function directionCount(plan: Plan, choice: Choice) {
  const count = choice.startsWith('transit-') ? plan.transit[Number(choice.split('-')[1])]?.legs.length
    : (choice === 'ideal' ? plan.ideal : plan.accessible)?.steps.length
  return count ? `, ${count} ${count === 1 ? 'step' : 'steps'}` : ''
}

function Directions({ plan, choice }: { plan: Plan; choice: Choice }) {
  if (choice.startsWith('transit-')) {
    const option = plan.transit[Number(choice.split('-')[1])]
    if (!option) return null
    return <ol>{option.legs.map((leg, index) => <li key={index}>
      {leg.mode === 'WALK'
        ? <span>Walk or roll {formatDistance(leg.distance_m)} to {place(leg.to_name)}</span>
        : <span>Take {legLabel(leg)}{leg.headsign ? ` (${leg.headsign})` : ''} from {leg.from_name} to {leg.to_name}</span>}
      <span className="step-distance">{formatTime(leg.start)}</span>
    </li>)}</ol>
  }
  const route = choice === 'ideal' ? plan.ideal : plan.accessible
  if (!route) return null
  return <ol>{route.steps.map((step, index) => <li key={index}>
    <span>{step.instruction}</span>
    {step.distance_m > 0 && <span className="step-distance">{formatDistance(step.distance_m)}</span>}
  </li>)}</ol>
}

export default function OptionsStep({ plan, loading, error, choice, fromLabel, toLabel, onChoice, onEditTrip, onEditProfile, onStart }: Props) {
  const profile = PROFILES.find((item) => item.value === plan?.profile)
  const cards: { id: Choice; body: ReactNode; tone?: string }[] = []
  if (plan?.accessible) cards.push({ id: 'accessible', body: <AccessibleCard route={plan.accessible} plan={plan} label="Accessible route" /> })
  plan?.transit.forEach((option, index) => cards.push({ id: `transit-${index}`, body: <TransitCard option={option} /> }))
  if (plan?.ideal) cards.push({ id: 'ideal', body: <TypicalCard ideal={plan.ideal} />, tone: 'typical' })
  const notes = [...new Set(plan?.warnings ?? [])]

  return <section className="step" aria-labelledby="options-title">
    <div className="trip-summary">
      <p><span className="summary-place">{fromLabel}</span> to <span className="summary-place">{toLabel}</span></p>
      <p className="summary-edit">
        <button type="button" className="link-button" onClick={onEditTrip}>Change trip</button>
        <button type="button" className="link-button" onClick={onEditProfile}>{profile ? profile.label : 'Change how you get around'}</button>
      </p>
    </div>

    {loading && <p className="loading" role="status">Checking street routes, stations and the barrier forecast…</p>}
    {error && <p className="error" role="alert">{error}</p>}

    {plan && !loading && <>
      <div className="option-list" role="radiogroup" aria-label="Route options">
        {cards.map((card) => <button key={card.id} type="button" role="radio" aria-checked={choice === card.id}
          className={`option-card${card.tone ? ` option-${card.tone}` : ''}${choice === card.id ? ' selected' : ''}`}
          onClick={() => onChoice(card.id)}>{card.body}</button>)}
      </div>
      <div className="start-trip">
        <button type="button" className="primary" onClick={() => onStart('gps')}>Start trip</button>
        <button type="button" className="secondary" onClick={() => onStart('sim')}>Simulate</button>
      </div>
      <details className="directions">
        <summary>Directions{directionCount(plan, choice)}</summary>
        <Directions plan={plan} choice={choice} />
      </details>
      {notes.length > 0 && <ul className="notes">{notes.map((note) => <li key={note}>{note}</li>)}</ul>}
    </>}
  </section>
}
