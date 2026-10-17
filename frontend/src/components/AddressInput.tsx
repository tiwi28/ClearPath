import { useEffect, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { searchPlaces } from '../api'
import { parsePoint } from '../format'
import type { LngLat, Place } from '../types'

export type Field = { text: string; point: LngLat | null }
type Props = {
  id: string
  label: string
  field: Field
  onChange: (field: Field) => void
  onFocus: () => void
}

export default function AddressInput({ id, label, field, onChange, onFocus }: Props) {
  const [query, setQuery] = useState<string | null>(null)
  const [places, setPlaces] = useState<Place[]>([])
  const [active, setActive] = useState(-1)
  const [searchError, setSearchError] = useState('')
  const listId = `${id}-suggestions`
  const open = places.length > 0

  useEffect(() => {
    if (!query || query.trim().length < 3 || parsePoint(query)) return
    const pending = new AbortController()
    const timer = setTimeout(() => {
      searchPlaces(query.trim(), pending.signal).then((results) => {
        if (!pending.signal.aborted) { setPlaces(results); setActive(-1); setSearchError('') }
      }).catch((failure) => {
        if (!pending.signal.aborted) { setPlaces([]); setSearchError(failure instanceof Error ? failure.message : String(failure)) }
      })
    }, 300)
    return () => { clearTimeout(timer); pending.abort() }
  }, [query])

  function pick(place: Place) {
    onChange({ text: place.label, point: place.coordinates })
    setQuery(null); setPlaces([]); setActive(-1)
  }

  function keyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!open) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActive((index) => (index + step + places.length) % places.length)
    } else if (event.key === 'Enter' && active >= 0) {
      event.preventDefault()
      pick(places[active])
    } else if (event.key === 'Escape') {
      setPlaces([])
    }
  }

  return <div className="address">
    <label htmlFor={id}>{label}</label>
    <input id={id} value={field.text} autoComplete="off" spellCheck={false}
      placeholder="Search a Toronto address or place"
      role="combobox" aria-expanded={open} aria-controls={listId} aria-autocomplete="list"
      aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
      onFocus={onFocus} onKeyDown={keyDown} onBlur={() => setPlaces([])}
      onChange={(event) => {
        const text = event.target.value
        onChange({ text, point: parsePoint(text) })
        setQuery(text)
        if (text.trim().length < 3) setPlaces([])
      }} />
    {open && <ul id={listId} role="listbox" aria-label={`${label} suggestions`} className="suggestions">
      {places.map((place, index) => <li key={`${place.label}-${index}`} id={`${listId}-${index}`} role="option"
        aria-selected={index === active} className={index === active ? 'active' : undefined}
        onMouseDown={(event) => { event.preventDefault(); pick(place) }}>{place.label}</li>)}
    </ul>}
    {searchError && <p className="field-error">{searchError}</p>}
  </div>
}
