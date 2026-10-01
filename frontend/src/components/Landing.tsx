/**
 * First-screen pitch for the demo (#28).
 *
 * The empty state used to assume you already knew what the tool was for,
 * which for a showcase is the whole page wasted. The two examples are the
 * argument: the same commander and budget with and without synergy produces
 * fifty-odd Goblins versus a handful, which demonstrates what the scoring
 * actually does rather than claiming it.
 *
 * The counts are deliberately not written down here -- they move with card
 * prices, and a stale number in the copy would be a lie. Click and see.
 */
interface Props {
  onExample: (slug: string, budgetDollars: number, tier0: boolean) => void
  busy: boolean
}

export function Landing({ onExample, busy }: Props) {
  return (
    <div className="landing">
      <h2>A commander and a budget in, a legal 100-card deck out.</h2>

      <p>
        Pick a commander, name a dollar figure, and get a complete Commander
        deck that costs no more than that &mdash; a real mana base, enough ramp
        and interaction, and a sane curve.
      </p>

      <h3>Why this is harder than sorting by price</h3>
      <p>
        It is a constrained knapsack, and the constraints are the whole
        problem. Sort by card quality and you get a pile of expensive spells
        with no lands. Sort by quality-per-dollar and you get ninety-nine
        one-mana cards. A deck has to satisfy colour identity, a land count,
        role quotas and singleton rules <em>at the same time</em> as hitting
        the budget.
      </p>

      <h3>See it both ways</h3>
      <p className="muted small">
        Same commander, same $75. The difference is whether scoring reads the
        commander&rsquo;s text or just global popularity.
      </p>
      <div className="examples">
        <button
          type="button"
          className="primary"
          disabled={busy}
          onClick={() => onExample('krenko-mob-boss', 75, false)}
        >
          Krenko, Mob Boss at $75
          <span className="muted small">With commander synergy</span>
        </button>
        <button
          type="button"
          className="secondary"
          disabled={busy}
          onClick={() => onExample('krenko-mob-boss', 75, true)}
          title="Ranks by global EDH popularity only, ignoring what the commander does."
        >
          &hellip; and without
          <span className="muted small">Popularity only &mdash; count the Goblins</span>
        </button>
      </div>

      <h3>What to expect</h3>
      <p className="muted small">
        Decks land around 80% of the way there. This is a strong first draft
        and a good shopping list, not a finished list &mdash; expect to swap a
        handful of cards once you see it.
      </p>
    </div>
  )
}
