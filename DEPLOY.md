# Deploying edh-budget-brewer

Everything needed to take this from a clone to a live demo. Self-contained on
purpose — you should not need to read another file to get through it.

> **The step people miss is step 5.** A fresh deploy has an empty card table.
> `/healthz` returns 200, the page loads, and commander search returns an
> empty list — so you cannot even select a commander, let alone brew. The app
> looks broken while being perfectly healthy. (Before `migrate` has run at
> all, the API returns 500s instead; the pre-deploy command handles that.)

---

## Platform

**Render**, as one web service plus one managed Postgres, declared in
[`render.yaml`](render.yaml).

Why this shape:

- **One service, not two.** The Django container serves both the API and the
  built React app through WhiteNoise, so there is no CORS to configure, no
  second host, and no CDN. The Vite dev proxy gives the same same-origin shape
  locally, so production and development differ only in who serves the files.
- **Managed Postgres, not a container.** Backups and point-in-time recovery
  are not worth hand-rolling for a demo.
- **Render specifically** because the nightly price refresh is a first-class
  cron service in the same blueprint. On a platform without native cron, that
  job becomes a scheduled-machine workaround or an external trigger.

**Postgres is required, not a preference.** The candidate-pool query filters by
colour identity using the array containment operator (`@>`) against a GIN
index. SQLite cannot express it. Do not substitute.

---

## Environment variables

| Variable | Example | Notes |
|---|---|---|
| `SECRET_KEY` | `kd8f...` (50+ random chars) | `generateValue: true` in the blueprint. Never commit one. |
| `DATABASE_URL` | `postgres://ebb:…@…/edh_budget_brewer` | Wired from the managed database. |
| `DEBUG` | `False` | Never `True` in production. CI fails the build if it is. |
| `ALLOWED_HOSTS` | `edh-budget-brewer.onrender.com` | Comma-separated. Prompted at blueprint creation — the hostname is not known until Render assigns it. |
| `CSRF_TRUSTED_ORIGINS` | `https://edh-budget-brewer.onrender.com` | Comma-separated, **scheme included**. Also prompted. |
| `SCRYFALL_USER_AGENT` | `edh-budget-brewer/0.1 (+https://github.com/…)` | Scryfall requires a descriptive UA. Do not leave this to an HTTP library. |
| `DEMO_MODE` | `True` | Read-only showcase. **Must be `True` for anything public** — see below. |
| `HTTPS_ONLY` | `True` | TLS, secure cookies, HSTS, and proxy awareness in one switch. |
| `WEB_CONCURRENCY` | `2` | gunicorn workers. |
| `SECURE_HSTS_SECONDS` | `3600` | Optional, defaults to 3600. Raise only once the deploy is known good. |

### `DEMO_MODE=True` is not optional for a public deploy

There are no accounts, and `Deck` / `CollectionItem` have no owner field, so
all state is global. With `DEMO_MODE=True` the write routes and the Django
admin are **not registered at all** — they return `404`, not `403`. With it
off, anyone who finds the URL can delete every deck and wipe the collection.

Collection tracking and saved decks live in the
[CLI](https://github.com/husomichael/edh-budget-brewer-cli), where per-user
state actually makes sense.

### `HTTPS_ONLY=True` and the redirect loop

Render terminates TLS at its load balancer and forwards plain HTTP. Django
therefore sees an insecure request, `SECURE_SSL_REDIRECT` redirects it to
`https://`, and that arrives back as plain HTTP — an infinite loop. The
`HTTPS_ONLY` switch sets `SECURE_PROXY_SSL_HEADER` alongside the redirect for
exactly this reason. If you ever set the four TLS settings by hand, set that
one too.

---

## First deploy

### 1. Provision

In Render: **New → Blueprint**, point it at this repo. It reads `render.yaml`
and creates the web service, the Postgres instance, and the cron job.

### 2. Answer the two prompts

`ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are marked `sync: false`, so Render
asks for them. You do not know the hostname yet — put anything, then fix it in
step 4.

### 3. Let the first deploy run

It will build the image (Node builds the frontend, Python runs
`collectstatic`), run `migrate` as the pre-deploy command, and start gunicorn.

**The app will be up and every brew will fail.** That is expected; the card
table is empty.

### 4. Fix the hostname

Copy the assigned hostname from the service page and set both:

```
ALLOWED_HOSTS=edh-budget-brewer.onrender.com
CSRF_TRUSTED_ORIGINS=https://edh-budget-brewer.onrender.com
```

Saving env vars triggers a redeploy. Wait for it.

### 5. Load the data — the step that is actually required

Open **Shell** on the web service and run:

```bash
python manage.py bootstrap
```

This runs four steps in order — `migrate`, `sync_catalogs`, `sync_cards`,
`classify_cards` — downloading ~25MB of bulk data from Scryfall. Measured at
**18s** in the container on a fast connection; budget a minute or two on a
small instance. The order matters: `classify_cards` has nothing to classify
before `sync_cards`, and Tier 1 theme detection needs the creature-type
catalog from `sync_catalogs`.

It is idempotent, so re-running is safe.

It finishes with a count line in this shape:

```
Done in <N>s. Cards: 0 -> 34558 (+34558), 34558 classified.
```

If it reports fewer than 25,000 cards it exits non-zero rather than claiming
success — a truncated download or a changed bulk format, not a quiet year for
Magic.

### 6. Verify

```bash
curl https://YOUR-HOST/healthz                      # -> ok
curl https://YOUR-HOST/api/config/                  # -> {"demo_mode":true}
curl -s -o /dev/null -w '%{http_code}\n' \
     https://YOUR-HOST/api/brew/save/               # -> 404, not 403
```

Then open the site and brew something. The Collection tab should not appear.

---

## Nightly price refresh

Already in the blueprint as the `edh-budget-brewer-refresh` cron service:

```
schedule:      0 10 * * *            # 10:00 UTC daily
dockerCommand: python manage.py bootstrap --refresh
```

`--refresh` skips `migrate` and `sync_catalogs` — the schema and type catalogs
are already in place — so it is prices and roles only. 10:00 UTC sits after
Scryfall's own daily bulk rebuild.

Prices really do move. A deck priced at $75 six months ago is not $75 now,
which is why `DeckCard.price_at_generation` exists.

**Watch the counts, not just the exit code.** Each run ends with a
`Cards: <before> -> <after> (<delta>), <n> classified.` line. A sync that
silently fetches nothing can still exit 0; that line is how you see it. The
plausibility guard catches the catastrophic case, not a stale-but-plausible
one.

---

## Rolling back

Code, in Render's dashboard: **Deploys → the previous successful deploy →
Rollback**. Images are kept, so this does not rebuild.

Two things a rollback does **not** undo:

- **Migrations.** Nothing in Phase 4 is destructive, but a future
  data-dropping migration will not reverse itself. Check what the migration
  did before rolling back past it.
- **HSTS.** Browsers cache it, and you cannot withdraw it on demand. This is
  why `SECURE_HSTS_SECONDS` starts at 3600 instead of a year — a bad TLS
  config pinned for 12 months is a long problem. Raise it deliberately, once.

Card data needs no rollback: re-running `bootstrap` rebuilds it from Scryfall.

---

## Cost

Approximate, as of October 2026 — check
[render.com/pricing](https://render.com/pricing) for current rates:

| | Plan | ~Monthly |
|---|---|---|
| Web service | `0.5c-512mb` | $7 |
| Postgres | `0.1c-256mb` | $6 |
| Cron job | `0.5c-512mb` | billed per run-minute; ~1 min/day, negligible |
| | | **~$13** |

Plus Postgres storage at $0.30/GB and outbound bandwidth above the included
allowance.

**Memory is the binding constraint, not CPU.** Measured against this image
with two workers and the full card set loaded:

| | |
|---|---|
| Idle | ~110 MiB |
| After a five-colour brew | ~195 MiB |
| Peak under 12 concurrent five-colour brews with upgrade paths | **262–274 MiB** (~54% of 512MB) |

Request latency, uncontended:

| Brew | Time |
|---|---|
| Mono-colour | 0.19s |
| Mono-colour + upgrade path | 0.35s |
| Five-colour | 0.60s |
| Five-colour + upgrade path | 1.12s |

That burst of 12 completed in 7.6s with no worker timeouts — roughly 1.6
worst-case brews/second through two workers. 512MB is genuinely enough, but
the headroom is about 2x, not 10x. If you scale anything, scale memory, and
raise `WEB_CONCURRENCY` only alongside it.

The free web tier spins down after inactivity, which makes a demo link cold
and slow on first hit. Not recommended for something you intend to share.

---

## Keep it non-commercial

This is a hard constraint, not a preference:

- The **Wizards Fan Content Policy** requires fan projects to be
  non-commercial. No ads, no charging, no paywall.
- **Scryfall** separately forbids paywalling or reselling their data, and
  requires attribution with their card data and images.
- **Do not scrape EDHREC.** No API, no data export, and their Acceptable Use
  Policy prohibits automated queries. `edhrec_rank` reaches this app through
  Scryfall's licensed bulk data, which is fine. Archidekt's terms carry the
  identical clause.

Visible Scryfall attribution on the deployed site is issue #27 and is not done
yet.
