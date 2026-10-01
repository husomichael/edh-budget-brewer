# edh-budget-brewer

Hosted web version of a Magic: The Gathering Commander deck optimizer. A
commander and a dollar budget in, a complete legal 100-card deck out.

A standalone CLI version lives in a **separate repo**:
`../edh-budget-brewer-cli` (github.com/husomichael/edh-budget-brewer-cli).

## State

Working end to end. Phases 1-3 are complete and closed (#1-#18 except #19).
Django + Postgres + React all run locally and the optimizer produces real
decks. **Nothing is deployed yet.**

**Phase 4: Public demo** — #20, #23, #24, #25, #26 and #29 are done. The
image has been **built and run end to end locally** (colima): bootstrap loads
34.5k cards in ~18s, five-colour brews work, the demo write surface 404s.
`render.yaml` itself has **never executed on Render** — that is the one
remaining unknown.

**All of Phase 4 is now implemented** (#20-#29 except #19, which is Phase 5).
The only thing not done is actually running the Render blueprint.

Targeting Render's **free tier**, which shapes the deployment: no shell and no
pre-deploy command (so `docker-entrypoint.sh` self-initialises), no cron (so
prices go stale), and the database expires every 30 days.

## Running it

```bash
.venv/bin/python manage.py runserver        # terminal 1
cd frontend && npm run dev                  # terminal 2  -> http://localhost:5173
.venv/bin/python manage.py brew "Krenko, Mob Boss" --budget 75
.venv/bin/python manage.py bootstrap        # empty env -> serving brews
.venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/ruff format --check .
```

To exercise the production path locally (WhiteNoise, the SPA catch-all, no
Vite): `cd frontend && npm run build`, then `manage.py collectstatic`, then
`DEBUG=False .venv/bin/gunicorn config.wsgi:application`. Leave `HTTPS_ONLY`
off — it would redirect to an https:// URL nothing is listening on.

## Environment gotchas

These each cost real debugging time. Check here before re-deriving them.

- **Postgres is 16 on port 5433**, not 5432. `postgresql@14` is installed but
  stopped; port **5432 is a different instance** running as the `postgres` user
  with password auth, which will prompt for a password and fail. `psql` on PATH
  is the v14 *client* and reports v14 — that is not the server version.
- **macOS python.org Python ignores the system cert store.** Scryfall
  downloads fail with `CERTIFICATE_VERIFY_FAILED` unless OpenSSL is pointed at
  `certifi`. Already handled in `sync_cards`; do the same for any new outbound
  HTTP.
- **Vite binds IPv6 `[::1]` only.** Use `http://localhost:5173`, not
  `127.0.0.1:5173`, which refuses the connection.
- **Scryfall's bulk format is gzipped JSONL** via `jsonl_download_uri` (not
  `download_uri`, and not a JSON array). Size is `compressed_size`.
- **Run `classify_cards` after every `sync_cards`.** A sync overwrites rows and
  leaves roles stale.
- An empty database makes every brew return `infeasible_budget`. Bootstrap is
  `migrate && sync_catalogs && sync_cards && classify_cards`, or just
  `manage.py bootstrap`. Before `migrate` has run at all the API returns 500s,
  not a friendly error.
- **`override_settings(REST_FRAMEWORK=...)` does not change DRF throttling.**
  `SimpleRateThrottle.THROTTLE_RATES` is a class attribute bound to the
  settings dict at import time, so the override is silently ignored and tests
  assert the wrong thing while throttling stays live. Patch the class
  attribute instead — see `conftest.py` and `test_throttling_and_cache.py`.
- **Readiness is a completion check, not a row count.** `sync_cards` writes in
  batches, so an interrupted load leaves a plausible-looking 31k of 34.5k
  rows. A count threshold accepts that and freezes the database permanently
  incomplete. `card_data_is_loaded()` requires every card to have a
  `role_source`, which only `classify_cards` sets. Verified by killing a
  container mid-load.
- **Docker locally is colima, not Docker Desktop.** `brew install colima
  docker`, then `colima start`. Docker Desktop was uninstalled in 2023 and
  left broken symlinks in `/usr/local/bin` plus `"credsStore": "desktop"` in
  `~/.docker/config.json` — the latter makes *any* image pull fail with
  `docker-credential-desktop: executable file not found`. Both are cleaned up
  now; if pulls break again, look there first.
- **`DEMO_MODE` is read at import time**, so toggling it needs the URLconfs
  rebuilt. Tests do that with `reload_urlconf()` in
  `cards/tests/test_demo_mode.py` — `cards.urls` first, because `config.urls`
  copies the list at `include()` time rather than reading it lazily.
- **Vite's `base` is `/static/` for builds only**, so production assets resolve
  under Django's `STATIC_URL`. Applying it in dev too would move the whole app
  to `localhost:5173/static/`.
- **`STATICFILES_DIRS` is conditional on `frontend/dist` existing.** A missing
  entry raises `staticfiles.W004`, and CI runs `check --deploy --fail-level
  WARNING` without a Node step.
- **Settings need `SECRET_KEY`, `DATABASE_URL` and `SCRYFALL_USER_AGENT` to
  import at all.** That is why the Dockerfile passes throwaway values inline on
  the `collectstatic` line — inline, so they never persist into a layer.

## Architecture

The pipeline, in dependency order:

```
sync_cards       Scryfall bulk JSONL -> Card rows (~34.5k)
classification   regex + override table -> functional role per card
scoring          Tier 0: log-normalized edhrec_rank
tier1            Tier 0 blended with themes inferred from commander text
pool             filter by legality/colour identity, score, tag roles
manabase         reserve lands first, two-pass for colour weights
solver           cheapest legal deck, then score-per-dollar upgrades
upgrades         solve at several budgets and diff
```

`views.py` / `serializers.py` / `urls.py` are the API; `frontend/` is React +
TypeScript with a Vite dev proxy to Django.

Brew responses are cached for 24h keyed on the full determinism key, and the
API is throttled with DRF scoped rates (`brew` vs `read`). `owned_free=True`
is never cached: it depends on the `CollectionItem` table, which can change
without the key changing.

Share URLs (#21) carry the whole deck in query parameters and resolve
`Card.slug` server-side via `cards/slugs.py`. **`ownedFree` is deliberately
absent from the URL** — it prices against the sender's collection, so sharing
it would give the recipient a different deck. `BREW_CACHE_VERSION` in
`views.py` must be bumped whenever the brew payload shape changes, or cached
responses will be served missing the new fields.

`cards/urls.py` splits routes into `public_urlpatterns` and
`stateful_urlpatterns`. **Any new route that mutates state goes in the
stateful list**, or `DEMO_MODE` will expose it publicly. There is no
per-request permission check to fall back on — the whole mechanism is which
routes get registered.

## Conventions

- **Money is integer cents everywhere.** Format only at the edge. Float dollars
  accumulate error across ~99 additions and miss the budget.
- **The solver must stay deterministic.** Every sort key ends in `oracle_id`.
  There is a test for this; share URLs (#21) depend on it.
- **A missing Scryfall price is NULL, never 0** — except basic lands, which
  genuinely are free and are the one exception.
- Scoring strategies normalize to 0..1 so the solver stays tier-agnostic.
- ruff for lint and format; `E501` is intentionally ignored under
  `cards/tests/` where real Oracle text is quoted one line per card.

## Known limitation, documented in the README

Score derives from `edhrec_rank`, which is log-normalized and so compresses
differences between top cards. The solver rates a $50 deck as ~94% as good as
an unlimited one, which overstates how close they are — it cannot see that an
expensive staple is *qualitatively* better, only that ranks are close. The
upgrade path is most trustworthy under ~$100. Fixing it properly needs a
signal for card power rather than popularity.

## EDHREC

**Do not scrape EDHREC.** They publish no API and no data export, and their
Terms of Use (Acceptable Use Policy, item 7) prohibit using scripts "to
generate automated searches, requests, or queries to the Site". Issue #8 was
closed for this reason. Archidekt's terms contain the identical clause.

`edhrec_rank` is fine — it reaches us through Scryfall's licensed bulk data.
Issue #19 (Tier 2) is user-pasted data only: each user fetches it in their own
browser under their own personal-use licence. Anything pasted stays in
`data/edhrec/`, which is gitignored and must never be committed.

## Two-repo caveat

The CLI repo is a **self-contained snapshot**, chosen deliberately over a
shared package. The solver exists in both repos, so a fix to `solver.py`,
`scoring.py`, `tier1.py`, `pool.py`, `manabase.py` or `classification.py`
must be applied in both if you want them to stay in sync.
