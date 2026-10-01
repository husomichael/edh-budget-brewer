import { useState } from 'react'
import { ROLE_ORDER, dollars, pricedLabel, roleLabel } from '../format'
import type { Brew, DeckCard } from '../types'
import { CardRow } from './CardRow'
import { ManaCurve } from './ManaCurve'

export function DeckResults({ brew }: { brew: Brew }) {
  const [copied, setCopied] = useState(false)

  const grouped = new Map<string, DeckCard[]>()
  for (const card of brew.spells) {
    const list = grouped.get(card.role) ?? []
    list.push(card)
    grouped.set(card.role, list)
  }

  async function copy() {
    await navigator.clipboard.writeText(brew.text_decklist)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const landCount = brew.lands.reduce((n, c) => n + c.quantity, 0)

  return (
    <div className="results">
      <header className="results-header">
        <div>
          <h2>{brew.commander.name}</h2>
          <p className="muted">
            {brew.card_count} cards &middot; {landCount} lands
            {pricedLabel(brew.priced_at) && (
              <>
                {' '}
                &middot;{' '}
                <span title="Prices come from Scryfall and are refreshed nightly. Indicative only — your local market will differ.">
                  {pricedLabel(brew.priced_at)}
                </span>
              </>
            )}
          </p>
        </div>
        <button type="button" className="primary" onClick={copy}>
          {copied ? 'Copied' : 'Copy decklist'}
        </button>
      </header>

      <div className="summary">
        <div className={brew.over_budget ? 'total over' : 'total'}>
          <span className="total-value">{dollars(brew.total_cents)}</span>
          <span className="muted">
            of {dollars(brew.budget_cents)}
            {brew.over_budget && ' — over budget'}
          </span>
        </div>
        <dl className="breakdown">
          <div>
            <dt>Spells</dt>
            <dd>{dollars(brew.spell_cents)}</dd>
          </div>
          <div>
            <dt>Lands</dt>
            <dd>{dollars(brew.land_cents)}</dd>
          </div>
          {brew.owned_count > 0 && (
            <>
              <div>
                <dt>Retail value</dt>
                <dd>{dollars(brew.retail_cents)}</dd>
              </div>
              <div>
                <dt>From collection</dt>
                <dd>{brew.owned_count} cards</dd>
              </div>
            </>
          )}
        </dl>
        <ManaCurve curve={brew.curve} />
      </div>

      <TierNotice brew={brew} />

      {brew.warnings.length > 0 && (
        <ul className="warnings">
          {brew.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}

      <div className="roles">
        {ROLE_ORDER.map((role) => {
          const cards = grouped.get(role)
          if (!cards?.length) return null
          const subtotal = cards.reduce((n, c) => n + c.price_cents, 0)
          return (
            <section key={role} className="role-group">
              <h3>
                {roleLabel(role)}
                <span className="muted small">
                  {cards.length} &middot; {dollars(subtotal)}
                </span>
              </h3>
              <ul className="card-list">
                {[...cards]
                  .sort((a, b) => b.price_cents - a.price_cents)
                  .map((card) => (
                    <CardRow key={card.oracle_id} card={card} />
                  ))}
              </ul>
            </section>
          )
        })}

        <section className="role-group">
          <h3>
            Lands
            <span className="muted small">
              {landCount} &middot; {dollars(brew.land_cents)}
            </span>
          </h3>
          <ul className="card-list">
            {brew.lands.map((card) => (
              <CardRow key={card.oracle_id} card={card} />
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}

/** Which engine built this deck. A tier 0 deck is not synergy-aware, and
 *  hiding that would let the user mistake it for a tuned list. */
function TierNotice({ brew }: { brew: Brew }) {
  const generic = brew.tier === 0 || brew.tier_label.includes('no themes')
  return (
    <div className={generic ? 'tier-notice generic' : 'tier-notice'}>
      <strong>Tier {brew.tier}</strong> &middot; {brew.tier_label}
      {generic && (
        <p className="muted small">
          This deck is ranked by global EDH popularity, so it is legal and
          playable in the right colors but is not tailored to this commander.
          Commanders whose rules text does not imply a strategy fall back to
          this automatically.
        </p>
      )}
    </div>
  )
}
