import { useCallback, useEffect, useRef, useState } from 'react'

export async function api(path, options) {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}

/** Fetch `path`, refresh every `every` ms and whenever the tab regains focus.
 *  Numbers on screen therefore change only when the backend's state changes. */
export function useLive(path, every = 15000) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const alive = useRef(true)

  const load = useCallback(async () => {
    try {
      const d = await api(path)
      if (alive.current) {
        setData(d)
        setError(null)
      }
    } catch (e) {
      if (alive.current) setError(e)
    }
  }, [path])

  useEffect(() => {
    alive.current = true
    load()
    const t = setInterval(load, every)
    const onFocus = () => load()
    window.addEventListener('focus', onFocus)
    return () => {
      alive.current = false
      clearInterval(t)
      window.removeEventListener('focus', onFocus)
    }
  }, [load, every])

  return { data, error, reload: load }
}

export function timeAgo(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} hr${h > 1 ? 's' : ''} ago`
  const d = Math.floor(h / 24)
  return `${d} day${d > 1 ? 's' : ''} ago`
}

/** Turn a thrown API error into the server's human-readable message. */
export function errText(e) {
  try {
    return JSON.parse(e.message.replace(/^\d+ /, '')).detail
  } catch {
    return e.message
  }
}
