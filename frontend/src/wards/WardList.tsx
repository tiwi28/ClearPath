import { useEffect, useRef, useState } from 'react'
import { getWards, locateWard } from '../api'
import AddressInput from '../components/AddressInput'
import type { Field } from '../components/AddressInput'
import type { WardSummary } from '../types'
import { prefetchWard } from './cache'

type Props = { selected: number | null; onSelect: (id: number) => void }

export default function WardList({ selected, onSelect }: Props) {
  const [wards, setWards] = useState<WardSummary[]>([])
  const [listError, setListError] = useState('')
  const [search, setSearch] = useState<Field>({ text: '', point: null })
  const [searchError, setSearchError] = useState('')
  const prefetch = useRef(0)
  // Load a card while the pointer rests on (or focus lands on) its row, so the click is instant.
  const warm = (id: number) => { window.clearTimeout(prefetch.current); prefetch.current = window.setTimeout(() => prefetchWard(id), 120) }
  const cool = () => window.clearTimeout(prefetch.current)

  useEffect(() => {
    const pending = new AbortController()
    getWards(pending.signal).then(setWards).catch((failure) => {
      if (!pending.signal.aborted) setListError(failure instanceof Error ? failure.message : String(failure))
    })
    return () => pending.abort()
  }, [])

  useEffect(() => {
    if (!search.point) return
    const pending = new AbortController()
    locateWard(search.point, pending.signal).then((ward) => { setSearchError(''); onSelect(ward.id) }).catch((failure) => {
      if (!pending.signal.aborted) setSearchError(failure instanceof Error ? failure.message : String(failure))
    })
    return () => pending.abort()
  }, [search.point, onSelect])

  return <div className="step ward-list">
    <AddressInput id="ward-search" label="Find your ward by address" field={search} onChange={setSearch} onFocus={() => {}} />
    {searchError && <p className="field-error" role="alert">{searchError}</p>}
    <p className="hint">Listed by ward number. Wards are not ranked.</p>
    {listError && <p className="error" role="alert">{listError}</p>}
    <ol className="wards">
      {wards.map((ward) => <li key={ward.id}>
        <button type="button" className={`ward-row${ward.id === selected ? ' selected' : ''}`}
          aria-current={ward.id === selected ? 'page' : undefined} onClick={() => onSelect(ward.id)}
          onPointerEnter={() => warm(ward.id)} onPointerLeave={cool} onFocus={() => warm(ward.id)} onBlur={cool}>
          <span className="ward-number">{ward.id}</span>
          <span>{ward.name}</span>
        </button>
      </li>)}
    </ol>
  </div>
}
