# edh-budget-brewer

Generate a Magic: The Gathering Commander (EDH) decklist from two inputs: a
**commander** and a **dollar budget**.

Existing tools can show you cheap cards for a commander. This one solves the
harder question — assembling a *complete, legal, playable 100-card deck* that
comes in under a price target, with a sane mana base, enough ramp, enough
interaction, and a reasonable curve.

## Status

**It generates decks.** `manage.py brew` produces a complete, legal, 100-card
Commander deck within a dollar budget in well under a second.

Working end to end: Scryfall sync, role classification, Tier 0 and Tier 1
scoring, the candidate pool, mana base, the knapsack solver, deck/collection
storage, own-it-already pricing, the marginal upgrade path, a REST API, and a
React frontend. Not yet built: Tier 2 paste import. See the
[issues](https://github.com/husomichael/edh-budget-brewer/issues).

### Try it

```bash
manage.py brew "Krenko, Mob Boss" --budget 75
manage.py brew "Muldrotha, the Gravetide" --budget 200 --format text
manage.py brew "Atraxa, Praetors' Voice" --budget 150 --format json

manage.py brew "Krenko, Mob Boss" --budget 50 --upgrade-path   # what the next $25 buys
manage.py brew "Edgar Markov" --budget 100 --owned-free   # collection is free
manage.py brew "Talrand" --budget 60 --save --name "Budget Drakes"
```

`--format text` emits `1 Card Name` per line, which pastes directly into
Moxfield or Archidekt. Partial commander names work when unambiguous
(`"Muldrotha"`); ambiguous ones list the matches (`"Krenko"` → three).

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

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Vite dev-proxies `/api` to Django on port 8000,
so both servers need to be running and there is no CORS setup to do. Note that
Vite binds IPv6 `[::1]` only, so use `localhost` rather than `127.0.0.1`.

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

### classify_cards

```bash
manage.py classify_cards --report    # role distribution summary
```

Assigns each card a functional role (ramp, draw, removal, sweeper, ...) from
regex over its type line and oracle text, with a curated override table for
cards whose role is not inferable from wording. Separate from `sync_cards`
because the rules get tuned often. Run it after any sync.

### brew

```bash
manage.py brew "<commander>" --budget <dollars> [--lands N] [--format FMT]
```

Solves in ~25-500ms depending on color count. Exits with a clear error naming
the real minimum if the budget cannot produce a legal deck.

| Flag | Effect |
|---|---|
| `--budget` | Dollar target (required) |
| `--strategy` | `auto` (tier 1, default), `tier0`, `tier1` |
| `--upgrade-path` | Also show what the next budget increments would buy |
| `--owned-free` | Price collection cards at $0 |
| `--save` / `--name` | Persist the deck |
| `--lands` | Target land count (default 36) |
| `--format` | `table`, `text`, `json` |

### The upgrade path

`--upgrade-path` solves at `+$25`, `+$50`, `+$100`, `+$250`, and no limit, then
diffs the results into an ordered purchase sequence. Each tier reports **dollars
per point of score gained**, which makes diminishing returns visible:

```
Best next buys, cheapest first:
  $   0.49  Hordeling Outburst
  $   2.86  Goblin Spymaster
  $   4.21  Brash Taunter

+$25  -> $74.57 spent, score 33.9 (+0.9)    $22.93 per point
+$50  -> $99.98 spent, score 34.1 (+0.2)   $121.36 per point
+$250 -> $297.54 spent, score 34.9 (+0.1)  $1269.30 per point
```

Deck selection is **not monotonic** — a tier with more money can differ by more
than one card, because extra budget in one role enables a cheaper reshuffle in
another. So each tier reports a *set* of changes rather than pretending to be a
single-card chain.

**A caveat on that metric.** Score is built from `edhrec_rank`, which is
log-normalized and therefore compresses differences between top cards. The
solver reports a $50 Krenko deck as ~94% as good as an unlimited one, which
overstates how close they are: it cannot see that Kiki-Jiki is *qualitatively*
different from a $1 goblin, only that their popularity ranks are not far apart.
Treat the upgrade path as most trustworthy in the $0–100 range, where the gains
are real and large.

### Own-it-already pricing

`--owned-free` prices cards in your collection at `$0`, so a budget means new
money rather than retail value:

```
Total: $40.00 / $40.00 budget
  new spend    $40.00
  retail value $52.91
  from collection: 7 cards
  ! "Sol Ring" is owned but sleeved in "Krenko, Mob Boss ($75)" --
    using it means taking that deck apart.
```

Owned cards that are currently in an **assembled** deck are still priced free
but flagged, since using one means dismantling a deck that already exists.
Surfacing the conflict beats deciding it silently.

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
commander's rules text usually states what the deck wants, and that text is
already in the local database. Measured against Tier 0 on the same commander
and budget:

| Commander | Themes detected | On-theme cards, tier 0 → tier 1 |
|---|---|---|
| Krenko, Mob Boss | Goblin, tokens | 4 → **52** goblins |
| Muldrotha, the Gravetide | graveyard | 6 → **61** graveyard cards |
| Atraxa, Praetors' Voice | counters | 8 → **62** counters cards |
| Talrand, Sky Summoner | spellslinger, tokens, Drake | 9 → **50** token cards |

Better still, the role quotas get filled *by on-theme cards*: a Tier 1 Krenko
deck ramps with Impulsive Pilferer, draws with Dark-Dweller Oracle, removes
with Siege-Gang Commander, and recurs with Squee — all Goblins. That is how the
deck is actually built in practice.

A bare subtype on the type line is treated as flavor, not a plan. Muldrotha is
an "Elemental Avatar" but is a graveyard deck; Atraxa is a "Phyrexian Angel
Horror" but is a counters deck. What marks a type as a real tribal theme is the
commander's *rules text* naming it too.

It works well for tribal and mechanic-themed commanders, poorly for abstract
value commanders (where it falls back to pure popularity rather than building
from near-zero theme scores), and not at all for combo commanders whose decks
are crowd knowledge rather than card text.

**Tier 2** is optional polish for those weak cases. Generated decks always
report which tier produced them.

## Expectations

Generated decks land roughly 80% of the way there. The optimizer cannot read
your commander and infer that your specific build wants sacrifice outlets over
+1/+1 counters. Treat the output as a strong first draft, not a finished deck.

## Stack

- **Backend:** Django 5.2 + Django REST Framework (Python 3.13)
- **Database:** PostgreSQL 16
- **Frontend:** React 19 + TypeScript + Vite

## API

```
GET  /api/config/                runtime feature flags
GET  /api/commanders/?q=         commander autocomplete
GET  /api/cards/ , /api/cards/<oracle_id>/
POST /api/brew/                  generate a deck
POST /api/brew/save/             generate and persist        | local only
GET  /api/decks/ , /api/decks/<id>/                          | local only
GET  /api/collection/ , DELETE /api/collection/<id>/         | local only
POST /api/collection/import/     paste a collection list     | local only
```

`POST /api/brew/` is deterministic — identical input always returns an
identical deck. An infeasible budget returns `400` carrying `minimum_cents`,
so a client can offer to raise the budget rather than just reporting failure.

That determinism is what makes the response cacheable. Brews are cached for
24h on the full determinism key — commander, budget, strategy, land count and
whether an upgrade path was asked for — which turns a repeat request from
0.39s into 0.002s. The TTL is capped at a day because Scryfall prices move
daily. Rate limits are scoped: `20/min` for brewing, `120/min` for reads,
since a five-colour brew with an upgrade path is ~1.1s of CPU while
autocomplete is a single indexed query. Exceeding either returns `429`.

### Demo mode

There are no accounts, so the API is open (`AllowAny`). That is safe in two
configurations and no others:

| | |
|---|---|
| `DEMO_MODE=False` | the local tool — write endpoints exist, bound to localhost |
| `DEMO_MODE=True` | a public read-only showcase — the write endpoints do not exist |

With `DEMO_MODE=True`, the routes marked *local only* above and the Django
admin are **not registered**, so they return `404` rather than `403` — the
demo does not advertise functionality it refuses. `GET /api/config/` reports
the flag, so one built frontend bundle serves both: the UI hides the
Collection tab and the "cards I own are free" option when demo mode is on.

Saved decks and collection tracking live in the
[CLI](https://github.com/husomichael/edh-budget-brewer-cli), which is where
per-user state actually makes sense.

## Share URLs

A generated deck is shareable as a plain link, with nothing stored server-side:

```
/?commander=krenko-mob-boss&budget=75&strategy=tier1&lands=36
```

This works only because the solver is deterministic — the same input returns a
byte-identical list, so the parameters *are* the deck. No row, no id, no
expiry. Opening the link resolves the slug server-side and re-runs the brew.
The URL is kept in sync with `history.replaceState`, so tweaking the budget
does not fill the back button with every intermediate value.

Slugs come from the full card name, never a prefix: `Krenko, Mob Boss` and
`Krenko, Tin Street Kingpin` must not collide, and as `krenko-mob-boss` and
`krenko-tin-street-kingpin` they do not. All 3,441 commander-legal cards
currently produce distinct slugs.

Prices move daily, so a link shared months ago may solve slightly differently
today. That is honest rather than broken, and the result says when it was
priced.

## Image hosting

**Decision: keep pointing at Scryfall's CDN, lazily.** Scryfall ask projects
doing bulk work to use their bulk data rather than hotlinking at scale, so
this was worth measuring rather than assuming.

The card image is only requested on hover, because the `<img>` element is not
rendered until then — stronger than `loading="lazy"`, which still fetches
eventually. Measured on a rendered 100-card deck: **one** Scryfall image
request, for the commander portrait in the sidebar. Hovering a card adds
exactly one more.

So a page view costs ~1 image, not ~100, and proxying would trade a CDN
problem for a storage and bandwidth problem on a 512MB instance. Worth
revisiting if traffic ever becomes non-trivial.

## Deploying

The app runs as a single container: Node builds the React frontend, Django
serves it through WhiteNoise alongside the API, and gunicorn fronts it.
[`render.yaml`](render.yaml) declares a web service, a managed Postgres, and a
nightly price-refresh cron job.

```bash
manage.py bootstrap            # empty environment -> serving brews
manage.py bootstrap --refresh  # nightly: prices and roles only
```

On a hosted deploy there is no manual step: `docker-entrypoint.sh` migrates
and runs `bootstrap --if-empty` on container start, because Render's free tier
has no shell to run it from. The load happens in the background so the service
goes healthy in ~100s rather than ~7.5 minutes, and `/api/config/` reports
`data_ready` so the UI can say it is still loading instead of looking broken.

**[DEPLOY.md](DEPLOY.md) is the full runbook** — environment variables, first
deploy, the free tier's trade-offs, rollback, and what to change to go paid.

## Related

The optimizer engine is also available as a standalone command-line tool, with
no web layer, at
[**edh-budget-brewer-cli**](https://github.com/husomichael/edh-budget-brewer-cli).

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
