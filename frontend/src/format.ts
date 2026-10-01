/** Money is integer cents everywhere; format only at the edge. */
export function dollars(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

export function roleLabel(role: string): string {
  return role.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/** Display order for role sections; roughly how a deck is read. */
export const ROLE_ORDER = [
  'ramp',
  'draw',
  'spot_removal',
  'sweeper',
  'protection',
  'recursion',
  'tutor',
  'wincon',
  'synergy',
] as const

const COLOR_NAMES: Record<string, string> = {
  W: 'White',
  U: 'Blue',
  B: 'Black',
  R: 'Red',
  G: 'Green',
}

export function colorIdentityLabel(identity: string[]): string {
  if (identity.length === 0) return 'Colorless'
  return identity.map((c) => COLOR_NAMES[c] ?? c).join(' / ')
}

/**
 * When this deck was priced.
 *
 * Prices move daily and a brew response can be cached for 24h or arrive via
 * a share URL solved months ago, so the result has to say how old it is
 * rather than implying it is current.
 */
export function pricedLabel(iso: string | undefined): string {
  if (!iso) return ''
  const then = new Date(iso)
  if (Number.isNaN(then.getTime())) return ''

  const now = new Date()
  if (then.toDateString() === now.toDateString()) return 'priced today'

  const days = Math.floor((now.getTime() - then.getTime()) / 86_400_000)
  if (days <= 1) return 'priced yesterday'
  if (days < 30) return `priced ${days} days ago`
  return `priced ${then.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })}`
}
