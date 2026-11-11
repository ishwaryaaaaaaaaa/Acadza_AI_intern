import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Settings as Cog,
  Bell,
  SlidersHorizontal,
  Lock,
  Sun,
  Monitor,
  Moon,
  Download,
  RotateCcw,
  ShieldCheck,
  Check,
  TriangleAlert,
} from 'lucide-react'
import Shell from '../components/Shell.jsx'
import { api } from '../api.js'
import { useSettings } from '../settings.jsx'
import art from '../assets/settings-illustration.webp'
import './Settings.css'

const TABS = [
  { key: 'general', label: 'General', icon: Cog },
  { key: 'notifications', label: 'Notifications', icon: Bell },
  { key: 'review', label: 'Review Preferences', icon: SlidersHorizontal },
  { key: 'account', label: 'Account & Security', icon: Lock },
]

const REPAIR_LABEL = {
  answer_form: 'Unit / answer form',
  answer_key: 'Answer key',
  exam_reference: 'Exam tag in text',
  markup_leak: 'Raw code in text',
  noise: 'Stray text',
  notation: 'Lost symbol',
  option_repair: 'Missing / blank option',
  solution_fix: 'Solution error',
  solution_missing: 'Missing solution',
  spelling: 'Spelling',
  stem_data: 'Missing data in question',
  type_mismatch: 'Wrong question type',
  diagram: 'Missing figure',
  identical_options: 'Identical options',
  syllabus: 'Out of syllabus',
  unsound: 'No valid option',
  wrong_chapter: 'Wrong chapter',
  wrong_question: "Solution doesn't match",
}

function Row({ label, hint, children }) {
  return (
    <div className="st-row">
      <div className="st-label">
        <span>{label}</span>
        {hint && <small>{hint}</small>}
      </div>
      <div className="st-control">{children}</div>
    </div>
  )
}

function Toggle({ on, onChange, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      className={`st-toggle${on ? ' is-on' : ''}`}
      onClick={() => onChange(!on)}
    >
      <span />
    </button>
  )
}

export default function Settings() {
  const { settings, engine, save, loaded } = useSettings()
  const [params, setParams] = useSearchParams()
  const tab = TABS.some((t) => t.key === params.get('tab')) ? params.get('tab') : 'general'
  const [draft, setDraft] = useState(settings)
  const [status, setStatus] = useState(null) // {ok, msg}
  const [saving, setSaving] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)

  useEffect(() => setDraft(settings), [settings])
  useEffect(() => {
    if (!status) return
    const t = setTimeout(() => setStatus(null), 3500)
    return () => clearTimeout(t)
  }, [status])

  const dirty = useMemo(() => Object.keys(settings).some((k) => draft[k] !== settings[k]), [draft, settings])
  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }))

  const onSave = async () => {
    setSaving(true)
    try {
      const changed = Object.fromEntries(Object.keys(draft).filter((k) => draft[k] !== settings[k]).map((k) => [k, draft[k]]))
      await save(changed)
      setStatus({ ok: true, msg: 'Settings saved.' })
    } catch (e) {
      let msg = e.message
      try {
        msg = JSON.parse(e.message.replace(/^\d+ /, '')).detail
      } catch {
        /* keep raw */
      }
      setStatus({ ok: false, msg })
    } finally {
      setSaving(false)
    }
  }

  const exportLog = async () => {
    const data = await api('/audit-log')
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `acadza-check-audit-log-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    setStatus({ ok: true, msg: `Exported ${data.events.length} audit entries.` })
  }

  const resetDemo = async () => {
    await api('/admin/reset', { method: 'POST' })
    setConfirmReset(false)
    setStatus({ ok: true, msg: 'Demo data reset: every faculty decision was cleared. Settings were kept.' })
  }

  return (
    <Shell sideArt>
      <div className="st">
        <header className="st-head">
          <h1>
            <Cog size={30} strokeWidth={2.2} className="st-head-icon" /> Settings
          </h1>
          <p className="st-sub">
            Manage your account, notifications, and review preferences.
            <svg className="st-swoosh" viewBox="0 0 120 10" preserveAspectRatio="none" aria-hidden="true">
              <path d="M2 7 C 35 2, 85 1, 118 4" />
            </svg>
          </p>
        </header>

        <section className="card st-card">
          <nav className="st-tabs" aria-label="Settings sections">
            {TABS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                className={`st-tab${tab === key ? ' is-on' : ''}`}
                aria-current={tab === key ? 'page' : undefined}
                onClick={() => setParams(key === 'general' ? {} : { tab: key }, { replace: true })}
              >
                <Icon size={20} strokeWidth={1.9} /> {label}
              </button>
            ))}
          </nav>

          <div className="st-panel">
            {tab === 'general' && (
              <>
                <h2>General</h2>
                <Row label="Display Name" hint="Shown in the greeting and on every decision in the audit log.">
                  <input
                    className="st-input"
                    value={draft.displayName}
                    maxLength={40}
                    onChange={(e) => set('displayName', e.target.value)}
                  />
                </Row>
                <Row label="Email" hint="Edit your contact details in My Profile.">
                  <Link to="/profile" className="st-input st-input--locked">
                    <span>{settings.email || 'Not set'}</span>
                    <Lock size={14} />
                  </Link>
                </Row>
                <Row label="Theme">
                  <div className="st-seg" role="radiogroup" aria-label="Theme">
                    {[
                      { k: 'light', label: 'Light', icon: Sun },
                      { k: 'auto', label: 'Auto', icon: Monitor },
                      { k: 'dark', label: 'Dark', icon: Moon },
                    ].map(({ k, label, icon: Icon }) => (
                      <button
                        key={k}
                        role="radio"
                        aria-checked={draft.theme === k}
                        className={`st-seg-btn${draft.theme === k ? ' is-on' : ''}`}
                        onClick={() => set('theme', k)}
                      >
                        <Icon size={16} /> {label}
                      </button>
                    ))}
                  </div>
                </Row>
              </>
            )}

            {tab === 'notifications' && (
              <>
                <h2>Notifications</h2>
                <Row label="Bell dot" hint="Red dot on the bell while cases are waiting for your decision.">
                  <Toggle label="Bell dot" on={draft.notifyBellDot} onChange={(v) => set('notifyBellDot', v)} />
                </Row>
                <Row label="Decision confirmations" hint="A short message after each Approve, Edit or Reject.">
                  <Toggle label="Decision confirmations" on={draft.notifyToasts} onChange={(v) => set('notifyToasts', v)} />
                </Row>
              </>
            )}

            {tab === 'review' && (
              <>
                <h2>Review Preferences</h2>
                <Row label="Default queue order" hint="How the Review Queue is sorted when you open it.">
                  <select className="st-input" value={draft.defaultSort} onChange={(e) => set('defaultSort', e.target.value)}>
                    <option value="priority">Priority (harm to students)</option>
                    <option value="reports">Most reports</option>
                    <option value="confidence">AI confidence</option>
                    <option value="oldest">Oldest report</option>
                  </select>
                </Row>
                <Row label="Show auto-fixed cases" hint="List fixes the AI already applied, so you can confirm or undo them.">
                  <Toggle label="Show auto-fixed cases" on={draft.showAutoFixed} onChange={(v) => set('showAutoFixed', v)} />
                </Row>
                <Row label="Require a reason to reject" hint="Reject can't be saved without a short note for the audit log.">
                  <Toggle label="Require a reason to reject" on={draft.requireRejectNote} onChange={(v) => set('requireRejectNote', v)} />
                </Row>
                <Row label="Keyboard shortcuts" hint="A approve · E edit · R reject · Enter save & next · S skip">
                  <Toggle label="Keyboard shortcuts" on={draft.keyboardShortcuts} onChange={(v) => set('keyboardShortcuts', v)} />
                </Row>
                {engine && (
                  <div className="st-engine">
                    <p className="st-engine-title">
                      <ShieldCheck size={16} /> AI safety rules (read-only)
                    </p>
                    <p>
                      The AI applies a fix by itself only above <b>{Math.round(engine.floor * 100)}%</b> confidence (
                      <b>{Math.round(engine.floorKey * 100)}%</b> for answer keys, which also need two independent solvers to
                      agree). These are enforced in the engine's code and change only when the engine is re-run.
                    </p>
                    <p className="st-engine-sub">Always sent to a teacher, never auto-applied:</p>
                    <div className="st-chips">
                      {engine.humanOnly.map((k) => (
                        <span key={k} className="st-chip">
                          {REPAIR_LABEL[k] || k}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {tab === 'account' && (
              <>
                <h2>Account &amp; Security</h2>
                <Row label="Profile" hint="Your name, contact details and photo live in My Profile.">
                  <Link to="/profile" className="st-btn">
                    My Profile
                  </Link>
                </Row>
                <Row label="Audit log" hint="Every engine and faculty action, oldest first, as a JSON file.">
                  <button className="st-btn" onClick={exportLog}>
                    <Download size={15} /> Export audit log
                  </button>
                </Row>
                <Row label="Reset demo data" hint="Clears every faculty decision and restores the AI engine's results.">
                  {!confirmReset ? (
                    <button className="st-btn st-btn--danger" onClick={() => setConfirmReset(true)}>
                      <RotateCcw size={15} /> Reset…
                    </button>
                  ) : (
                    <div className="st-confirm">
                      <span>
                        <TriangleAlert size={15} /> This can't be undone.
                      </span>
                      <button className="st-btn st-btn--danger" onClick={resetDemo}>
                        Yes, reset
                      </button>
                      <button className="st-btn" onClick={() => setConfirmReset(false)}>
                        Cancel
                      </button>
                    </div>
                  )}
                </Row>
              </>
            )}

            {tab !== 'account' && (
              <footer className="st-foot">
                {status && (
                  <span className={`st-status ${status.ok ? 'ok' : 'bad'}`}>
                    {status.ok ? <Check size={15} /> : <TriangleAlert size={15} />} {status.msg}
                  </span>
                )}
                <button className="btn btn-ghost st-discard" disabled={!dirty || saving} onClick={() => setDraft(settings)}>
                  Discard
                </button>
                <button className="btn btn-primary" disabled={!dirty || saving || !loaded} onClick={onSave}>
                  {saving ? 'Saving…' : 'Save Changes'}
                </button>
              </footer>
            )}
            {tab === 'account' && status && (
              <footer className="st-foot">
                <span className={`st-status ${status.ok ? 'ok' : 'bad'}`}>
                  {status.ok ? <Check size={15} /> : <TriangleAlert size={15} />} {status.msg}
                </span>
              </footer>
            )}
          </div>

          <img className="st-art" src={art} alt="" width="776" height="592" />
        </section>
      </div>
    </Shell>
  )
}
