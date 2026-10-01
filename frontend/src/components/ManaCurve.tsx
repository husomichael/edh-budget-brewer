import type { Brew } from '../types'

/** Mana-value histogram of the nonland cards. */
export function ManaCurve({ curve }: { curve: Brew['curve'] }) {
  const entries = Object.entries(curve)
  if (entries.length === 0) return null
  const peak = Math.max(...entries.map(([, n]) => n))

  return (
    <div className="curve">
      {entries.map(([bucket, count]) => (
        <div className="curve-col" key={bucket}>
          <span className="curve-count">{count}</span>
          <div
            className="curve-bar"
            style={{ height: `${Math.round((count / peak) * 100)}%` }}
            role="img"
            aria-label={`${count} cards at mana value ${bucket}`}
          />
          <span className="curve-label">{bucket}</span>
        </div>
      ))}
    </div>
  )
}
