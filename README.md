# edh-budget-brewer

Generate a Magic: The Gathering Commander (EDH) decklist from two inputs: a
**commander** and a **dollar budget**.

Existing tools can show you cheap cards for a commander. This one solves the
harder question — assembling a *complete, legal, playable 100-card deck* that
comes in under a price target, with a sane mana base, enough ramp, enough
interaction, and a reasonable curve.

## Status

Early scaffolding. Nothing works yet. See the
[issues](https://github.com/husomichael/edh-budget-brewer/issues) for the build
plan.

## How it works

Deckbuilding to a budget is a **multi-constraint knapsack problem**: maximize
total synergy subject to a dollar budget *and* deck-construction quotas.

```
Input: commander, budget B

1. Resolve commander -> color identity, legality
2. Candidate pool = EDHREC recommendations (cached locally), joined
   against local Scryfall rows for price / cmc / type / oracle text
3. Filter: commander-legal, color identity subset of commander's, not banned
4. Score each card: blend of inclusion rate and synergy
      (inclusion alone -> generic staples; synergy alone -> cute jank)
5. Classify into roles from type line + oracle text:
      land / ramp / draw / spot removal / sweeper / recursion /
      protection / wincon / synergy
6. Reserve lands first (~36 slots; basics are free, nonbasics eat budgets)
7. Fill remaining ~62 slots against role quotas, greedy by score-per-dollar
8. Repair pass: spend leftover budget on upgrades; evict the worst
   score-per-dollar cards if over budget
9. Output: decklist, total price, curve histogram, role counts
```

### The part that makes it worth building

**Marginal upgrade path.** Solve at `B`, then at `B + $25`, `B + $50`,
`B + $100`, and diff the results. That yields an *ordered purchase sequence* —
"the best next $18 you can spend on this deck is this card" — which no existing
tool provides.

**Own-it-already pricing.** Cards already in your collection are priced at `$0`,
so "build me a $50 deck" means "the best deck for this commander using what I
own plus $50 of new cards."

## Expectations

Generated decks land roughly 80% of the way there. The optimizer cannot read
your commander and infer that your specific build wants sacrifice outlets over
+1/+1 counters. Treat the output as a strong first draft, not a finished deck.

## Stack

- **Backend:** Django + Django REST Framework (Python 3.13)
- **Database:** PostgreSQL
- **Frontend:** React

## Data sources and attribution

Card data, legalities, and prices come from
[**Scryfall**](https://scryfall.com), via their public bulk data endpoints.
Scryfall is not affiliated with this project. Prices are provided by Scryfall
and sourced from TCGplayer and Cardmarket; they are updated daily and are
indicative only.

Deck recommendation data comes from [**EDHREC**](https://edhrec.com). EDHREC
does not publish a documented public API, and this project is not affiliated
with or endorsed by them. Accordingly it:

- caches every response locally and refreshes no more than weekly,
- rate-limits requests and sends an identifying `User-Agent`,
- never redistributes or republishes their data,
- degrades to Scryfall's `edhrec_rank` field if their endpoints change.

This is a personal, non-commercial tool.

## Legal

Unofficial Fan Content permitted under the Wizards of the Coast Fan Content
Policy. Not approved or endorsed by Wizards. Portions of the materials used are
property of Wizards of the Coast LLC. Magic: The Gathering is a trademark of
Wizards of the Coast.
