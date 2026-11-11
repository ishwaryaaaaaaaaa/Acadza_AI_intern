import { useEffect, useRef, useState } from 'react'
import { Sparkles, X, SendHorizontal, RotateCcw, TriangleAlert } from 'lucide-react'
import { api, errText } from '../api.js'
import LatexText from './LatexText.jsx'
import './ChatPanel.css'

// Conversations survive moving between cases (and a page refresh) for the session.
const memory = new Map()
const KEY = (qid) => `acadza-chat-${qid}`
function recall(qid) {
  if (memory.has(qid)) return memory.get(qid)
  try {
    const v = JSON.parse(sessionStorage.getItem(KEY(qid)) || '[]')
    return Array.isArray(v) ? v : []
  } catch {
    return []
  }
}
function remember(qid, msgs) {
  memory.set(qid, msgs)
  try {
    sessionStorage.setItem(KEY(qid), JSON.stringify(msgs.slice(-24)))
  } catch {
    /* storage may be blocked; memory copy still works */
  }
}

const SUGGESTIONS = [
  'Why did the AI flag this question?',
  'Solve this question step by step.',
  'Is the stored solution correct?',
  'Draft a short reply to the student.',
]

export default function ChatPanel({ qid, displayId, onClose }) {
  const [msgs, setMsgs] = useState(() => recall(qid))
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const listRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    setMsgs(recall(qid))
    setError(null)
    setInput('')
  }, [qid])
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [msgs, busy])
  useEffect(() => inputRef.current?.focus(), [qid])

  const send = async (text) => {
    const q = (text ?? input).trim()
    if (!q || busy) return
    const next = [...msgs, { role: 'user', content: q }]
    setMsgs(next)
    remember(qid, next)
    setInput('')
    setBusy(true)
    setError(null)
    try {
      const r = await api(`/cases/${qid}/chat`, { method: 'POST', body: JSON.stringify({ messages: next }) })
      const done = [...next, { role: 'assistant', content: r.reply }]
      setMsgs(done)
      remember(qid, done)
    } catch (e) {
      setError(errText(e))
    } finally {
      setBusy(false)
    }
  }

  const clear = () => {
    setMsgs([])
    remember(qid, [])
    setError(null)
  }

  return (
    <aside className="chat" aria-label="Review assistant">
      <header className="chat-head">
        <span className="chat-title">
          <Sparkles size={18} fill="#f6a514" color="#f6a514" /> Ask AI
          <small>about {displayId}</small>
        </span>
        {msgs.length > 0 && (
          <button className="chat-icon" onClick={clear} title="Clear this conversation" aria-label="Clear conversation">
            <RotateCcw size={16} />
          </button>
        )}
        <button className="chat-icon" onClick={onClose} aria-label="Close assistant">
          <X size={18} />
        </button>
      </header>

      <div className="chat-list" ref={listRef}>
        {msgs.length === 0 && (
          <div className="chat-empty">
            <p>
              I can see this question, its key and solution, the AI&apos;s checks and what students wrote. Ask me anything
              about it.
            </p>
            <div className="chat-sugs">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)} disabled={busy}>
                  {s}
                </button>
              ))}
            </div>
            <p className="chat-fine">
              Answers are suggestions. I can't change the question: use Approve, Edit or Reject for that.
            </p>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`msg msg--${m.role}`}>
            {m.role === 'assistant' ? <LatexText text={m.content} rich /> : m.content}
          </div>
        ))}
        {busy && (
          <div className="msg msg--assistant msg--typing" aria-live="polite">
            <span />
            <span />
            <span />
            <em>Thinking it through…</em>
          </div>
        )}
        {error && (
          <div className="chat-error" role="alert">
            <TriangleAlert size={15} /> {error}
          </div>
        )}
      </div>

      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault()
          send()
        }}
      >
        <textarea
          ref={inputRef}
          rows={2}
          value={input}
          maxLength={2000}
          placeholder="Ask about this question…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
        />
        <button className="chat-send" disabled={busy || !input.trim()} aria-label="Send">
          <SendHorizontal size={18} />
        </button>
      </form>
    </aside>
  )
}
