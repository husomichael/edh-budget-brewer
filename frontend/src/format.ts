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
