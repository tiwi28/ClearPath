import type { Hazard, ReportKind } from '../types'
import { formatMetres } from './progress'
import type { TripRoute, TripStep } from './route'
import { SIM_RATES } from './sources'
import type { TripMode, useTrip } from './useTrip'

// ORS turn types -> arrow rotation in degrees (0 = straight ahead).
const TURN_ANGLE: Record<number, number> = { 0: -90, 1: 90, 2: -135, 3: 135, 4: -45, 5: 45, 6: 0, 9: 180, 11: 0, 12: -30, 13: 30 }
const REPORT_KINDS: { kind: ReportKind; label: string }[] = [
  { kind: 'blocked_sidewalk', label: 'Sidewalk blocked' },
  { kind: 'snow_ice', label: 'Snow or ice' },
  { kind: 'construction', label: 'Construction' },
  { kind: 'elevator_out', label: 'Elevator out' },
  { kind: 'other', label: 'Something else' },
]
const BLOCKING = new Set(['barrier', 'rider_report', 'closure', 'elevator'])

function TurnIcon({ step }: { step: TripStep }) {
  if (step.ride) {
    return <span className="turn turn-ride" style={{ background: step.ride.color ?? 'var(--asphalt)' }} aria-hidden="true">
      <svg viewBox="0 0 24 24"><rect x="6" y="3" width="12" height="15" rx="3" /><path d="M8 21l2-3m6 3-2-3M6 11h12" /></svg>
    </span>
  }
  if (step.type === 10) {
    return <span className="turn" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 21s-6-6.2-6-11a6 6 0 0 1 12 0c0 4.8-6 11-6 11Z" /><circle cx="12" cy="10" r="2.2" /></svg></span>
  }
  const angle = TURN_ANGLE[step.type ?? 6] ?? 0
  return <span className="turn" aria-hidden="true">
    <svg viewBox="0 0 24 24" style={{ transform: `rotate(${angle}deg)` }}><path d="M12 20V5m-6 6 6-6 6 6" /></svg>
  </span>
}

type Trip = ReturnType<typeof useTrip>
type Props = {
  trip: Trip
  route: TripRoute
  mode: TripMode
  rerouting: boolean
  rerouteError: string
  onFindWayAround: () => void
  onEnd: () => void
  onDone: () => void
}

function AlertBanner({ hazard, distance, onFindWayAround }: { hazard: Hazard; distance: number; onFindWayAround: () => void }) {
  return <div className={`trip-alert trip-alert-${hazard.severity}`} role="alert">
    <p><b>{distance > 5 ? `In ${formatMetres(distance)}` : 'Here'}:</b> {hazard.label}</p>
    {BLOCKING.has(hazard.kind) && hazard.severity !== 'info' &&
      <button type="button" className="secondary" onClick={onFindWayAround}>Find a way around</button>}
  </div>
}

export default function TripPanel({ trip, route, mode, rerouting, rerouteError, onFindWayAround, onEnd, onDone }: Props) {
  const { progress, banner, prompt, sim } = trip

  if (progress?.arrived) {
    return <section className="step trip" aria-label="Trip">
      <div className="trip-now trip-arrived">
        <TurnIcon step={{ instruction: '', start_m: 0, end_m: 0, type: 10, ride: null }} />
        <div><p className="trip-distance">You've arrived</p><p className="trip-instruction">{route.destination}</p></div>
      </div>
      <p>Did anything on the way get in your way? Your report warns the next rider.</p>
      <ReportMenu onReport={trip.report} />
      {trip.notice && <p className="trip-notice" role="status">{trip.notice}</p>}
      <button type="button" className="primary" onClick={onDone}>Done</button>
    </section>
  }

  return <section className="step trip" aria-label="Trip">
    {!progress && <div className="trip-now trip-waiting">
      <p className="trip-instruction">{mode === 'gps' ? 'Waiting for your location…' : 'Starting the simulation…'}</p>
      {trip.gpsError && <p className="trip-gps-error">{trip.gpsError}</p>}
    </div>}

    {progress && <div className="trip-now" aria-live="polite">
      <TurnIcon step={progress.step} />
      <div>
        <p className="trip-distance">{progress.step.ride ? 'Ride' : progress.toTurn < 10 ? 'Now' : formatMetres(progress.toTurn)}</p>
        <p className="trip-instruction">{progress.step.instruction}</p>
      </div>
    </div>}
    {progress?.next && <p className="trip-then">Then: {progress.next.instruction}</p>}

    {rerouting && <p className="trip-status" role="status">Off route. Finding a new way from here…</p>}
    {rerouteError && <p className="error" role="alert">{rerouteError}</p>}

    {banner && <AlertBanner hazard={banner} distance={banner.at_m - (progress?.along ?? 0)} onFindWayAround={onFindWayAround} />}

    {prompt && <div className="trip-prompt" role="group" aria-labelledby="prompt-text">
      <p id="prompt-text">You just passed: <b>{prompt.label}</b>. Was it blocked?</p>
      <div className="trip-prompt-buttons">
        <button type="button" className="primary" onClick={() => trip.answer(prompt, 'blocked')}>Blocked</button>
        <button type="button" className="secondary" onClick={() => trip.answer(prompt, 'clear')}>It was clear</button>
        <button type="button" className="link-button" onClick={() => trip.answer(prompt, 'skip')}>Skip</button>
      </div>
    </div>}
    {trip.notice && <p className="trip-notice" role="status">{trip.notice} <button type="button" className="link-button" onClick={trip.dismissNotice}>Dismiss</button></p>}

    {progress && <div className="trip-progress">
      <div className="trip-stats">
        <span><b>{progress.eta.toLocaleTimeString('en-CA', { hour: 'numeric', minute: '2-digit' })}</b> arrival</span>
        <span><b>{formatMetres(progress.remaining)}</b> left</span>
      </div>
      <div className="trip-bar" role="progressbar" aria-label="Trip progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress.share * 100)}>
        <span style={{ width: `${progress.share * 100}%` }} />
      </div>
    </div>}

    {trip.ahead.filter((h) => h !== banner).length > 0 && <details className="trip-ahead">
      <summary>Coming up on this route ({trip.ahead.filter((h) => h !== banner).length})</summary>
      <ul>{trip.ahead.filter((h) => h !== banner).slice(0, 6).map((h) => <li key={h.id}>
        <span className={`trip-dot trip-dot-${h.severity}`} aria-hidden="true" />
        <span>{h.label}</span><span className="trip-ahead-m">{formatMetres(h.at_m - (progress?.along ?? 0))}</span>
      </li>)}</ul>
    </details>}

    {mode === 'sim' && <div className="trip-sim" role="group" aria-label="Simulation controls">
      <button type="button" className="secondary" onClick={() => sim.setPlaying(!sim.playing)}>{sim.playing ? 'Pause' : 'Resume'}</button>
      <div className="trip-rates" role="radiogroup" aria-label="Simulation speed">
        {SIM_RATES.map((rate) => <button key={rate} type="button" role="radio" aria-checked={sim.rate === rate}
          className={sim.rate === rate ? 'current' : ''} onClick={() => sim.setRate(rate)}>{rate}×</button>)}
      </div>
      <button type="button" className="link-button" disabled={sim.wrongTurn} onClick={sim.takeWrongTurn}>Take a wrong turn</button>
    </div>}

    <div className="trip-actions">
      <details className="trip-report">
        <summary>Report a problem here</summary>
        <ReportMenu onReport={trip.report} />
      </details>
      <label className="trip-sound">
        <input type="checkbox" checked={trip.sound} onChange={(event) => trip.setSound(event.target.checked)} />
        Spoken directions and alerts
      </label>
      <button type="button" className="secondary" onClick={onEnd}>End trip</button>
    </div>
  </section>
}

function ReportMenu({ onReport }: { onReport: (kind: ReportKind) => void }) {
  return <div className="report-menu">
    {REPORT_KINDS.map((item) => <button key={item.kind} type="button" className="secondary" onClick={() => onReport(item.kind)}>{item.label}</button>)}
  </div>
}
