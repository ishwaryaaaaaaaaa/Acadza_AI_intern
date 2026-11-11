import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { Bell, ChevronDown, Home, Layers, CircleCheck, BarChart3, Settings, UserRound } from 'lucide-react'
import { Cog } from './Logo.jsx'
import { useLive } from '../api.js'
import { useSettings } from '../settings.jsx'
import sidebarArt from '../assets/sidebar-illustration.webp'
import './Shell.css'

function BrandMark() {
  return (
    <Link to="/" className="brandmark" aria-label="Acadza Check home">
      <Cog size={40} className="brandmark-cog" />
      <span className="brandmark-text">
        <span className="brandmark-acadza">ACADZA</span>
        <span className="brandmark-check">CHECK</span>
      </span>
    </Link>
  )
}

function useOutside(ref, onOut) {
  useEffect(() => {
    const h = (e) => ref.current && !ref.current.contains(e.target) && onOut()
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [ref, onOut])
}

function TopBar({ dash }) {
  const [open, setOpen] = useState(null)
  const ref = useRef(null)
  const navigate = useNavigate()
  useOutside(ref, () => setOpen(null))
  const pending = dash?.needsDecision ?? 0
  const { settings } = useSettings()
  const initial = (settings.displayName || 'F').trim().charAt(0).toUpperCase()

  return (
    <div className="topbar" ref={ref}>
      <button
        className="icon-btn"
        aria-label={`Notifications: ${pending} case${pending === 1 ? '' : 's'} need a decision`}
        onClick={() => setOpen(open === 'bell' ? null : 'bell')}
      >
        <Bell size={22} strokeWidth={2} />
        {pending > 0 && settings.notifyBellDot && <span className="bell-dot" />}
      </button>
      <button className="avatar-btn" aria-label="Account menu" onClick={() => setOpen(open === 'me' ? null : 'me')}>
        {settings.photo ? (
          <img className="avatar avatar--photo" src={settings.photo} alt="" />
        ) : (
          <span className="avatar">{initial}</span>
        )}
        <ChevronDown size={18} strokeWidth={2.2} />
      </button>

      {open === 'bell' && (
        <div className="menu menu--bell" role="menu">
          <p className="menu-title">Notifications</p>
          {pending > 0 ? (
            <button
              className="menu-item"
              onClick={() => {
                setOpen(null)
                navigate('/dashboard?filter=decision')
              }}
            >
              <strong>{pending}</strong> case{pending === 1 ? '' : 's'} waiting for your decision
            </button>
          ) : (
            <p className="menu-empty">Nothing needs your decision right now.</p>
          )}
        </div>
      )}
      {open === 'me' && (
        <div className="menu menu--me" role="menu">
          <p className="menu-title">{settings.displayName}</p>
          <Link className="menu-item" to="/profile" onClick={() => setOpen(null)}>
            My Profile
          </Link>
          <Link className="menu-item" to="/settings" onClick={() => setOpen(null)}>
            Settings
          </Link>
        </div>
      )}
    </div>
  )
}

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: Home },
  { to: '/queue', label: 'Review Queue', icon: Layers, badge: true, also: '/case/' },
  { to: '/reviews', label: 'My Reviews', icon: CircleCheck },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
]

export default function Shell({ children, sideArt = false }) {
  const { data: dash } = useLive('/dashboard')
  const { pathname } = useLocation()
  return (
    <div className="shell">
      <aside className="sidebar">
        <BrandMark />
        <span className="role-pill">
          <UserRound size={17} strokeWidth={2} /> Faculty
        </span>
        <nav className="nav" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, badge, also }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `nav-item${isActive || (also && pathname.startsWith(also)) ? ' is-active' : ''}`
              }
            >
              <Icon size={18} strokeWidth={1.9} />
              <span>{label}</span>
              {badge && dash?.underReview > 0 && <span className="nav-badge">{dash.underReview}</span>}
            </NavLink>
          ))}
          <hr className="nav-rule" />
          <NavLink to="/settings" className={({ isActive }) => `nav-item${isActive ? ' is-active' : ''}`}>
            <Settings size={18} strokeWidth={1.9} />
            <span>Settings</span>
          </NavLink>
        </nav>
        {sideArt && <img className="sidebar-art" src={sidebarArt} alt="" width="488" height="444" />}
        <span className="sidebar-wash" aria-hidden="true" />
      </aside>
      <div className="shell-main">
        <TopBar dash={dash} />
        {children}
      </div>
    </div>
  )
}
