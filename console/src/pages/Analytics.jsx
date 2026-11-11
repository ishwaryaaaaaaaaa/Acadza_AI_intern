import { useMemo, useState } from 'react'
import {
  ChartNoAxesColumnIncreasing,
  Calendar,
  ChevronDown,
  FileText,
  CircleAlert,
  CircleCheck,
  Zap,
  TrendingUp,
  Shapes,
  Layers,
  Lightbulb,
  Table2,
} from 'lucide-react'
import Shell from '../components/Shell.jsx'
import { useLive } from '../api.js'
import art from '../assets/insights-illustration.webp'
import './Analytics.css'

// Validated categorical order (dataviz validator: all six checks pass on white). Colour follows the family, never rank.
const FAMILY_COLORS = ['#e8710a', '#2f6fe4', '#b8860b', '#2aa198', '#8a5cd0', '#9a9db0']
const LINE = { reported: '#1d5ee0', resolved: '#2fb45b' }
const RANGES = [
  { key: '7d', label: 'Last 7 Days' },
  { key: '30d', label: 'Last 30 Days' },
  { key: 'all', label: 'All Time' },
]

const dayLabel = (iso, n) => {
  const d = new Date(`${iso}T00:00:00`)
  return n <= 7 ? d.toLocaleDateString([], { weekday: 'short' }) : d.toLocaleDateString([], { day: 'numeric', month: 'short' })
}

// Four gridline steps of a round size (1, 2, 5 × 10ⁿ), so ticks read 10 / 20 / 30 / 40, never 13 / 25 / 38.
function niceStep(v) {
  const raw = Math.max(1, v) / 4
  const p = Math.pow(10, Math.floor(Math.log10(raw)))
  return [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw)
}

/* ------------------------------------------------------------------ line chart */
function ProgressChart({ data }) {
  const [hover, setHover] = useState(null)
  const W = 520
  const H = 200
  const P = { l: 34, r: 46, t: 16, b: 30 }
  const n = data.length
  const step = niceStep(Math.max(...data.map((d) => Math.max(d.reported, d.resolved))))
  const max = step * 4
  const x = (i) => P.l + (n === 1 ? (W - P.l - P.r) / 2 : (i * (W - P.l - P.r)) / (n - 1))
  const y = (v) => P.t + (H - P.t - P.b) * (1 - v / max)
  const ticks = [0, 1, 2, 3, 4].map((k) => k * step)
  const path = (k) => data.map((d, i) => `${i ? 'L' : 'M'}${x(i)},${y(d[k])}`).join(' ')
  const area = (k) => `${path(k)} L${x(n - 1)},${y(0)} L${x(0)},${y(0)} Z`
  const labelEvery = Math.max(1, Math.ceil(n / 8))
  const last = data[n - 1] || { reported: 0, resolved: 0 }
  // keep the two end labels from colliding
  let yRep = y(last.reported)
  let yRes = y(last.resolved)
  if (Math.abs(yRep - yRes) < 22) {
    if (yRep >= yRes) yRep = yRes + 22
    else yRes = yRep + 22
  }

  return (
    <div className="lc">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Cumulative reported vs resolved questions, ${data[0]?.date} to ${last.date}`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect()
          const px = ((e.clientX - r.left) / r.width) * W
          const i = Math.round(((px - P.l) / (W - P.l - P.r)) * (n - 1))
          setHover(Math.max(0, Math.min(n - 1, i)))
        }}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} className="lc-grid" />
            <text x={P.l - 8} y={y(t) + 4} className="lc-tick" textAnchor="end">
              {t}
            </text>
          </g>
        ))}
        {data.map((d, i) =>
          i % labelEvery === 0 || i === n - 1 ? (
            <text key={d.date} x={x(i)} y={H - 8} className="lc-tick" textAnchor="middle">
              {dayLabel(d.date, n)}
            </text>
          ) : null,
        )}
        <path d={area('resolved')} fill={LINE.resolved} opacity="0.1" />
        <path d={area('reported')} fill={LINE.reported} opacity="0.05" />
        <path d={path('reported')} className="lc-line" stroke={LINE.reported} />
        <path d={path('resolved')} className="lc-line" stroke={LINE.resolved} />
        {n <= 31 &&
          data.map((d, i) => (
            <g key={i}>
              <circle cx={x(i)} cy={y(d.reported)} r="4" fill="#fff" stroke={LINE.reported} strokeWidth="2" />
              <circle cx={x(i)} cy={y(d.resolved)} r="4" fill="#fff" stroke={LINE.resolved} strokeWidth="2" />
            </g>
          ))}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={y(0)} className="lc-cross" />}
        {/* direct end labels, like the mock's value pills */}
        <g className="lc-end">
          <rect x={x(n - 1) + 8} y={yRes - 11} width="32" height="22" rx="5" fill={LINE.resolved} />
          <text x={x(n - 1) + 24} y={yRes + 4} textAnchor="middle">
            {last.resolved}
          </text>
          <rect x={x(n - 1) + 8} y={yRep - 11} width="32" height="22" rx="5" fill={LINE.reported} />
          <text x={x(n - 1) + 24} y={yRep + 4} textAnchor="middle">
            {last.reported}
          </text>
        </g>
      </svg>
      {hover !== null && (
        <div className="tip" style={{ left: `${(x(hover) / W) * 100}%` }}>
          <b>{new Date(`${data[hover].date}T00:00:00`).toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })}</b>
          <span>
            <i style={{ background: LINE.reported }} /> Reported {data[hover].reported}
          </span>
          <span>
            <i style={{ background: LINE.resolved }} /> Resolved by faculty {data[hover].resolved}
          </span>
        </div>
      )}
      <div className="legend-row">
        <span>
          <i style={{ background: LINE.reported }} /> Reported
        </span>
        <span>
          <i style={{ background: LINE.resolved }} /> Resolved
        </span>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ donut */
function Donut({ items, total }) {
  const [hover, setHover] = useState(null)
  const R = 52
  const r = 33
  const C = 66
  const gap = total > 1 ? 0.025 : 0 // radians of surface gap between slices
  let a0 = -Math.PI / 2
  const arcs = items
    .filter((it) => it.count > 0)
    .map((it) => {
      const sweep = (it.count / total) * Math.PI * 2
      const s = a0 + gap / 2
      const e = a0 + sweep - gap / 2
      a0 += sweep
      const big = e - s > Math.PI ? 1 : 0
      const p = (rad, ang) => `${C + rad * Math.cos(ang)},${C + rad * Math.sin(ang)}`
      const d =
        sweep >= Math.PI * 2 - 0.001
          ? `M${C},${C - R} A${R},${R} 0 1 1 ${C - 0.01},${C - R} L${C - 0.01},${C - r} A${r},${r} 0 1 0 ${C},${C - r} Z`
          : `M${p(R, s)} A${R},${R} 0 ${big} 1 ${p(R, e)} L${p(r, e)} A${r},${r} 0 ${big} 0 ${p(r, s)} Z`
      return { ...it, d }
    })
  return (
    <div className="donut-wrap">
      <svg viewBox="0 0 132 132" className="donut2" role="img" aria-label={`${total} open or fixed real issues by type`}>
        {total === 0 && <circle cx={C} cy={C} r={(R + r) / 2} fill="none" stroke="#eceef4" strokeWidth={R - r} />}
        {arcs.map((a) => (
          <path
            key={a.label}
            d={a.d}
            fill={FAMILY_COLORS[a.slot]}
            opacity={hover && hover !== a.label ? 0.35 : 1}
            onMouseEnter={() => setHover(a.label)}
            onMouseLeave={() => setHover(null)}
          >
            <title>{`${a.label}: ${a.count} (${Math.round((100 * a.count) / total)}%)`}</title>
          </path>
        ))}
        <text x={C} y={C + 2} className="d2-num" textAnchor="middle">
          {total}
        </text>
        <text x={C} y={C + 17} className="d2-cap" textAnchor="middle">
          Issues
        </text>
      </svg>
      <ul className="d2-legend">
        {items.map((it) => (
          <li
            key={it.label}
            className={hover && hover !== it.label ? 'is-dim' : ''}
            onMouseEnter={() => setHover(it.label)}
            onMouseLeave={() => setHover(null)}
          >
            <i style={{ background: FAMILY_COLORS[it.slot] }} />
            <span>{it.label}</span>
            <b>{total ? Math.round((100 * it.count) / total) : 0}%</b>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function Analytics() {
  const [range, setRange] = useState('all')
  const [table, setTable] = useState(false)
  const { data: a, error } = useLive(`/analytics?range=${range}`)
  const c = a?.cards ?? {}
  const maxSubj = useMemo(() => Math.max(1, ...(a?.subjects ?? []).map((s) => s.reports)), [a])

  return (
    <Shell sideArt>
      <div className="an">
        <header className="an-head">
          <div>
            <h1>
              <ChartNoAxesColumnIncreasing size={30} strokeWidth={2.6} className="an-head-icon" /> Analytics
            </h1>
            <p className="an-sub">
              Track review progress, issue trends, and question quality over time.
              <svg className="an-swoosh" viewBox="0 0 120 10" preserveAspectRatio="none" aria-hidden="true">
                <path d="M2 7 C 35 2, 85 1, 118 4" />
              </svg>
            </p>
          </div>
          <label className="an-range">
            <Calendar size={16} />
            <select value={range} onChange={(e) => setRange(e.target.value)} aria-label="Time range">
              {RANGES.map((r) => (
                <option key={r.key} value={r.key}>
                  {r.label}
                </option>
              ))}
            </select>
            <ChevronDown size={16} className="an-range-chev" />
          </label>
        </header>

        <div className="an-cards">
          <div className="an-card an-card--total">
            <FileText size={28} />
            <span>
              <b>{a ? c.totalReported : '–'}</b>
              <small>Total Reported</small>
            </span>
          </div>
          <div className="an-card an-card--review">
            <CircleAlert size={28} />
            <span>
              <b>{a ? c.underReview : '–'}</b>
              <small>Under Review</small>
            </span>
          </div>
          <div className="an-card an-card--resolved">
            <CircleCheck size={28} />
            <span>
              <b>{a ? c.resolved : '–'}</b>
              <small>Resolved</small>
            </span>
          </div>
          <div className="an-card an-card--rate">
            <Zap size={28} />
            <span>
              <b>{a ? `${c.resolutionRate}%` : '–'}</b>
              <small>Resolution Rate</small>
            </span>
          </div>
        </div>
        {a && c.aiClosed > 0 && (
          <p className="an-note">
            Not counted as resolved: {c.aiClosed} reported question{c.aiClosed === 1 ? '' : 's'} the AI check closed as
            "no change needed". Only faculty decisions count here.
          </p>
        )}

        <div className="an-grid">
          <section className="card an-progress">
            <header className="an-card-head">
              <h2>
                <TrendingUp size={22} className="side-icon" /> Review Progress
              </h2>
              <button className={`an-tablebtn${table ? ' is-on' : ''}`} onClick={() => setTable((t) => !t)}>
                <Table2 size={14} /> {table ? 'Chart' : 'Table'}
              </button>
            </header>
            {a && !table && <ProgressChart data={a.progress} />}
            {a && table && (
              <div className="an-table-wrap">
                <table className="an-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Reported (total)</th>
                      <th>Resolved by faculty (total)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {a.progress.map((p) => (
                      <tr key={p.date}>
                        <td>{p.date}</td>
                        <td>{p.reported}</td>
                        <td>{p.resolved}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="card an-types">
            <h2>
              <Shapes size={22} className="side-icon" /> Issue Types
            </h2>
            {a && <Donut items={a.issueTypes} total={a.issueTotal} />}
            {a && (a.notDefect > 0 || a.rejectedByFaculty > 0) && (
              <p className="an-foot">
                Not shown: {a.notDefect} report{a.notDefect === 1 ? '' : 's'} that weren't question errors
                {a.rejectedByFaculty > 0 ? `, ${a.rejectedByFaculty} rejected by faculty` : ''}.
              </p>
            )}
          </section>

          <section className="card an-subjects">
            <h2>
              <Layers size={22} className="side-icon" /> Subject-wise Issues
            </h2>
            <ul className="bars">
              {(a?.subjects ?? []).map((s) => (
                <li key={s.label} title={`${s.label}: ${s.reports} reports on ${s.questions} questions`}>
                  <span className="bar-label">{s.label}</span>
                  <span className="bar-track">
                    <span className="bar-fill" style={{ width: `${(100 * s.reports) / maxSubj}%` }} />
                  </span>
                  <b>{s.reports}</b>
                </li>
              ))}
            </ul>
            <p className="an-foot">Student reports per subject in this period.</p>
          </section>

          <section className="card an-insights">
            <div className="an-ins-body">
              <h2>
                <Lightbulb size={22} className="an-bulb" /> Key Insights
              </h2>
              <ul>
                {(a?.insights ?? []).map((t, i) => (
                  <li key={i}>
                    <CircleCheck size={18} fill="#2fb45b" color="#fff" />
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </div>
            <img className="an-ins-art" src={art} alt="" width="648" height="640" />
          </section>
        </div>
        {error && <p className="error">Couldn't reach the server. Retrying…</p>}
      </div>
    </Shell>
  )
}
