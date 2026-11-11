import DOMPurify from 'dompurify'
import { useMemo } from 'react'

// Acadza stores questions as HTML with inline MathML. Browsers render MathML natively, so we only sanitise
// (scripts, event handlers and the like are stripped) and render it as-is. Humans always see the real MathML.
export default function MathHtml({ html, className, as: Tag = 'div' }) {
  const clean = useMemo(
    () =>
      DOMPurify.sanitize(html || '', {
        USE_PROFILES: { html: true, mathMl: true },
        FORBID_ATTR: ['style'], // inline colours from the CMS fight the console's theme
      }),
    [html],
  )
  return <Tag className={`mathhtml ${className || ''}`} dangerouslySetInnerHTML={{ __html: clean }} />
}
