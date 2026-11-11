import { useState } from 'react'
import { X, Check, TriangleAlert } from 'lucide-react'
import { api } from '../api.js'
import MathText from './MathText.jsx'

/** Manual edit panel. Text edits use the same safe mechanism as the AI:
 *  "find" must occur exactly once in plain text, and math blocks [Mk: …] can never be touched. */
export default function Editor({ data, onClose, onReady }) {
  const q = data.question
  const [answer, setAnswer] = useState(q.type === 'mcq' ? q.answerLetters : q.answer)
  const [type, setType] = useState(q.type)
  const [field, setField] = useState('question')
  const [find, setFind] = useState(data.proposal?.kind === 'text' ? data.proposal.find : '')
  const [replace, setReplace] = useState(data.proposal?.kind === 'text' ? data.proposal.replace : '')
  const [chapter, setChapter] = useState(q.chapter || '')
  const [status, setStatus] = useState(null) // {ok, msg}
  const [busy, setBusy] = useState(false)

  const changes = () => {
    const c = []
    if (find.trim()) c.push({ field, find, replace })
    if (type !== q.type) c.push({ field: 'questionType', value: type })
    const ansChanged =
      type === 'mcq' ? JSON.stringify([...answer].sort()) !== JSON.stringify(q.answerLetters) : String(answer) !== q.answer
    if (ansChanged || type !== q.type) c.push({ field: 'answer', value: type === 'mcq' ? [...answer].sort() : String(answer) })
    if (chapter.trim() && chapter.trim() !== (q.chapter || '')) c.push({ field: 'chapter', value: chapter.trim() })
    return c
  }

  const check = async () => {
    const c = changes()
    if (!c.length) {
      setStatus({ ok: false, msg: 'Nothing changed yet.' })
      return
    }
    setBusy(true)
    try {
      await api(`/cases/${data.questionId}/preview`, { method: 'POST', body: JSON.stringify({ changes: c }) })
      setStatus({ ok: true, msg: 'Edit is valid. Press Save & Next to apply it.' })
      onReady(c)
    } catch (e) {
      const msg = (() => {
        try {
          return JSON.parse(e.message.replace(/^\d+ /, '')).detail
        } catch {
          return e.message
        }
      })()
      setStatus({ ok: false, msg })
      onReady(null)
    } finally {
      setBusy(false)
    }
  }

  const letters = ['A', 'B', 'C', 'D']
  return (
    <div className="editor" role="dialog" aria-label="Edit manually">
      <header className="editor-head">
        <h3>Edit manually</h3>
        <button className="icon-btn" onClick={onClose} aria-label="Close editor">
          <X size={18} />
        </button>
      </header>

      <div className="editor-grid">
        <label className="ed-field">
          <span>Question type</span>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="scq">Single correct</option>
            <option value="mcq">Multiple correct</option>
            <option value="integerQuestion">Integer</option>
          </select>
        </label>

        <div className="ed-field">
          <span>Answer key</span>
          {type === 'integerQuestion' ? (
            <input value={answer} onChange={(e) => setAnswer(e.target.value)} inputMode="decimal" />
          ) : (
            <div className="ed-keys">
              {letters.map((l) => {
                const on = type === 'mcq' ? (Array.isArray(answer) ? answer : [answer]).includes(l) : answer === l
                return (
                  <button
                    key={l}
                    type="button"
                    className={`ed-key${on ? ' is-on' : ''}`}
                    onClick={() =>
                      setAnswer((a) => {
                        if (type !== 'mcq') return l
                        const arr = Array.isArray(a) ? a : [a].filter(Boolean)
                        return arr.includes(l) ? arr.filter((x) => x !== l) : [...arr, l]
                      })
                    }
                  >
                    {l}
                  </button>
                )
              })}
            </div>
          )}
        </div>

        <label className="ed-field">
          <span>Chapter</span>
          <input value={chapter} onChange={(e) => setChapter(e.target.value)} />
        </label>
      </div>

      <div className="ed-text">
        <div className="ed-tabs">
          {['question', 'solution'].map((f) => (
            <button key={f} className={`ed-tab${field === f ? ' is-on' : ''}`} onClick={() => setField(f)}>
              {f === 'question' ? 'Question text' : 'Solution text'}
            </button>
          ))}
        </div>
        <p className="ed-hint">
          Copy the exact words to change into <b>Find</b>. Math is shown in grey chips and is locked, so edit the words
          around it.
        </p>
        <div className="ed-source">
          <MathText text={data.editable[field]} math={data.math?.[field]} />
        </div>
        <div className="ed-pair">
          <label className="ed-field">
            <span>Find (exact, once)</span>
            <input value={find} onChange={(e) => setFind(e.target.value)} placeholder="e.g. plexux" />
          </label>
          <label className="ed-field">
            <span>Replace with</span>
            <input value={replace} onChange={(e) => setReplace(e.target.value)} placeholder="e.g. plexus" />
          </label>
        </div>
      </div>

      <footer className="editor-foot">
        {status && (
          <span className={`ed-status ${status.ok ? 'ok' : 'bad'}`}>
            {status.ok ? <Check size={15} /> : <TriangleAlert size={15} />} {status.msg}
          </span>
        )}
        <button className="btn btn-primary" onClick={check} disabled={busy}>
          {busy ? 'Checking…' : 'Check edit'}
        </button>
      </footer>
    </div>
  )
}
