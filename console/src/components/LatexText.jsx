import { useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

// Model-written text (solver working) uses LaTeX between $…$, $$…$$, \(…\) or \[…\].
// Render those spans as real math; leave everything else as plain text.
const MATH = /\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$|\\\(([\s\S]+?)\\\)|\\\[([\s\S]+?)\\\]/g

// Light formatting for chat answers: **bold**, "- " bullets and line breaks. Runs on already-escaped HTML.
function richen(html) {
  return html
    .replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>')
    .split('\n')
    .map((line) => (/^\s*[-*]\s+/.test(line) ? `<span class="li">${line.replace(/^\s*[-*]\s+/, '')}</span>` : line))
    .join('<br/>')
    .replace(/(<br\/>){3,}/g, '<br/><br/>')
}

export default function LatexText({ text, className, rich = false }) {
  const html = useMemo(() => {
    const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
    let out = ''
    let last = 0
    const src = text || ''
    for (const m of src.matchAll(MATH)) {
      out += esc(src.slice(last, m.index))
      const tex = m[1] ?? m[2] ?? m[3] ?? m[4]
      const display = m[1] !== undefined || m[4] !== undefined
      try {
        out += katex.renderToString(tex, { throwOnError: false, displayMode: display, output: 'html' })
      } catch {
        out += esc(m[0])
      }
      last = m.index + m[0].length
    }
    const full = out + esc(src.slice(last))
    return rich ? richen(full) : full
  }, [text, rich])
  return <span className={className} dangerouslySetInnerHTML={{ __html: html }} />
}
