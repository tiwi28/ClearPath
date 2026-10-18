import type { MultiPolygon, Polygon } from 'geojson'
import type { ReactNode } from 'react'
import type { WardCard as Card } from '../types'
import WardTrend from './WardTrend'

function longDate(iso: string) {
  return new Date(`${iso.slice(0, 10)}T12:00:00Z`).toLocaleDateString('en-CA', { month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
}

/** The ward outline as an SVG path, longitude scaled by latitude so the shape isn't stretched. */
function Outline({ geometry }: { geometry: Polygon | MultiPolygon }) {
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates
  const points = polygons.flat(2)
  const lats = points.map((p) => p[1])
  const kx = Math.cos(((Math.min(...lats) + Math.max(...lats)) / 2) * Math.PI / 180)
  const xs = points.map((p) => p[0] * kx)
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...lats), Math.max(...lats)]
  const scale = 100 / Math.max(maxX - minX, maxY - minY)
  const d = polygons.map((rings) => rings.map((ring) => ring.map(([lng, lat], i) =>
    `${i ? 'L' : 'M'}${((lng * kx - minX) * scale).toFixed(1)},${((maxY - lat) * scale).toFixed(1)}`).join('') + 'Z').join('')).join('')
  return <svg className="ward-outline" viewBox={`-4 -4 ${(maxX - minX) * scale + 8} ${(maxY - minY) * scale + 8}`} aria-hidden="true">
    <path d={d} />
  </svg>
}

function Stat({ value, label, note, source, href }: { value: ReactNode; label: string; note?: string; source: string; href: string }) {
  return <div className="stat">
    <span className="stat-value">{value}</span>
    <span className="stat-label">{label}</span>
    {note && <span className="stat-note">{note}</span>}
    <a className="stat-source" href={href} target="_blank" rel="noreferrer">Source: {source}<span className="visually-hidden"> (opens in a new tab)</span></a>
  </div>
}

const unavailable = <span className="stat-missing">Unavailable</span>

export default function WardCard({ card }: { card: Card }) {
  const { elevators, closures, forecast } = card.live
  const change = card.reports_prior_12m ? (card.reports_12m - card.reports_prior_12m) / card.reports_prior_12m : null
  const [winterFrom, winterTo] = card.meta.winter.map((day) => new Date(`${day}T12:00:00Z`).getUTCFullYear())

  return <article className="ward-card" aria-labelledby="ward-title">
    <header className="ward-head">
      <div>
        <h2 id="ward-title"><span className="ward-badge"><span className="visually-hidden">Ward </span>{card.id}</span>{card.name}</h2>
        <p className="ward-meta">311 reports through {longDate(card.meta.reports_through)} · Live numbers as of {new Date(card.live_as_of).toLocaleTimeString('en-CA', { hour: 'numeric', minute: '2-digit' })}</p>
      </div>
      <Outline geometry={card.geometry} />
    </header>

    <p className="ward-notice">This page shows City of Toronto data only. It does not mention candidates or compare wards.</p>

    <section className="ward-section ward-plain" aria-labelledby="plain-title">
      <div className="ward-section-head">
        <h3 id="plain-title">In plain words</h3>
        <span className="ward-chip">{card.summary_source === 'gemini' ? 'AI summary of the numbers below' : 'Summary of the numbers below'}</span>
      </div>
      <p className="ward-summary">{card.summary}</p>
      {card.summary_live && <p className="ward-summary-live">{card.summary_live}</p>}
    </section>

    <section className="ward-section" aria-labelledby="numbers-title">
      <h3 id="numbers-title">Key numbers</h3>
      <div className="stats">
        <Stat value={card.snow_last_winter} label={`Reports of sidewalks not cleared of snow or ice, winter ${winterFrom}–${winterTo}`}
          source="Toronto 311" href={card.sources['311']} />
        <Stat value={card.damage_12m} label="Reports of damaged sidewalks or curbs, past 12 months"
          note={card.ramps_12m ? `Plus ${card.ramps_12m} about ramps or tactile pavers` : undefined} source="Toronto 311" href={card.sources['311']} />
        <Stat value={elevators.available ? elevators.out : unavailable} label="TTC elevators out of service right now"
          note={elevators.available ? (elevators.stations ? `${elevators.stations} subway or LRT ${elevators.stations === 1 ? 'station' : 'stations'} in the ward` : 'No subway or LRT stations in this ward') : undefined}
          source="TTC service alerts" href={card.sources.ttc} />
        <Stat value={closures.available ? closures.count : unavailable} label="Active road or sidewalk restrictions"
          note={closures.available && closures.count ? `${closures.sidewalk} mention the sidewalk, ${closures.road_closed} close a road` : undefined}
          source="City road restrictions" href={card.sources.closures} />
        <Stat value={forecast.available ? forecast.high : unavailable} label="Areas with a high chance of sidewalk barrier reports today"
          note={forecast.available ? `Out of ${forecast.cells} forecast areas in the ward` : undefined}
          source="ClearPath forecast" href={card.sources.forecast} />
      </div>
    </section>

    <section className="ward-section" aria-labelledby="attention-title">
      <h3 id="attention-title">What may need attention</h3>
      <div className="attention">
        <div className="attention-chart">
          <p className="attention-lead">
            {card.reports_12m} reports in the past 12 months
            {change !== null && `, ${Math.abs(Math.round(change * 100))}% ${change >= 0 ? 'more' : 'fewer'} than the year before`}.
          </p>
          <WardTrend months={card.monthly} />
        </div>
        <div className="attention-side">
          <h4>Where reports cluster</h4>
          {card.top_places.length ? <ol className="places">
            {card.top_places.map((place) => <li key={place.place}><span>{place.place}</span><span className="places-n">{place.reports}</span></li>)}
          </ol> : <p className="hint">Most reports in this ward don't name an intersection.</p>}
          <p className="open-share-line"><b className="open-share">{Math.round(card.open_share_12m * 100)}%</b> of the past year's reports are not marked completed yet.</p>
        </div>
      </div>
    </section>

    <section className="ward-section" aria-labelledby="sources-title">
      <h3 id="sources-title">Sources</h3>
      <ul className="sources">
        <li><a href={card.sources['311']} target="_blank" rel="noreferrer">Toronto Open Data: 311 service requests</a></li>
        <li><a href={card.sources.wards} target="_blank" rel="noreferrer">Toronto Open Data: City wards</a></li>
        <li><a href={card.sources.closures} target="_blank" rel="noreferrer">Toronto Open Data: road restrictions</a></li>
        <li><a href={card.sources.ttc} target="_blank" rel="noreferrer">TTC service advisories</a></li>
        <li><a href={card.sources.forecast} target="_blank" rel="noreferrer">Open-Meteo weather, used by the ClearPath forecast</a></li>
      </ul>
    </section>
  </article>
}
