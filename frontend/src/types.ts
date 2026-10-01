// Mirrors the API's wire format. Worth keeping typed: the brew response is
// nontrivial and will keep changing as the optimizer evolves.

export type Role =
  | 'ramp'
  | 'draw'
  | 'spot_removal'
  | 'sweeper'
  | 'protection'
  | 'recursion'
  | 'tutor'
  | 'wincon'
  | 'synergy'
  | 'land'

export interface Commander {
  oracle_id: string
  name: string
  type_line: string
  color_identity: string[]
  image_uri: string
  edhrec_rank: number | null
  price_cents: number | null
}

export interface DeckCard {
  oracle_id: string
  name: string
  quantity: number
  price_cents: number
  retail_cents: number
  is_owned: boolean
  /** Name of an assembled deck already using this card, if any. */
  locked_in: string
  cmc: number
  mana_cost: string
  type_line: string
  image_uri: string
  role: Role
  secondary_role: Role | ''
  score: number
}

export interface UpgradeStep {
  label: string
  budget_cents: number
  total_cents: number
  score: number
  score_delta: number
  spend_delta_cents: number
  cost_per_point: number | null
  is_no_limit: boolean
  added: DeckCard[]
  removed: DeckCard[]
}

export interface UpgradePath {
  base_total_cents: number
  base_score: number
  best_next_buys: DeckCard[]
  steps: UpgradeStep[]
}

export interface Brew {
  commander: Pick<
    Commander,
    'oracle_id' | 'name' | 'type_line' | 'color_identity' | 'image_uri'
  >
  budget_cents: number
  total_cents: number
  retail_cents: number
  land_cents: number
  spell_cents: number
  over_budget: boolean
  card_count: number
  /** 0 = popularity only, 1 = commander-text synergy, 2 = pasted EDHREC data. */
  tier: number
  tier_label: string
  curve: Record<string, number>
  role_counts: Partial<Record<Role, number>>
  role_coverage: Partial<Record<Role, number>>
  warnings: string[]
  owned_count: number
  spells: DeckCard[]
  lands: DeckCard[]
  text_decklist: string
  upgrade_path?: UpgradePath
}

export interface BrewRequest {
  commander_oracle_id: string
  budget_cents: number
  strategy: 'auto' | 'tier0' | 'tier1'
  owned_free: boolean
  lands: number
  include_upgrade_path: boolean
}

export interface ImportSummary {
  parsed: number
  created: number
  updated: number
  unresolved: string[]
  detail: string
}

export interface ApiError {
  detail: string
  code?: string
  minimum_cents?: number
}
