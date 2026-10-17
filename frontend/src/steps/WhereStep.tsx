import { useState } from 'react'
import type { FormEvent } from 'react'
import AddressInput from '../components/AddressInput'
import type { Field } from '../components/AddressInput'

export type Target = 'start' | 'destination'
type Props = {
  start: Field
  destination: Field
  target: Target
  onStart: (field: Field) => void
  onDestination: (field: Field) => void
  onTarget: (target: Target) => void
  onNext: () => void
}

const EXAMPLE = {
  start: { text: 'Union Station', point: [-79.3806, 43.6453] } as Field,
  destination: { text: 'CN Tower', point: [-79.3871, 43.6426] } as Field,
}

export default function WhereStep({ start, destination, target, onStart, onDestination, onTarget, onNext }: Props) {
  const [locating, setLocating] = useState(false)
  const [error, setError] = useState('')

  function locate() {
    if (!navigator.geolocation) { setError('Your browser can’t share your location. Search for your start instead.'); return }
    setLocating(true); setError('')
    navigator.geolocation.getCurrentPosition((position) => {
      setLocating(false)
      onStart({ text: 'My location', point: [position.coords.longitude, position.coords.latitude] })
      onTarget('destination')
    }, () => {
      setLocating(false)
      setError('Location access was blocked. Search for your start or click the map.')
    }, { enableHighAccuracy: true, timeout: 10_000 })
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!start.point || !destination.point) {
      setError(`Choose a ${!start.point ? 'start' : 'destination'} from the suggestions, or click the map to drop it.`)
      return
    }
    setError('')
    onNext()
  }

  return <form className="step" onSubmit={submit} aria-labelledby="where-title">
    <h2 id="where-title">Where are you going?</h2>
    <AddressInput id="start" label="From" field={start} onFocus={() => onTarget('start')} onChange={onStart} />
    <div className="field-actions">
      <button type="button" className="link-button" onClick={locate} disabled={locating}>
        {locating ? 'Finding you…' : 'Use my location'}
      </button>
      <button type="button" className="link-button" onClick={() => { onStart(destination); onDestination(start) }}>Swap</button>
    </div>
    <AddressInput id="destination" label="To" field={destination} onFocus={() => onTarget('destination')} onChange={onDestination} />
    <p className="hint">Or click the map to set the {target === 'start' ? 'start' : 'destination'}.</p>
    {error && <p className="error" role="alert">{error}</p>}
    <button type="submit" className="primary">Next: how you get around</button>
    <button type="button" className="link-button example" onClick={() => { onStart(EXAMPLE.start); onDestination(EXAMPLE.destination) }}>
      Try an example: Union Station to the CN Tower
    </button>
  </form>
}
