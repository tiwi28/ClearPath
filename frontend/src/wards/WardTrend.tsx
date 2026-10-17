import { useState } from 'react'
import type { WardMonth } from '../types'

// Two series, validated together (light surface): snow or ice, and damage plus ramps.
const SERIES = [
  { key: 'snow', label: 'Snow or ice', color: '#2f5fa8' },
  { key: 'damage', label: 'Damage and ramps', color: '#c25e00' },
] as const
const WIDTH = 640
const HEIGHT = 230
const PAD = { top: 14, right: 8, bottom: 32, left: 44 }

function monthLabel(month: string, withYear = false) {
  const [year, number] = month.split('-').map(Number)
  return new Date(Date.UTC(year, number - 1, 15)).toLocaleDateString('en-CA',
    { month: 'short', ...(withYear ? { year: 'numeric' } : {}), timeZone: 'UTC' })
}

function niceMax(value: number) {
  if (value <= 5) return 5
  const step = 10 ** Math.floor(Math.log10(value))
  return Math.ceil(value / step) * step
}

export default function WardTrend({ months }: { months: WardMonth[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const rows = months.map((m) => ({ month: m.month, snow: m.snow_ice, damage: m.damage + m.ramps }))
  const max = niceMax(Math.max(1, ...rows.map((r) => r.snow + r.damage)))
  const plotW = WIDTH - PAD.left - PAD.right
  const plotH = HEIGHT - PAD.top - PAD.bottom
  const slot = plotW / rows.length
  const barW = Math.max(4, slot - 6)
  const y = (value: number) => PAD.top + plotH - (value / max) * plotH
  const ticks = [0, max / 2, max]
  const active = hover === null ? null : rows[hover]

  return <figure className="trend">
    <figcaption className="trend-legend">
      {SERIES.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}
    </figcaption>
    <div className="trend-plot">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img"
        aria-label={`Monthly 311 accessibility reports from ${monthLabel(rows[0].month, true)} to ${monthLabel(rows[rows.length - 1].month, true)}`}
        onMouseLeave={() => setHover(null)}>
        {ticks.map((tick) => <g key={tick}>
          <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} className="trend-grid" />
          <text x={PAD.left - 8} y={y(tick)} dy="0.32em" textAnchor="end" className="trend-tick">{tick}</text>
        </g>)}
        {rows.map((row, index) => {
          const x = PAD.left + index * slot + (slot - barW) / 2
          const snowTop = y(row.snow)
          const total = y(row.snow + row.damage)
          return <g key={row.month} opacity={hover === null || hover === index ? 1 : 0.45}>
            {row.snow > 0 && <rect x={x} y={snowTop} width={barW} height={y(0) - snowTop} rx={row.damage ? 0 : 3} fill={SERIES[0].color} />}
            {row.damage > 0 && <rect x={x} y={total} width={barW} height={Math.max(0, snowTop - total - (row.snow ? 2 : 0))} rx={3} fill={SERIES[1].color} />}
            {(index % 3 === 0) && <text x={x + barW / 2} y={HEIGHT - 8} textAnchor="middle" className="trend-tick">
              {monthLabel(row.month, row.month.endsWith('-01') || index === 0)}</text>}
            <rect x={PAD.left + index * slot} y={PAD.top} width={slot} height={plotH} fill="transparent"
              onMouseEnter={() => setHover(index)} />
          </g>
        })}
      </svg>
      {active && hover !== null && <div className="trend-tip" style={{ left: `${((PAD.left + (hover + 0.5) * slot) / WIDTH) * 100}%` }}>
        <b>{monthLabel(active.month, true)}</b>
        <span><i style={{ background: SERIES[0].color }} />{active.snow} snow or ice</span>
        <span><i style={{ background: SERIES[1].color }} />{active.damage} damage and ramps</span>
      </div>}
    </div>
    <details className="trend-table">
      <summary>Show as a table</summary>
      <table>
        <thead><tr><th>Month</th><th>Snow or ice</th><th>Damage and ramps</th></tr></thead>
        <tbody>{rows.map((row) => <tr key={row.month}><td>{monthLabel(row.month, true)}</td><td>{row.snow}</td><td>{row.damage}</td></tr>)}</tbody>
      </table>
    </details>
  </figure>
}
