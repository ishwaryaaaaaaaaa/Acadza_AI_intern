import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft,
  Camera,
  Building2,
  Pencil,
  UserRound,
  Mail,
  IdCard,
  Trash2,
} from 'lucide-react'
import Shell from '../components/Shell.jsx'
import { errText } from '../api.js'
import { useSettings } from '../settings.jsx'
import art from '../assets/profile-illustration.webp'
import './Profile.css'

/** Shrink a chosen photo in the browser (256 px, JPEG) so only a small image is ever stored. */
function shrink(file) {
  return new Promise((resolve, reject) => {
    if (!/^image\/(png|jpeg|webp)$/.test(file.type)) return reject(new Error('Choose a PNG, JPEG or WebP image.'))
    const img = new Image()
    img.onload = () => {
      const s = 256
      const c = document.createElement('canvas')
      c.width = c.height = s
      const k = Math.max(s / img.width, s / img.height) // cover-crop to a square
      const w = img.width * k
      const h = img.height * k
      c.getContext('2d').drawImage(img, (s - w) / 2, (s - h) / 2, w, h)
      URL.revokeObjectURL(img.src)
      resolve(c.toDataURL('image/jpeg', 0.86))
    }
    img.onerror = () => reject(new Error("That file couldn't be read as an image."))
    img.src = URL.createObjectURL(file)
  })
}

function Avatar({ settings, size = 80 }) {
  const initial = (settings.displayName || 'F').trim().charAt(0).toUpperCase()
  return settings.photo ? (
    <img className="pf-avatar" src={settings.photo} alt="" width={size} height={size} />
  ) : (
    <span className="pf-avatar pf-avatar--initial" style={{ width: size, height: size, fontSize: size * 0.42 }}>
      {initial}
    </span>
  )
}

const FIELDS = [
  { k: 'displayName', label: 'Full Name', icon: UserRound, placeholder: 'e.g. Dr. Ishwarya Rao' },
  { k: 'email', label: 'Email', icon: Mail, placeholder: 'name@school.edu', type: 'email' },
  { k: 'department', label: 'Department', icon: Building2, placeholder: 'e.g. Physics' },
  { k: 'designation', label: 'Designation', icon: IdCard, placeholder: 'e.g. Assistant Professor' },
]

export default function Profile() {
  const { settings, save } = useSettings()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(settings)
  const [msg, setMsg] = useState(null)
  const fileRef = useRef(null)

  useEffect(() => {
    if (!editing) setDraft(settings)
  }, [settings, editing])
  useEffect(() => {
    if (!msg) return
    const t = setTimeout(() => setMsg(null), 3500)
    return () => clearTimeout(t)
  }, [msg])

  const saveProfile = async () => {
    try {
      const patch = Object.fromEntries(FIELDS.map((f) => [f.k, draft[f.k]]).filter(([k, v]) => v !== settings[k]))
      if (Object.keys(patch).length) await save(patch)
      setEditing(false)
      setMsg({ ok: true, text: 'Profile saved.' })
    } catch (e) {
      setMsg({ ok: false, text: errText(e) })
    }
  }

  const onPhoto = async (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    try {
      await save({ photo: await shrink(f) })
      setMsg({ ok: true, text: 'Photo updated.' })
    } catch (err) {
      setMsg({ ok: false, text: errText(err) })
    }
  }

  const show = (k) => settings[k] || <span className="pf-unset">Not set</span>

  return (
    <Shell sideArt>
      <div className="pf">
        <Link to="/settings" className="pf-back">
          <ArrowLeft size={15} /> Back to Settings
        </Link>
        <h1>My Profile</h1>
        <p className="pf-sub">
          Your Acadza Check account details.
          <svg className="pf-swoosh" viewBox="0 0 120 10" preserveAspectRatio="none" aria-hidden="true">
            <path d="M2 7 C 35 2, 85 1, 118 4" />
          </svg>
        </p>

        <section className="pf-hero">
          <div className="pf-photo">
            <Avatar settings={settings} />
            <button className="pf-cam" onClick={() => fileRef.current?.click()} aria-label="Change profile photo">
              <Camera size={15} />
            </button>
            {settings.photo && (
              <button className="pf-cam pf-cam--del" onClick={() => save({ photo: '' })} aria-label="Remove profile photo">
                <Trash2 size={13} />
              </button>
            )}
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={onPhoto} />
          </div>
          <div className="pf-who">
            <h2>{settings.displayName}</h2>
            <p>{settings.email || <span className="pf-unset">No email added</span>}</p>
            <p className="pf-dept">
              <Building2 size={16} /> {settings.department ? `${settings.department} Department` : <span className="pf-unset">No department added</span>}
            </p>
          </div>
          <img className="pf-art" src={art} alt="" width="600" height="592" />
        </section>

        <section className="card pf-info">
          <header>
            <h2>Profile Information</h2>
            {!editing ? (
              <button className="pf-btn pf-btn--outline" onClick={() => setEditing(true)}>
                <Pencil size={15} /> Edit
              </button>
            ) : (
              <span className="pf-edit-actions">
                <button
                  className="pf-btn"
                  onClick={() => {
                    setEditing(false)
                    setDraft(settings)
                  }}
                >
                  Cancel
                </button>
                <button className="pf-btn pf-btn--primary" onClick={saveProfile}>
                  Save
                </button>
              </span>
            )}
          </header>
          <dl>
            {FIELDS.map(({ k, label, icon: Icon, placeholder, type }) => (
              <div key={k} className="pf-row">
                <dt>
                  <Icon size={18} strokeWidth={1.8} /> {label}
                </dt>
                <dd>
                  {editing ? (
                    <input
                      type={type || 'text'}
                      value={draft[k] ?? ''}
                      placeholder={placeholder}
                      maxLength={k === 'displayName' ? 40 : 60}
                      onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))}
                    />
                  ) : (
                    show(k)
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </section>

        {msg && (
          <div className={`toast ${msg.ok ? '' : 'toast--bad'}`} role="status">
            {msg.text}
          </div>
        )}
      </div>
    </Shell>
  )
}
