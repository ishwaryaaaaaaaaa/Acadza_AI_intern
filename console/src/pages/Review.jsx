import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  TriangleAlert,
  FileText,
  Sparkles,
  CircleCheck,
  CircleX,
  CircleHelp,
  Users,
  Quote,
  Pencil,
  RotateCcw,
  ChevronDown,
  Check,
} from 'lucide-react'
import Shell from '../components/Shell.jsx'
import MathHtml from '../components/MathHtml.jsx'
import Editor from '../components/Editor.jsx'
import ChatPanel from '../components/ChatPanel.jsx'
import MathText from '../components/MathText.jsx'
import LatexText from '../components/LatexText.jsx'
import { api, timeAgo } from '../api.js'
import { useSettings } from '../settings.jsx'
import art from '../assets/review-illustration.webp'
import './Review.css'

const TYPE_LABEL = { scq: 'Single correct', mcq: 'Multiple correct', integerQuestion: 'Integer' }
const FLAG_LABEL = {
  instruction: 'Instruction aimed at the system, ignored',
  gibberish: 'Unclear comment',
  vague: 'Vague comment',
}

function errText(e) {
  try {
    return JSON.parse(e.message.replace(/^\d+ /, '')).detail
  } catch {
    return e.message
  }
}

function actionCopy(d) {
  const open = d.status === 'needs_decision' || d.status === 'auto_applied'
  const p = d.proposal
  if (!open) return null
  if (d.status === 'auto_applied') {
    return {
      approve: { title: 'Approve Fix', sub: p.kind === 'key' ? `Keep the corrected key (${p.suggestedKey})` : 'Keep the applied fix', enabled: true },
      reject: { title: 'Reject', sub: p.kind === 'key' ? `Restore the old key (${p.currentKey})` : 'Undo the fix, restore original', enabled: true },
    }
  }
  if (p.kind === 'key')
    return {
      approve: { title: 'Approve Fix', sub: `Update to suggested answer (${p.suggestedKey})`, enabled: true },
      reject: { title: 'Reject', sub: `Keep the current version (${p.currentKey})`, enabled: true },
    }
  if (p.kind === 'text')
    return {
      approve: { title: 'Approve Fix', sub: 'Apply the suggested edit', enabled: true },
      reject: { title: 'Reject', sub: 'Keep the current version', enabled: true },
    }
  return {
    approve: { title: 'Approve Fix', sub: 'No automatic fix here: use Edit', enabled: false },
    reject: { title: 'Reject', sub: 'Not a real problem: keep as is', enabled: true },
  }
}

// Long model working is cut at a sentence boundary; the full text is one click away.
function SolverWork({ s }) {
  const [open, setOpen] = useState(false)
  const text = s.working || ''
  const LIMIT = 260
  const cut = (() => {
    if (text.length <= LIMIT) return text
    const end = text.slice(0, LIMIT).search(/[.!?](?=\s)[^.!?]*$/)
    return text.slice(0, end > 80 ? end + 1 : LIMIT).trim()
  })()
  const long = cut.length < text.length
  return (
    <div className="solver-item">
      <p className="solver-line">
        <b>
          {s.name} → {s.noAnswer ? 'no valid option' : s.answer}
        </b>
        {s.selfContradicts && <span className="solver-warn">contradicts its own working</span>}
      </p>
      <p className="solver-text">
        <LatexText text={open || !long ? text : `${cut} …`} />
        {long && (
          <button className="solver-more" onClick={() => setOpen((o) => !o)}>
            {open ? 'Show less' : 'Show full working'}
          </button>
        )}
      </p>
    </div>
  )
}

function Options({ q, highlight, doubtful }) {
  if (!q.options) return null
  return (
    <ol className="opts">
      {['A', 'B', 'C', 'D'].map((l) => {
        const has = l in q.options
        const on = highlight.includes(l)
        return (
          <li
            key={l}
            className={`opt${on ? (doubtful ? ' is-doubt' : ' is-correct') : ''}${has ? '' : ' is-missing'}`}
          >
            <span className="opt-letter">
              {on && !doubtful ? <CircleCheck size={20} fill="#2fb45b" color="#fff" /> : l}
            </span>
            {has ? (
              <MathHtml className="opt-body" html={q.options[l]} />
            ) : (
              <span className="opt-body opt-absent">Option {l} is missing from the record</span>
            )}
            {on && doubtful && <span className="opt-doubt">Stored key, in doubt</span>}
          </li>
        )
      })}
    </ol>
  )
}

function Proposal({ d }) {
  const p = d.proposal
  if (p.kind === 'key') {
    return (
      <div className="keyband">
        {p.currentType !== p.suggestedType && (
          <div className="keyband-row">
            <span>Question type</span>
            <span className="kpill kpill--old">{TYPE_LABEL[p.currentType]}</span>
            <ArrowRight size={18} />
            <span>Suggested</span>
            <span className="kpill kpill--new">{TYPE_LABEL[p.suggestedType]}</span>
          </div>
        )}
        <div className="keyband-row">
          <span>Current Answer Key</span>
          <span className="kpill kpill--old">{p.currentKey}</span>
          <ArrowRight size={18} />
          <span>Suggested Answer Key</span>
          <span className="kpill kpill--new">{p.suggestedKey}</span>
        </div>
      </div>
    )
  }
  if (p.kind === 'text') {
    return (
      <div className="diff">
        <p className="diff-title">
          Proposed change in the {p.field} {d.status === 'auto_applied' && <em>(already applied)</em>}
        </p>
        <p className="diff-line">
          <MathText text={p.context?.before} math={d.math?.original} />
          <del>{p.find}</del>
          <ins>{p.replace || '∅'}</ins>
          <MathText text={p.context?.after} math={d.math?.original} />
        </p>
      </div>
    )
  }
  return (
    <div className="diff diff--none">
      <p className="diff-title">No automatic fix</p>
      <p className="diff-line">{d.evidence}</p>
    </div>
  )
}

export default function Review() {
  const { qid } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [d, setD] = useState(null)
  const [error, setError] = useState(null)
  const [choice, setChoice] = useState(null) // approve | edit | reject
  const [editChanges, setEditChanges] = useState(null)
  const [editing, setEditing] = useState(false)
  const [showAllReports, setShowAllReports] = useState(false)
  const [showSolution, setShowSolution] = useState(false)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState(location.state?.toast || null)
  const [note, setNote] = useState('')
  const { settings } = useSettings()
  const [sequence, setSequence] = useState(location.state?.sequence || null)
  const [chatOpen, setChatOpen] = useState(() => {
    try {
      return sessionStorage.getItem('acadza-chat-open') === '1'
    } catch {
      return false
    }
  })
  const toggleChat = (v) => {
    setChatOpen(v)
    try {
      sessionStorage.setItem('acadza-chat-open', v ? '1' : '0')
    } catch {
      /* ignore */
    }
  }

  const load = useCallback(async () => {
    try {
      setD(await api(`/cases/${qid}`))
      setError(null)
    } catch (e) {
      setError(errText(e))
    }
  }, [qid])

  useEffect(() => {
    setD(null)
    setChoice(null)
    setEditChanges(null)
    setEditing(false)
    setShowAllReports(false)
    setShowSolution(false)
    setNote('')
    load()
  }, [load])

  // Without a list handed over from the dashboard, walk the live queue in priority order.
  useEffect(() => {
    if (sequence) return
    api('/queue').then((r) => {
      const ids = r.rows.map((x) => x.questionId)
      setSequence(ids.includes(qid) ? ids : [qid, ...ids])
    })
  }, [sequence, qid])

  // same route, new :qid — the component is reused, so pick up the message handed over on navigation
  useEffect(() => {
    if (location.state?.toast) setToast(location.state.toast)
  }, [location.key, location.state])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3500)
    return () => clearTimeout(t)
  }, [toast])

  const pos = sequence ? sequence.indexOf(qid) : -1
  const go = useCallback(
    (delta, extra = {}) => {
      if (!sequence) return
      const i = sequence.indexOf(qid) + delta
      if (i >= 0 && i < sequence.length) navigate(`/case/${sequence[i]}`, { state: { sequence, ...extra } })
      else navigate('/dashboard', { state: extra })
    },
    [sequence, qid, navigate],
  )

  const copy = d ? actionCopy(d) : null
  const isOpen = !!copy
  const needNote = choice === 'reject' && settings.requireRejectNote
  const canSave =
    isOpen &&
    !saving &&
    (choice === 'approve' || (choice === 'reject' && (!needNote || note.trim())) || (choice === 'edit' && editChanges))

  const save = useCallback(async () => {
    if (!canSave) return
    setSaving(true)
    try {
      const body = { action: choice, changes: choice === 'edit' ? editChanges : null, note: note.trim() }
      const r = await api(`/cases/${qid}/action`, { method: 'POST', body: JSON.stringify(body) })
      go(+1, settings.notifyToasts ? { toast: `${r.event.title}: ${r.event.detail}` } : {})
    } catch (e) {
      setToast(errText(e))
    } finally {
      setSaving(false)
    }
  }, [canSave, choice, editChanges, qid, go, note, settings.notifyToasts])

  const reopen = async () => {
    try {
      await api(`/cases/${qid}/action`, { method: 'POST', body: JSON.stringify({ action: 'reopen' }) })
      if (settings.notifyToasts) setToast('Case reopened for review')
      load()
    } catch (e) {
      setToast(errText(e))
    }
  }

  // Keyboard: A approve · E edit · R reject · S skip · Enter save · ←/→ previous/next
  useEffect(() => {
    if (!settings.keyboardShortcuts) return
    const h = (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName) || e.metaKey || e.ctrlKey) return
      const k = e.key.toLowerCase()
      if (k === 'a' && copy?.approve.enabled) setChoice('approve')
      else if (k === 'r' && copy) setChoice('reject')
      else if (k === 'e' && copy) {
        setChoice('edit')
        setEditing(true)
      } else if (k === 's') go(+1)
      else if (k === 'enter') save()
      else if (k === 'arrowright') go(+1)
      else if (k === 'arrowleft') go(-1)
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [copy, go, save, settings.keyboardShortcuts])

  const highlight = useMemo(() => {
    if (!d) return []
    if (d.proposal.kind === 'key' && d.status === 'needs_decision') return d.proposal.suggestedLetters
    return d.question.answerLetters
  }, [d])

  const reports = d ? (showAllReports ? d.reports : d.reports.slice(0, 2)) : []

  return (
    <Shell>
      <div className={`review${chatOpen ? ' has-chat' : ''}`}>
        <header className="rv-head">
          <Link to="/dashboard" className="rv-back">
            <ArrowLeft size={15} /> Review Queue
          </Link>
          <div className="rv-titlerow">
            <h1>Review Question — {d?.displayId ?? '…'}</h1>
            <div className="rv-pager">
              <button aria-label="Previous question" disabled={pos <= 0} onClick={() => go(-1)}>
                <ChevronLeft size={18} />
              </button>
              <span>{sequence && pos >= 0 ? `${pos + 1} of ${sequence.length}` : '–'}</span>
              <button aria-label="Next question" disabled={!sequence || pos >= sequence.length - 1} onClick={() => go(+1)}>
                <ChevronRight size={18} />
              </button>
            </div>
            <div className="rv-actions">
              <button
                className={`btn btn-ask${chatOpen ? ' is-on' : ''}`}
                onClick={() => toggleChat(!chatOpen)}
                aria-pressed={chatOpen}
                title="Ask the AI about this question"
              >
                <Sparkles size={16} /> Ask AI
              </button>
              <button className="btn btn-ghost" onClick={() => go(+1)} title="Skip (S)">
                Skip
              </button>
              <button
                className="btn btn-primary"
                disabled={!canSave}
                onClick={save}
                title={canSave ? 'Save & Next (Enter)' : 'Choose Approve, Edit or Reject first'}
              >
                {saving ? 'Saving…' : 'Save & Next'} <ArrowRight size={17} />
              </button>
            </div>
          </div>
        </header>

        {error && <p className="rv-error">Couldn't load this question: {error}</p>}

        {d && !isOpen && (
          <div className="rv-banner">
            <CircleCheck size={18} />
            <span>
              Resolved: <b>{d.status.replace(/_/g, ' ')}</b>
              {d.decidedBy ? ` by ${d.decidedBy}` : ' by the AI check'}
              {d.decidedAt ? ` · ${timeAgo(d.decidedAt)}` : ''}
            </span>
            <button className="btn btn-ghost btn-sm" onClick={reopen}>
              <RotateCcw size={14} /> Reopen
            </button>
          </div>
        )}

        {d && (
          <div className="rv-grid">
            <section className="card rv-question">
              <div className="chips">
                {d.tier && (
                  <span className="chip chip--issue">
                    <TriangleAlert size={16} /> {d.issue}
                  </span>
                )}
                <span className="chip chip--subject">{d.subject}</span>
                <span className="chip chip--reports">
                  <FileText size={15} /> {d.reports.length} report{d.reports.length === 1 ? '' : 's'}
                </span>
                <span className="chip chip--conf">{Math.round(d.confidence * 100)}% confidence</span>
              </div>

              <div className="rv-qhead">
                <h2>Question</h2>
                {d.question.patched && <span className="tag-live">Live version · fix applied</span>}
              </div>
              <MathHtml className="rv-stem" html={d.question.options ? d.question.stemHtml : d.question.fullHtml} />
              <Options
                q={d.question}
                highlight={highlight}
                doubtful={d.repair === 'unsound' || d.confidenceLabel === 'Mixed Signals'}
              />
              {d.question.type === 'integerQuestion' && (
                <p className="int-answer">
                  Answer key: <b>{d.question.answer}</b>
                </p>
              )}

              <Proposal d={d} />

              <button className="rv-solution-toggle" onClick={() => setShowSolution((s) => !s)}>
                <ChevronDown size={16} className={showSolution ? 'rot' : ''} /> {showSolution ? 'Hide' : 'Show'} solution
              </button>
              {showSolution && <MathHtml className="rv-solution" html={d.question.solutionHtml} />}
            </section>

            <div className="rv-side">
              <section className="card rv-ai">
                <div className="rv-ai-body">
                  <h2>
                    <Sparkles size={22} className="spark" fill="#f6a514" color="#f6a514" /> AI Check
                    <span className={`conf-tag conf-tag--${d.confidenceLabel.split(' ')[0].toLowerCase()}`}>
                      {d.confidenceLabel}
                    </span>
                  </h2>
                  <ul className="checks">
                    {d.checks.map((c, i) => (
                      <li key={i} className={c.ok === false ? 'is-bad' : c.ok === null ? 'is-note' : ''}>
                        {c.ok === true && <CircleCheck size={18} fill="#2fb45b" color="#fff" />}
                        {c.ok === false && <CircleX size={18} color="#e5484d" />}
                        {c.ok === null && <CircleHelp size={18} color="#b4560a" />}
                        <span>{c.text}</span>
                      </li>
                    ))}
                  </ul>
                  {d.solverWork.length > 0 && (
                    <details className="solver">
                      <summary>How the solvers worked it out</summary>
                      {d.solverWork.map((s, i) => (
                        <SolverWork key={i} s={s} />
                      ))}
                    </details>
                  )}
                </div>
                <img className="rv-art" src={art} alt="" width="544" height="552" />
              </section>

              <section className="card rv-reports">
                <header className="rv-reports-head">
                  <h2>
                    <Users size={22} className="side-icon" /> Student Reports ({d.reports.length})
                  </h2>
                  {d.reports.length > 2 || d.reports.some((r) => r.reply) ? (
                    <button className="link" onClick={() => setShowAllReports((s) => !s)}>
                      {showAllReports ? 'Show less' : 'View All'} <ArrowRight size={15} />
                    </button>
                  ) : null}
                </header>
                <ul className="quotes">
                  {reports.map((r) => (
                    <li key={r.reportId}>
                      <span className="quote-icon">
                        <Quote size={13} fill="#3b6fe0" color="#3b6fe0" />
                      </span>
                      <div className="quote-body">
                        <p>“{r.comment}”</p>
                        {r.flag && <span className={`flag flag--${r.flag}`}>{FLAG_LABEL[r.flag]}</span>}
                        {showAllReports && (
                          <p className="reply">
                            <b>Reply:</b> {r.reply}
                          </p>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
                {!showAllReports && d.reports[0]?.reply && (
                  <div className="reply-preview">
                    <span>Reply students will see</span>
                    <p>{d.reports[0].reply}</p>
                  </div>
                )}
              </section>
            </div>
          </div>
        )}

        {d && copy && (
          <div className="rv-choices" role="radiogroup" aria-label="Decision">
            <button
              role="radio"
              aria-checked={choice === 'approve'}
              disabled={!copy.approve.enabled}
              className={`choice choice--approve${choice === 'approve' ? ' is-on' : ''}`}
              onClick={() => setChoice('approve')}
            >
              <CircleCheck size={28} />
              <span>
                <b>{copy.approve.title}</b>
                <small>{copy.approve.sub}</small>
              </span>
              {choice === 'approve' && <Check className="choice-tick" size={16} />}
            </button>
            <button
              role="radio"
              aria-checked={choice === 'edit'}
              className={`choice choice--edit${choice === 'edit' ? ' is-on' : ''}`}
              onClick={() => {
                setChoice('edit')
                setEditing(true)
              }}
            >
              <Pencil size={26} />
              <span>
                <b>Edit Manually</b>
                <small>{editChanges ? 'Edit checked and ready to save' : 'Modify question or answer key'}</small>
              </span>
              {choice === 'edit' && <Check className="choice-tick" size={16} />}
            </button>
            <button
              role="radio"
              aria-checked={choice === 'reject'}
              className={`choice choice--reject${choice === 'reject' ? ' is-on' : ''}`}
              onClick={() => setChoice('reject')}
            >
              <CircleX size={28} />
              <span>
                <b>{copy.reject.title}</b>
                <small>{copy.reject.sub}</small>
              </span>
              {choice === 'reject' && <Check className="choice-tick" size={16} />}
            </button>
          </div>
        )}
        {d && copy && choice === 'reject' && (
          <label className={`reject-note${needNote && !note.trim() ? ' is-required' : ''}`}>
            <span>
              Reason for rejecting{' '}
              {needNote ? <b>(required)</b> : <small>(optional, saved in the audit log)</small>}
            </span>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              maxLength={300}
              placeholder="e.g. Options are correct; the student misread option C."
            />
          </label>
        )}
        {d && copy && settings.keyboardShortcuts && (
          <p className="kbd-hint">
            Shortcuts: <kbd>A</kbd> approve · <kbd>E</kbd> edit · <kbd>R</kbd> reject · <kbd>Enter</kbd> save &amp; next ·{' '}
            <kbd>S</kbd> skip
          </p>
        )}

        {editing && d && (
          <div className="editor-backdrop" onMouseDown={(e) => e.target === e.currentTarget && setEditing(false)}>
            <Editor
              data={d}
              onClose={() => setEditing(false)}
              onReady={(c) => {
                setEditChanges(c)
                if (c) {
                  setChoice('edit')
                  setTimeout(() => setEditing(false), 700)
                }
              }}
            />
          </div>
        )}

        {toast && (
          <div className="toast" role="status">
            {toast}
          </div>
        )}
        {chatOpen && d && <ChatPanel qid={qid} displayId={d.displayId} onClose={() => toggleChat(false)} />}
      </div>
    </Shell>
  )
}
