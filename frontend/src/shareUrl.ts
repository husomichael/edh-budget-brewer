/**
 * Share URLs (#21).
 *
 * The URL carries the whole deck, because the solver is deterministic:
 * identical input always produces a byte-identical list. So a link needs no
 * database row, no id, and no expiry.
 *
 *   /?commander=krenko-mob-boss&budget=100&strategy=tier1&lands=36
 *
 * `ownedFree` is deliberately NOT in the URL. It prices cards against the
 * sender's collection, so including it would mean the recipient opens the
 * link and gets a different deck than the one that was shared.
 */
import type { BrewSettings } from './components/BrewForm'

export interface ShareParams {
  commander: string
  settings: Partial<BrewSettings>
}

const MIN_BUDGET = 1
const MAX_BUDGET = 1_000_000

/** Read share parameters from a query string, or null if none are present. */
export function parseShareUrl(search: string): ShareParams | null {
  const q = new URLSearchParams(search)
  const commander = q.get('commander')?.trim()
  if (!commander) return null

  const settings: Partial<BrewSettings> = {}

  // Clamped rather than rejected: a hand-edited budget should brew at the
  // nearest sane value, not show an error page.
  const budget = Number(q.get('budget'))
  if (Number.isFinite(budget) && budget > 0) {
    settings.budgetDollars = Math.min(Math.max(budget, MIN_BUDGET), MAX_BUDGET)
  }

  const strategy = q.get('strategy')
  if (strategy === 'tier0') settings.strategy = 'tier0'
  if (strategy === 'tier1' || strategy === 'auto') settings.strategy = 'auto'

  const lands = Number(q.get('lands'))
  if (Number.isInteger(lands) && lands >= 20 && lands <= 48) {
    settings.lands = lands
  }

  if (q.get('upgrades') === '1') settings.includeUpgradePath = true

  return { commander, settings }
}

/** Build the query string for a brew that just succeeded. */
export function buildShareUrl(slug: string, settings: BrewSettings): string {
  const q = new URLSearchParams({
    commander: slug,
    // Whole dollars where possible, so the common case reads as `budget=100`
    // rather than `budget=100.00`.
    budget: String(Number(settings.budgetDollars.toFixed(2))),
    strategy: settings.strategy === 'tier0' ? 'tier0' : 'tier1',
    lands: String(settings.lands),
  })
  if (settings.includeUpgradePath) q.set('upgrades', '1')
  return `?${q}`
}

/**
 * Point the address bar at a brew without adding a history entry.
 *
 * replaceState, not pushState: every budget tweak re-brews, and pushState
 * would make the back button walk through each one instead of leaving the
 * page.
 */
export function syncShareUrl(slug: string, settings: BrewSettings): void {
  window.history.replaceState(null, '', buildShareUrl(slug, settings))
}
