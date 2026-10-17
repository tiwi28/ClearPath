import { formatDate, forecastDays, percent, RISK_STOPS } from '../format'
import type { RiskMap, Station } from '../types'
import type { Hover, Layers } from './MapView'

type LayerProps = {
  layers: Layers
  day: string
  onLayers: (layers: Layers) => void
  onDay: (day: string) => void
}

export function LayerPanel({ layers, day, onLayers, onDay }: LayerProps) {
  const options: { key: keyof Layers; label: string }[] = [
    { key: 'risk', label: 'Sidewalk barrier forecast' },
    { key: 'stations', label: 'TTC station elevators' },
    { key: 'barriers', label: 'Known barriers' },
  ]
  return <details className="layer-panel">
    <summary>Map layers</summary>
    <div className="layer-body">
      {options.map((option) => <label key={option.key} className="layer-option">
        <input type="checkbox" checked={layers[option.key]} onChange={(event) => onLayers({ ...layers, [option.key]: event.target.checked })} />
        {option.label}
      </label>)}
      <label className="layer-day">
        <span>Forecast for</span>
        <select value={day} onChange={(event) => onDay(event.target.value)}>
          {forecastDays().map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
    </div>
  </details>
}

type LegendProps = { risk: RiskMap | null; riskError: string; hover: Hover | null; layers: Layers }

export function Legend({ risk, riskError, hover, layers }: LegendProps) {
  const high = risk ? risk.features.filter((feature) => feature.properties.risk >= 0.3).length : 0
  return <aside className="legend" aria-label="Map legend">
    {layers.risk && <>
      <p className="legend-title">Chance of a sidewalk barrier report{risk ? `, ${formatDate(risk.date)}` : ''}</p>
      <div className="ramp" style={{ background: `linear-gradient(to right, ${RISK_STOPS.map(([, color]) => color).join(', ')})` }} aria-hidden="true" />
      <div className="ramp-labels"><span>Unlikely</span><span>Likely</span></div>
      <p className="legend-detail">{riskError ? riskError
        : hover?.kind === 'risk' ? `This area: ${percent(hover.cell.risk)} chance of a report about an uncleared or damaged sidewalk in the next 3 days. ${hover.cell.reports_last_year} reports here in the past year.`
          : hover?.kind === 'station' ? stationText(hover.station)
            : risk ? `${high ? `${high} areas likely to have barriers.` : 'Low risk across the city.'} Each hexagon is about 0.7 km². Areas without a hexagon have too few past reports to predict.`
              : 'Loading the forecast…'}</p>
    </>}
    {!layers.risk && hover?.kind === 'station' && <p className="legend-detail">{stationText(hover.station)}</p>}
    <ul className="legend-keys">
      <li><span className="key key-route" />Your route</li>
      <li><span className="key key-typical" />Typical route</li>
      <li><span className="key key-stairs" />Stairs</li>
      <li><span className="key key-gap" />Not confirmed</li>
      {layers.stations && <>
        <li><span className="dot dot-ok" />Elevator</li>
        <li><span className="dot dot-outage" />Elevator out</li>
        <li><span className="dot dot-none" />No elevator</li>
      </>}
    </ul>
  </aside>
}

function stationText(station: Station) {
  const lines = `Line ${station.lines.join(' and ')}`
  if (!station.has_elevator) return `${station.name} (${lines}) has no elevator.`
  const out = station.outages.filter((outage) => outage.kind === 'elevator')
  const escalators = station.outages.filter((outage) => outage.kind === 'escalator')
  return `${station.name} (${lines}): ${out.length ? `elevator out. ${out[0].text}` : 'elevators working.'}`
    + (escalators.length ? ` ${escalators.length} escalator${escalators.length > 1 ? 's' : ''} out.` : '')
}
