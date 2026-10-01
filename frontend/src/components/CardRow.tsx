import { useState } from 'react'
import { dollars } from '../format'
import type { DeckCard } from '../types'

/** One card line. Hovering reveals the Scryfall image. */
export function CardRow({ card }: { card: DeckCard }) {
  const [hover, setHover] = useState(false)

  return (
    <li
      className="card-row"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <span className="card-qty">
        {card.quantity > 1 ? `${card.quantity}x` : ''}
      </span>
      <span className="card-name">
        {card.name}
        {card.is_owned && <span className="tag owned">owned</span>}
        {card.locked_in && (
          <span className="tag locked" title={`Sleeved in "${card.locked_in}"`}>
            in {card.locked_in}
          </span>
        )}
      </span>
      <span className="card-cost">{card.mana_cost}</span>
      <span className="card-price">
        {card.price_cents === 0 && card.retail_cents > 0 ? (
          <>
            <s className="muted">{dollars(card.retail_cents)}</s> free
          </>
        ) : (
          dollars(card.price_cents)
        )}
      </span>
      {hover && card.image_uri && (
        <img className="card-preview" src={card.image_uri} alt={card.name} />
      )}
    </li>
  )
}
