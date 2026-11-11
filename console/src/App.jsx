import { useEffect } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import Landing from './pages/Landing.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Review from './pages/Review.jsx'
import MyReviews from './pages/MyReviews.jsx'
import Analytics from './pages/Analytics.jsx'
import Settings from './pages/Settings.jsx'
import Profile from './pages/Profile.jsx'
import Shell from './components/Shell.jsx'
import { api } from './api.js'

// "Review Queue" in the sidebar starts reviewing at the most urgent open case.
function QueueStart() {
  const navigate = useNavigate()
  useEffect(() => {
    api('/queue').then((r) => {
      const ids = r.rows.map((x) => x.questionId)
      if (ids.length) navigate(`/case/${ids[0]}`, { replace: true, state: { sequence: ids } })
      else navigate('/dashboard', { replace: true, state: { toast: 'The review queue is empty. Nice work!' } })
    })
  }, [navigate])
  return (
    <Shell>
      <p style={{ padding: 40, color: '#4a4d63' }}>Opening the most urgent case…</p>
    </Shell>
  )
}

// Pages not designed yet render inside the real shell, so navigation works end to end.
function NotYet() {
  const { pathname } = useLocation()
  return (
    <Shell>
      <div style={{ padding: '60px 28px' }}>
        <p style={{ fontWeight: 800, fontSize: 20, color: 'var(--navy)', margin: 0 }}>This page is next.</p>
        <p style={{ color: '#4a4d63' }}>
          <code>{pathname}</code> will be built from its design image.
        </p>
        <Link to="/dashboard" style={{ color: '#1d5ee0', fontWeight: 600 }}>
          ← Back to dashboard
        </Link>
      </div>
    </Shell>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/queue" element={<QueueStart />} />
        <Route path="/case/:qid" element={<Review />} />
        <Route path="/reviews" element={<MyReviews />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="*" element={<NotYet />} />
      </Routes>
    </BrowserRouter>
  )
}
