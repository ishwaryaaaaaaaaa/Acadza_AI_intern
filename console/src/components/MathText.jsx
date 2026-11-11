import { Fragment, useMemo } from 'react'
import { Lock } from 'lucide-react'
import MathHtml from './MathHtml.jsx'

/** Plain text in which math blocks appear as "[M1: latex]" (the form the AI and the safe editor work on).
 *  Each block is shown as the real, rendered MathML in a locked chip, so people see symbols, never LaTeX. */
export default function MathText({ text, math = {}, className }) {
  const parts = useMemo(() => {
    const markers = Object.entries(math).map(([id, m]) => ({ id, m, s: `[${id}: ${m.latex}]` }))
    const out = []
    let rest = text || ''
    while (rest) {
      let best = null
      for (const mk of markers) {
        const i = rest.indexOf(mk.s)
        if (i >= 0 && (!best || i < best.i)) best = { ...mk, i }
      }
      if (!best) {
        out.push({ t: rest })
        break
      }
      if (best.i) out.push({ t: rest.slice(0, best.i) })
      out.push({ id: best.id, mathml: best.m.mathml })
      rest = rest.slice(best.i + best.s.length)
    }
    return out
  }, [text, math])

  return (
    <span className={`mathtext ${className || ''}`}>
      {parts.map((p, i) =>
        p.mathml ? (
          <span key={i} className="mchip" title={`${p.id}: math is locked and cannot be edited here`} contentEditable={false}>
            <MathHtml as="span" html={p.mathml} />
            <Lock size={10} className="mchip-lock" aria-hidden="true" />
          </span>
        ) : (
          <Fragment key={i}>{p.t}</Fragment>
        ),
      )}
    </span>
  )
}
