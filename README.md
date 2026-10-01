# edh-budget-brewer

Generate a Magic: The Gathering Commander (EDH) decklist from two inputs: a
**commander** and a **dollar budget**.

Existing tools can show you cheap cards for a commander. This one solves the
harder question — assembling a *complete, legal, playable 100-card deck* that
comes in under a price target, with a sane mana base, enough ramp, enough
interaction, and a reasonable curve.

## Status

Phase 1 done: Django runs on Postgres, the full Scryfall card database syncs
locally (~34.5k cards in under 10 seconds), and cards are browsable in the
Django admin. The optimizer itself is not built yet. See the
[issues](https://github.com/husomichael/edh-budget-brewer/issues) for the
build plan.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env        # then set SECRET_KEY and check DATABASE_URL
createdb edh_budget_brewer

.venv/bin/python manage.py migrate
.venv/bin/python manage.py sync_cards     # downloads ~25 MB from Scryfall
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

Then browse the card database at `/admin/cards/card/`.

**Note on the Postgres port.** On the machine this was built on, Homebrew's
`postgresql@16` listens on **5433**, not the default 5432 — port 5432 is a
separate instance running as the `postgres` user with password auth. If
`migrate` cannot connect, check which instance is actually running:

```bash
brew services list
grep '^port' /opt/homebrew/var/postgresql@16/postgresql.conf
```

`psql --version` reports the *client* version, which may not match the running
server.

### sync_cards

```bash
manage.py sync_cards              # download if stale, then upsert
manage.py sync_cards --force      # re-download even if current
manage.py sync_cards --dry-run    # parse and report, write nothing
manage.py sync_cards --limit 500  # first 500 cards only, for testing
```

Re-running is idempotent. The command reads Scryfall's `bulk-data` index, pulls
the gzipped JSONL `oracle_cards` file (one row per logical card), and upserts on
`oracle_id`.

## How it works

Deckbuilding to a budget is a **multi-constraint knapsack problem**: maximize
total synergy subject to a dollar budget *and* deck-construction quotas.

```
Input: commander, budget B

1. Resolve commander -> color identity, legality
2. Candidate pool = every commander-legal card, scored by the active
   tier (see below), joined against local Scryfall rows for
   price / cmc / type / oracle text
3. Filter: commander-legal, color identity subset of commander's, not banned
4. Score each card via the active scoring tier, normalized to 0..1
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

### Scoring tiers

Scoring is pluggable, so the tool works for any commander without requiring
anyone's data but Scryfall's.

| Tier | Source | Works for | Quality |
|---|---|---|---|
| 0 | `edhrec_rank` + color identity + role quotas | any commander | legal, playable, generic |
| 1 | synergy inferred from the commander's own oracle text | any commander | thematically coherent |
| 2 | EDHREC percentages pasted in by the user, per commander | one commander, on demand | crowd-validated |

**Tier 1 is the default** and needs no input beyond the commander's name. A
commander's rules text usually states what the deck wants — Krenko says
"Goblin", Muldrotha says "graveyard", Omnath says "land" — and that text is
already in the local database. It works well for tribal and mechanic-themed
commanders, poorly for abstract value commanders, and not at all for combo
commanders whose decks are crowd knowledge rather than card text.

**Tier 2** is optional polish for those weak cases. Generated decks always
report which tier produced them.

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

`edhrecRank` and `edhrecSaltiness` are also available from
[**MTGJSON**](https://mtgjson.com), which is MIT licensed.

**This project does not scrape EDHREC.** [EDHREC](https://edhrec.com) publishes
no API and no data export, and their Terms of Use prohibit automated queries, so
there is no sanctioned programmatic path to their data. The optimizer is
therefore built on data this project is plainly licensed to use, and EDHREC
participates only through Tier 2 below, where a user supplies data they fetched
themselves in their own browser.

This is a personal, non-commercial tool. It is not affiliated with or endorsed
by Scryfall, EDHREC, Space Cow Media, or Wizards of the Coast.

## Legal

Unofficial Fan Content permitted under the Wizards of the Coast Fan Content
Policy. Not approved or endorsed by Wizards. Portions of the materials used are
property of Wizards of the Coast LLC. Magic: The Gathering is a trademark of
Wizards of the Coast.
