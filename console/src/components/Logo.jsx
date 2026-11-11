// Solid cog + wordmark, as in the mock's top-left corner.
function cogPath(teeth = 8, rOuter = 11.6, rInner = 8.9, rHole = 4.4, cx = 12, cy = 12) {
  const pts = []
  const step = (Math.PI * 2) / teeth
  for (let i = 0; i < teeth; i++) {
    const a = i * step - Math.PI / 2
    const w = step * 0.22 // half-width of a tooth top
    const b = step * 0.3 // half-width of a tooth root
    pts.push([a - b, rInner], [a - w, rOuter], [a + w, rOuter], [a + b, rInner])
  }
  const d = pts
    .map(([ang, r], i) => `${i ? 'L' : 'M'}${(cx + r * Math.cos(ang)).toFixed(2)} ${(cy + r * Math.sin(ang)).toFixed(2)}`)
    .join(' ')
  const hole = `M${cx + rHole} ${cy} A${rHole} ${rHole} 0 1 0 ${cx - rHole} ${cy} A${rHole} ${rHole} 0 1 0 ${cx + rHole} ${cy}Z`
  return `${d} Z ${hole}`
}

export function Cog({ size = 32, color = 'currentColor', className }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d={cogPath()} fill={color} fillRule="evenodd" />
    </svg>
  )
}

export default function Logo({ size = 32 }) {
  return (
    <span className="logo">
      <Cog size={size} />
      <span className="logo-word">ACADZA</span>
    </span>
  )
}
