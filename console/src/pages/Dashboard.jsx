import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import {
  TriangleAlert,
  CircleAlert,
  Hourglass,
  CircleCheck,
  ChevronRight,
  ChevronDown,
  Layers,
  FileText,
  Target,
  Clock3,
  ArrowRight,
  Check,
  Loader,
  X,
} from 'lucide-react'
import Shell from '../components/Shell.jsx'
import { useLive, timeAgo } from '../api.js'
import { useSettings } from '../settings.jsx'
import art from '../assets/dashboard-illustration.webp'
import './Dashboard.css'

const TIERS = [
  { key: 'critical', label: 'Critical', sub: 'Needs immediate fix', icon: TriangleAlert },
  { key: 'high', label: 'High', sub: 'Review soon', icon: CircleAlert },
  { key: 'medium', label: 'Medium', sub: 'Can be reviewed later', icon: Hourglass },
]

const SORTS = [
  { key: 'priority', label: 'Priority' },
  { key: 'reports', label: 'Most reports' },
  { key: 'confidence', label: 'Confidence' },
  { key: 'oldest', label: 'Oldest report' },
]

function StatCard({ tone, icon: Icon, value, label, sub, onClick }) {
  return (
    <button className={`stat stat--${tone}`} onClick={onClick}>
      <Icon className="stat-icon" size={27} strokeWidth={2} />
      <span className="stat-body">
        <span className="stat-value">{value ?? '–'}</span>
        <span className="stat-label">{label}</span>
        <span className="stat-sub">{sub}</span>
      </span>
      <ChevronRight className="stat-chev" size={18} strokeWidth={2.4} />
    </button>
  )
}

function SortMenu({ value, onChange }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const current = SORTS.find((s) => s.key === value) ?? SORTS[0]
  return (
    <div className="sort" ref={ref}>
      <button className="sort-btn" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(!open)}>
        Sort by: {current.label} <ChevronDown size={17} strokeWidth={2.2} />
      </button>
      {open && (
        <ul className="sort-menu" role="listbox">
          {SORTS.map((s) => (
            <li key={s.key}>
              <button
                role="option"
                aria-selected={s.key === value}
                className={s.key === value ? 'is-on' : ''}
                onClick={() => {
                  onChange(s.key)
                  setOpen(false)
                }}
              >
                {s.label}
                {s.key === value && <Check size={15} />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Donut({ pct }) {
  const r = 42
  const c = 2 * Math.PI * r
  return (
    <svg className="donut" viewBox="0 0 110 110" role="img" aria-label={`${pct}% resolved`}>
      <circle cx="55" cy="55" r={r} className="donut-track" />
      <circle
        cx="55"
        cy="55"
        r={r}
        className="donut-fill"
        strokeDasharray={`${(c * pct) / 100} ${c}`}
        transform="rotate(-90 55 55)"
      />
      <text x="55" y="55" className="donut-pct">
        {pct}%
      </text>
      <text x="55" y="71" className="donut-cap">
        Resolved
      </text>
    </svg>
  )
}

const EVENT_ICON = {
  fixed: { icon: CircleCheck, tone: 'ok' },
  verified: { icon: CircleCheck, tone: 'ok' },
  approved: { icon: CircleCheck, tone: 'ok' },
  confirmed: { icon: CircleCheck, tone: 'ok' },
  edited: { icon: CircleCheck, tone: 'ok' },
  rejected: { icon: X, tone: 'bad' },
  reverted: { icon: X, tone: 'bad' },
  review: { icon: Clock3, tone: 'wait' },
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tier = params.get('tier') || 'all'
  const { settings } = useSettings()
  const sort = params.get('sort') || settings.defaultSort
  const onlyDecision = params.get('filter') === 'decision'
  const [selected, setSelected] = useState(() => new Set())
  const queueRef = useRef(null)
  const location = useLocation()
  const [toast, setToast] = useState(location.state?.toast || null)
  const showToast = toast && settings.notifyToasts
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(t)
  }, [toast])

  const { data: dash, error } = useLive('/dashboard')
  const { data: queue } = useLive(`/queue?sort=${sort}`)

  const rows = useMemo(() => {
    let r = queue?.rows ?? []
    if (tier !== 'all') r = r.filter((x) => x.tier === tier)
    if (onlyDecision) r = r.filter((x) => x.needsDecision)
    return r
  }, [queue, tier, onlyDecision])

  const counts = dash?.counts ?? {}
  const all = (counts.critical ?? 0) + (counts.high ?? 0) + (counts.medium ?? 0)

  const setParam = (k, v) => {
    const p = new URLSearchParams(params)
    if (v === null || v === 'all' || (k === 'sort' && v === settings.defaultSort)) p.delete(k)
    else p.set(k, v)
    setParams(p, { replace: true })
    setSelected(new Set())
  }
  const goTier = (t) => {
    setParam('tier', t)
    queueRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  const toggle = (qid) =>
    setSelected((s) => {
      const n = new Set(s)
      n.has(qid) ? n.delete(qid) : n.add(qid)
      return n
    })
  const allChecked = rows.length > 0 && rows.every((r) => selected.has(r.questionId))
  const openCase = (qid, list) =>
    navigate(`/case/${qid}`, { state: { sequence: list ?? rows.map((r) => r.questionId) } })

  return (
    <Shell>
      <div className="dash">
        <section className="dash-hello">
          <h1>
            Welcome back, {settings.displayName}! <span aria-hidden="true">👋</span>
          </h1>
          <p className="dash-sub">
            Review reported questions, verify issues, and make quick fixes.
            <svg className="dash-swoosh" viewBox="0 0 120 10" preserveAspectRatio="none" aria-hidden="true">
              <path d="M2 7 C 35 2, 85 1, 118 4" />
            </svg>
          </p>

          <div className="stats">
            {TIERS.map((t) => (
              <StatCard
                key={t.key}
                tone={t.key}
                icon={t.icon}
                value={dash ? counts[t.key] : null}
                label={t.label}
                sub={t.sub}
                onClick={() => goTier(t.key)}
              />
            ))}
            <StatCard
              tone="resolved"
              icon={CircleCheck}
              value={dash?.resolvedThisWeek}
              label="Resolved"
              sub="Closed this week"
              onClick={() => navigate('/reviews')}
            />
          </div>
        </section>

        <figure className="dash-art">
          <img src={art} alt="A cheerful teacher checking questions on a laptop" width="1024" height="704" />
        </figure>

        <section className="card queue" ref={queueRef} aria-labelledby="queue-title">
          <header className="queue-head">
            <h2 id="queue-title">
              <Layers size={24} strokeWidth={2} className="queue-title-icon" /> Review Queue
            </h2>
            <SortMenu value={sort} onChange={(v) => setParam('sort', v)} />
          </header>

          <div className="tabs" role="tablist">
            {[
              { key: 'all', label: 'All', n: all },
              { key: 'critical', label: 'Critical', n: counts.critical },
              { key: 'high', label: 'High', n: counts.high },
              { key: 'medium', label: 'Medium', n: counts.medium },
            ].map((t) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={tier === t.key}
                className={`tab${tier === t.key ? ' is-on' : ''}`}
                onClick={() => setParam('tier', t.key)}
              >
                {t.label} ({t.n ?? 0})
              </button>
            ))}
          </div>

          {onlyDecision && (
            <div className="filter-chip">
              Showing only cases that need your decision
              <button aria-label="Show all cases" onClick={() => setParam('filter', null)}>
                <X size={14} />
              </button>
            </div>
          )}

          {selected.size > 0 && (
            <div className="bulkbar">
              <span>
                {selected.size} selected
              </span>
              <button
                className="bulk-primary"
                onClick={() => {
                  const list = rows.map((r) => r.questionId).filter((q) => selected.has(q))
                  openCase(list[0], list)
                }}
              >
                Review selected <ArrowRight size={15} />
              </button>
              <button className="bulk-clear" onClick={() => setSelected(new Set())}>
                Clear
              </button>
            </div>
          )}

          <div className="table-wrap">
            <table className="qtable">
              <thead>
                <tr>
                  <th className="col-check">
                    <input
                      type="checkbox"
                      aria-label="Select all"
                      checked={allChecked}
                      onChange={() =>
                        setSelected(allChecked ? new Set() : new Set(rows.map((r) => r.questionId)))
                      }
                    />
                  </th>
                  <th>Question ID</th>
                  <th>Subject</th>
                  <th>Issue (AI Check)</th>
                  <th>Reports</th>
                  <th>Confidence</th>
                  <th aria-label="Open" />
                </tr>
              </thead>
              <tbody>
                {!queue &&
                  !error &&
                  [0, 1, 2].map((i) => (
                    <tr key={i} className="row-skeleton">
                      <td colSpan={7}>
                        <span />
                      </td>
                    </tr>
                  ))}
                {queue && rows.length === 0 && (
                  <tr>
                    <td colSpan={7} className="empty">
                      Nothing in this view. Every reported question here is resolved.
                    </td>
                  </tr>
                )}
                {rows.map((r) => (
                  <tr
                    key={r.questionId}
                    className={`row row--${r.tier}`}
                    onClick={() => openCase(r.questionId)}
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && openCase(r.questionId)}
                  >
                    <td className="col-check" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        aria-label={`Select ${r.displayId}`}
                        checked={selected.has(r.questionId)}
                        onChange={() => toggle(r.questionId)}
                      />
                    </td>
                    <td className="qid">{r.displayId}</td>
                    <td>{r.subject}</td>
                    <td>
                      <span className="issue">{r.issue}</span>
                      {!r.needsDecision && (
                        <span className="autofix" title="Already applied by the engine; one click to confirm or revert">
                          Auto-fixed
                        </span>
                      )}
                    </td>
                    <td>
                      <span className="reports">
                        <FileText size={16} strokeWidth={1.9} /> {r.reports}
                      </span>
                    </td>
                    <td>
                      <span className="conf">{Math.round(r.confidence * 100)}%</span>
                    </td>
                    <td className="col-go">
                      <ChevronRight size={18} strokeWidth={2.2} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {error && <p className="error">Couldn't reach the server. Retrying…</p>}
        </section>

        <aside className="dash-side">
          <section className="card progress" aria-labelledby="progress-title">
            <h2 id="progress-title">
              <Target size={22} strokeWidth={2} className="side-icon" /> Overall Progress
            </h2>
            <div className="progress-body">
              <Donut pct={dash?.progress ?? 0} />
              <ul className="legend">
                <li>
                  <CircleCheck size={18} className="lg-ok" fill="#32bd65" color="#fff" />
                  <strong>{dash?.resolved ?? '–'}</strong> Resolved
                </li>
                <li>
                  <Loader size={18} className="lg-wait" />
                  <strong>{dash?.underReview ?? '–'}</strong> Under Review
                </li>
                <li>
                  <FileText size={18} className="lg-doc" />
                  <strong>{dash?.totalReported ?? '–'}</strong> Total Reported
                </li>
              </ul>
            </div>
          </section>

          <section className="card activity" aria-labelledby="activity-title">
            <header className="activity-head">
              <h2 id="activity-title">
                <Clock3 size={22} strokeWidth={2} className="side-icon" /> Recent Activity
              </h2>
              <button className="link" onClick={() => navigate('/activity')}>
                View All <ArrowRight size={15} />
              </button>
            </header>
            <ol className="events">
              {(dash?.recent ?? []).map((e, i) => {
                const { icon: Icon, tone } = EVENT_ICON[e.kind] ?? EVENT_ICON.review
                return (
                  <li key={i} className="event">
                    <span className={`event-dot event-dot--${tone}`}>
                      <Icon size={14} strokeWidth={3} />
                    </span>
                    <button className="event-body" onClick={() => openCase(e.questionId, [e.questionId])}>
                      <strong>{e.title}</strong>
                      <span>{e.detail}</span>
                    </button>
                    <time dateTime={e.at}>{timeAgo(e.at)}</time>
                  </li>
                )
              })}
            </ol>
          </section>
        </aside>
      </div>
      {showToast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </Shell>
  )
}
