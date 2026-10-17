import type { FormEvent } from 'react'
import { PROFILES } from '../format'
import type { ProfileName } from '../types'

type Props = {
  profile: ProfileName
  includeTransit: boolean
  avoidRisk: boolean
  onProfile: (profile: ProfileName) => void
  onIncludeTransit: (value: boolean) => void
  onAvoidRisk: (value: boolean) => void
  onBack: () => void
  onNext: () => void
}

export default function ProfileStep(props: Props) {
  function submit(event: FormEvent) {
    event.preventDefault()
    props.onNext()
  }

  return <form className="step" onSubmit={submit} aria-labelledby="how-title">
    <fieldset className="profiles">
      <legend className="visually-hidden">Mobility profile</legend>
      {PROFILES.map((option) => <label key={option.value} className="profile-card">
        <input type="radio" name="profile" value={option.value} checked={props.profile === option.value}
          onChange={() => props.onProfile(option.value)} />
        <span className="profile-text">
          <span className="profile-label">{option.label}</span>
          <span className="profile-detail">{option.detail}</span>
        </span>
      </label>)}
    </fieldset>
    <label className="toggle">
      <input type="checkbox" checked={props.includeTransit} onChange={(event) => props.onIncludeTransit(event.target.checked)} />
      <span className="toggle-text">
        <span>Include the TTC</span>
        <span className="toggle-detail">Subway, streetcar and bus trips, checked against station elevators and live outages.</span>
      </span>
    </label>
    <label className="toggle">
      <input type="checkbox" checked={props.avoidRisk} onChange={(event) => props.onAvoidRisk(event.target.checked)} />
      <span className="toggle-text">
        <span>Avoid likely sidewalk barriers</span>
        <span className="toggle-detail">Takes a short detour when our forecast shows a much higher chance of uncleared or damaged sidewalks.</span>
      </span>
    </label>
    <div className="step-actions">
      <button type="button" className="secondary" onClick={props.onBack}>Back</button>
      <button type="submit" className="primary">Find routes</button>
    </div>
  </form>
}
