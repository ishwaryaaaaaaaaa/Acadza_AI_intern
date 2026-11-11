import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CircleCheck,
  CircleX,
  FileText,
  Pencil,
  Layers,
  ArrowRight,
  ChevronDown,
  Calendar,
  Search,
  Target,
  Users,
  ShieldCheck,
  TriangleAlert,
  Check,
} from 'lucide-react'
import Shell from '../components/Shell.jsx'
import { useLive } from '../api.js'
import art from '../assets/reviews-illustration.webp'
import './MyReviews.css'

const RANGES = [
  { key: 'all', label: 'All Time' },
  { key: 'today', label: 'Today' },
  { key: '7d', label: 'Last 7 days' },
  { key: '30d', label: 'Last 30 days' },
]

const DECISION = {
  approved: { label: 'Approved & Fixed', icon: Check, tone: 'ok' },
  edited: { label: 'Edited', icon: Pencil, tone: 'blue' },
  rejected: { label: 'Rejected', icon: CircleX, tone: 'bad' },
}

function when(iso) {
  const d = new Date(iso)
  const now = new Date()
  const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diff = Math.round((day(now) - day(d)) / 86400000)
  if (diff === 0) return `Today, ${time}`
  if (diff === 1) return `Yesterday, ${time}`
  return `${d.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' })}, ${time}`
}

function inRange(iso, range) {
  if (range === 'all') return true
  const t = new Date(iso).getTime()
  const now = Date.now()
  if (range === 'today') return new Date(iso).toDateString() === new Date().toDateString()
  return now - t <= (range === '7d' ? 7 : 30) * 86400000
}

function Select({ icon: Icon, value, options, onChange, label }) {
  return (
    <label className="mr-select">
      {Icon && <Icon size={15} />}
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
        {options.map((o) => (
          <option key={o.key} value={o.key}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown size={15} className="mr-select-chev" />
    </label>
  )
}

export default function MyReviews() {
  const navigate = useNavigate()
  const { data, error } = useLive('/reviews')
  const [tab, setTab] = useState('all')
  const [subject, setSubject] = useState('all')
  const [range, setRange] = useState('all')
  const [query, setQuery] = useState('')

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (data?.rows ?? []).filter(
      (r) =>
        (tab === 'all' || r.decision === tab) &&
        (subject === 'all' || r.subject === subject) &&
        inRange(r.at, range) &&
        (!q ||
          [r.displayId, r.questionId, r.subject, r.chapter, r.issue, r.studentSaid]
            .filter(Boolean)
            .some((x) => x.toLowerCase().includes(q))),
    )
  }, [data, tab, subject, range, query])

  const s = data?.stats ?? {}
  const im = data?.impact ?? {}
  const tabCount = { all: s.total, approved: s.approved, edited: s.edited, rejected: s.rejected }

  return (
    <Shell sideArt>
      <div className="mr">
        <header className="mr-head">
          <div>
            <h1>
              <CircleCheck size={28} strokeWidth={2.4} className="mr-head-icon" /> My Reviews
            </h1>
            <p className="mr-sub">
              Your review history and decisions
              <svg className="mr-swoosh" viewBox="0 0 120 10" preserveAspectRatio="none" aria-hidden="true">
                <path d="M2 7 C 35 2, 85 1, 118 4" />
              </svg>
            </p>
          </div>
          <button className="mr-continue" onClick={() => navigate('/queue')}>
            Continue Reviewing <ArrowRight size={16} />
          </button>
        </header>

        <div className="mr-stats">
          {[
            { k: 'all', tone: 'total', icon: FileText, n: s.total, label: 'Total Reviewed' },
            { k: 'approved', tone: 'approved', icon: CircleCheck, n: s.approved, label: 'Approved & Fixed' },
            { k: 'rejected', tone: 'rejected', icon: CircleX, n: s.rejected, label: 'Rejected' },
            { k: 'edited', tone: 'edited', icon: Pencil, n: s.edited, label: 'Edited Manually' },
          ].map(({ k, tone, icon: Icon, n, label }) => (
            <button key={k} className={`mr-stat mr-stat--${tone}`} onClick={() => setTab(k)}>
              <span className="mr-stat-icon">
                <Icon size={24} strokeWidth={2} />
              </span>
              <span>
                <b>{data ? n : '–'}</b>
                <small>{label}</small>
              </span>
            </button>
          ))}
        </div>

        <div className="mr-grid">
          <section className="card mr-history" aria-labelledby="hist-title">
            <h2 id="hist-title">
              <Layers size={22} className="side-icon" /> Review History
            </h2>

            <div className="mr-tabs" role="tablist">
              {[
                { k: 'all', label: 'All', icon: null },
                { k: 'approved', label: 'Approved', icon: CircleCheck },
                { k: 'edited', label: 'Edited', icon: Pencil },
                { k: 'rejected', label: 'Rejected', icon: CircleX },
              ].map(({ k, label, icon: Icon }) => (
                <button
                  key={k}
                  role="tab"
                  aria-selected={tab === k}
                  className={`mr-tab mr-tab--${k}${tab === k ? ' is-on' : ''}`}
                  onClick={() => setTab(k)}
                >
                  {Icon && <Icon size={14} />} {label} ({tabCount[k] ?? 0})
                </button>
              ))}
            </div>

            <div className="mr-filters">
              <Select
                label="Subject"
                value={subject}
                onChange={setSubject}
                options={[{ key: 'all', label: 'All Subjects' }, ...(data?.subjects ?? []).map((x) => ({ key: x, label: x }))]}
              />
              <Select label="Time range" icon={Calendar} value={range} onChange={setRange} options={RANGES} />
              <label className="mr-search">
                <Search size={15} />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search by question ID, topic or issue..."
                  aria-label="Search reviews"
                />
              </label>
            </div>

            <div className="mr-table-wrap">
              <table className="mr-table">
                <thead>
                  <tr>
                    <th>Question</th>
                    <th>Issue Reported</th>
                    <th>AI Verdict</th>
                    <th>Your Decision</th>
                    <th>Reviewed On</th>
                    <th aria-label="View" />
                  </tr>
                </thead>
                <tbody>
                  {data && rows.length === 0 && (
                    <tr>
                      <td colSpan={6} className="mr-empty">
                        {data.rows.length === 0 ? (
                          <>
                            You haven't decided any cases yet. Every Approve, Edit or Reject you make will appear here.
                            <button className="link" onClick={() => navigate('/queue')}>
                              Start reviewing <ArrowRight size={14} />
                            </button>
                          </>
                        ) : (
                          'No reviews match these filters.'
                        )}
                      </td>
                    </tr>
                  )}
                  {rows.map((r, i) => {
                    const D = DECISION[r.decision]
                    const V = r.aiVerdict
                    return (
                      <tr key={`${r.questionId}-${r.at}-${i}`} className={r.superseded ? 'is-old' : ''}>
                        <td>
                          <button className="mr-qid" onClick={() => navigate(`/case/${r.questionId}`)}>
                            {r.displayId}
                          </button>
                          <span className="mr-topic">
                            {r.subject} · {r.chapter}
                          </span>
                        </td>
                        <td className="mr-issue">
                          {r.issue}
                          {r.superseded && <span className="mr-reopened">Reopened later</span>}
                        </td>
                        <td>
                          <span className={`mr-pill mr-pill--${V.tone}`}>
                            {V.tone === 'ok' ? (
                              <CircleCheck size={13} />
                            ) : V.tone === 'warn' ? (
                              <TriangleAlert size={13} />
                            ) : (
                              <CircleX size={13} />
                            )}
                            {V.label} ({V.confidence}%)
                          </span>
                        </td>
                        <td>
                          <span className={`mr-pill mr-pill--d-${D.tone}`} title={r.detail}>
                            <D.icon size={13} /> {D.label}
                          </span>
                        </td>
                        <td className="mr-when">
                          <time dateTime={r.at}>{when(r.at)}</time>
                        </td>
                        <td>
                          <button className="mr-view" onClick={() => navigate(`/case/${r.questionId}`)}>
                            View <ArrowRight size={14} />
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {error && <p className="error">Couldn't reach the server. Retrying…</p>}
          </section>

          <aside className="mr-side">
            <section className="card mr-impact" aria-labelledby="impact-title">
              <h2 id="impact-title">
                <Target size={22} className="mr-impact-icon" /> Your Impact
              </h2>
              <ul>
                <li>
                  <CircleCheck size={18} fill="#2fb45b" color="#fff" />
                  <span>
                    <b>{im.questionsFixed ?? 0}</b> question{im.questionsFixed === 1 ? '' : 's'} fixed
                  </span>
                </li>
                <li>
                  <Users size={18} color="#1d5ee0" />
                  <span>
                    <b>{im.reportsResolved ?? 0}</b> student report{im.reportsResolved === 1 ? '' : 's'} resolved
                  </span>
                </li>
                <li>
                  <ShieldCheck size={18} color="#f08a1c" />
                  <span>
                    <b>{im.autoFixesChecked ?? 0}</b> AI auto-fix{im.autoFixesChecked === 1 ? '' : 'es'} double-checked
                  </span>
                </li>
              </ul>
            </section>
            <img className="mr-art" src={art} alt="A happy teacher celebrating at her laptop" width="584" height="604" />
          </aside>
        </div>
      </div>
    </Shell>
  )
}
