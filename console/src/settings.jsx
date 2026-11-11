import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api.js'

// Mirrors server/settings.py DEFAULTS so the UI renders before the first fetch returns.
export const DEFAULT_SETTINGS = {
  displayName: 'Faculty',
  theme: 'light',
  notifyBellDot: true,
  notifyToasts: true,
  defaultSort: 'priority',
  showAutoFixed: true,
  requireRejectNote: false,
  keyboardShortcuts: true,
  email: '',
  department: '',
  designation: '',
  photo: '',
}

const Ctx = createContext({ settings: DEFAULT_SETTINGS, engine: null, save: async () => {}, loaded: false })

function readCachedTheme() {
  try {
    return localStorage.getItem('acadza-theme') || 'light'
  } catch {
    return 'light'
  }
}

/** light | dark | auto → applied to <html data-theme>. "auto" follows the OS and keeps following it. */
function applyTheme(theme) {
  const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
  const resolved = theme === 'auto' ? (mq?.matches ? 'dark' : 'light') : theme
  document.documentElement.dataset.theme = resolved
  document.documentElement.style.colorScheme = resolved
  try {
    localStorage.setItem('acadza-theme', theme)
  } catch {
    /* storage may be blocked; the server copy is the source of truth */
  }
}

export function SettingsProvider({ children }) {
  const [settings, setSettings] = useState({ ...DEFAULT_SETTINGS, theme: readCachedTheme() })
  const [engine, setEngine] = useState(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    api('/settings')
      .then((r) => {
        setSettings(r.settings)
        setEngine(r.engine)
      })
      .catch(() => {})
      .finally(() => setLoaded(true))
  }, [])

  useEffect(() => {
    applyTheme(settings.theme)
    if (settings.theme !== 'auto') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const on = () => applyTheme('auto')
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [settings.theme])

  const save = useCallback(async (patch) => {
    const r = await api('/settings', { method: 'PUT', body: JSON.stringify(patch) })
    setSettings(r.settings)
    setEngine(r.engine)
    return r.settings
  }, [])

  return <Ctx.Provider value={{ settings, engine, save, loaded }}>{children}</Ctx.Provider>
}

export const useSettings = () => useContext(Ctx)
