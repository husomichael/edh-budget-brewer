# Deploying edh-budget-brewer

Everything needed to take this from a clone to a live demo, on Render's
**free tier**, for $0/month. Self-contained on purpose — you should not need
to read another file to get through it.

> **There is no manual data-loading step.** Free instances have no shell, so
> the app loads its own card data on first boot. You deploy, wait, and it
> works. The part that needs attention is further down: the free database
> **expires 30 days after creation**.

---

## Platform

**Render**, as one free web service plus one free Postgres, declared in
[`render.yaml`](render.yaml).

Why this shape:

- **One service, not two.** The Django container serves both the API and the
  built React app through WhiteNoise, so there is no CORS to configure, no
  second host, and no CDN.
- **Self-initialising.** `docker-entrypoint.sh` runs migrations and the card
  load on container start, because the free tier offers no shell and no
  pre-deploy command — there is nowhere else to run them from.

**Postgres is required, not a preference.** The candidate-pool query filters by
colour identity using the array containment operator (`@>`) against a GIN
index. SQLite cannot express it. Do not substitute.

### What the free tier costs you

All three are real, and all three are survivable for a demo:

| | |
|---|---|
| **Cold starts** | The instance spins down after 15 minutes of inactivity. The next visitor waits ~1 minute. |
| **Slow uncached brews** | 0.1 CPU. An uncached five-colour brew takes ~11s versus 0.6s on a full core. The 24h brew cache is what rescues this: a repeat of the same brew is **0.08s**, and a demo mostly serves repeats of the same few commanders. |
| **Stale prices** | No cron jobs on free, so there is no nightly refresh. Prices drift. The result header says how old they are rather than pretending otherwise. |

Measured on a simulated free instance (`--cpus 0.1 --memory 512m`), not
estimated.

---

## Environment variables

Everything except the last two is set for you by `render.yaml`.

| Variable | Value | Notes |
|---|---|---|
| `SECRET_KEY` | auto-generated | `generateValue: true`. Must be 50+ characters — CI enforces this via `security.W009`. |
| `DATABASE_URL` | wired from the database | |
| `DEBUG` | `False` | Never `True` in production. |
| `ALLOWED_HOSTS` | `edh-budget-brewer.onrender.com` | **Prompted at creation.** Comma-separated. |
| `CSRF_TRUSTED_ORIGINS` | `https://edh-budget-brewer.onrender.com` | **Prompted at creation.** **Scheme included.** |
| `SCRYFALL_USER_AGENT` | `edh-budget-brewer/0.1 (+…)` | Scryfall requires a descriptive UA. |
| `DEMO_MODE` | `True` | Read-only showcase. **Must be `True` for anything public.** |
| `HTTPS_ONLY` | `True` | TLS, secure cookies, HSTS and proxy awareness in one switch. |
| `WEB_CONCURRENCY` | `1` | At 0.1 CPU a second worker buys no parallelism and costs ~50MB. |
| `BREW_CACHE_SECONDS` | `86400` | The single most important setting on free. |
| `BREW_THROTTLE_RATE` | `8/min` | Lower than the paid default: 20 uncached brews/min is more than 0.1 CPU can serve. |

### `DEMO_MODE=True` is not optional for a public deploy

There are no accounts, and `Deck` / `CollectionItem` have no owner field, so
all state is global. With `DEMO_MODE=True` the write routes and the Django
admin are **not registered at all** — they return `404`, not `403`. With it
off, anyone who finds the URL can delete every deck and wipe the collection.

### `HTTPS_ONLY=True` and the redirect loop

Render terminates TLS at its load balancer and forwards plain HTTP. Django
therefore sees an insecure request, `SECURE_SSL_REDIRECT` redirects it to
`https://`, and that arrives back as plain HTTP — an infinite loop. The
`HTTPS_ONLY` switch sets `SECURE_PROXY_SSL_HEADER` alongside the redirect for
exactly this reason.

---

## First deploy

### 1. Provision

In Render: **New → Blueprint**, point it at this repo. It reads `render.yaml`
and creates the web service and the Postgres instance.

If you connected GitHub with "Only select repositories", make sure
`edh-budget-brewer` is in that list first.

### 2. Answer the two prompts

`ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are marked `sync: false`, so Render
asks for them. You do not know the hostname yet — put anything, then fix it in
step 4.

### 3. Let the first deploy run

It builds the image (Node builds the frontend, Python runs `collectstatic`),
then starts. `docker-entrypoint.sh` migrates, kicks off the card load **in the
background**, and starts gunicorn immediately.

**The service goes healthy in about 100 seconds.** That is the point of
loading in the background: Render cancels a deploy whose health checks fail
for 15 minutes and destroys the instance, and a synchronous load uses ~7.5
minutes of that budget at 0.1 CPU. Serving first turns a possible
never-initialises failure into a visible, self-healing wait.

### 4. Fix the hostname

Copy the assigned hostname from the service page and set both:

```
ALLOWED_HOSTS=edh-budget-brewer.onrender.com
CSRF_TRUSTED_ORIGINS=https://edh-budget-brewer.onrender.com
```

Saving triggers a redeploy. The card data survives it — it lives in Postgres,
not the container.

### 5. Wait for the cards

Open the site. You will see a notice saying card data is still loading. It
takes **about 6.5 minutes** at 0.1 CPU, most of it classification, and the
notice clears itself — the page re-checks `/api/config/` every 15 seconds.

Watch the logs if you want to follow it:

```
Wrote: 34558 created, 0 updated. ...
Classified 34501 by heuristic, 57 by override.
Done in 380.3s. Cards: 0 -> 34558 (+34558), 34558 classified.
```

### 6. Verify

```bash
curl https://YOUR-HOST/healthz                      # -> ok
curl https://YOUR-HOST/api/config/                  # -> {"demo_mode":true,"data_ready":true}
curl -s -o /dev/null -w '%{http_code}\n' \
     https://YOUR-HOST/api/brew/save/               # -> 404, not 403
```

Then open the site and click the Krenko example. The Collection tab should not
appear.

---

## The monthly chore: the database expires

**Free Postgres is deleted 30 days after creation**, with a 14-day grace
period after expiry. There is one free database per workspace. This is the
single thing about this deployment that needs a calendar reminder.

When it expires:

1. Create a new free Postgres in Render.
2. Point the web service's `DATABASE_URL` at it.
3. Save, which redeploys.

That is all. The app detects an empty database on boot and reloads the cards
itself — the same path as the first deploy, ~6.5 minutes. No shell, no manual
bootstrap, no data to migrate, because the only data is a rebuildable cache of
Scryfall's.

To stop doing this every month, move the database to the cheapest paid plan
(`0.1c-256mb`, ~$6/mo) — see below.

---

## Rolling back

Code, in Render's dashboard: **Deploys → the previous successful deploy →
Rollback**. Images are kept, so this does not rebuild.

Two things a rollback does **not** undo:

- **Migrations.** Nothing so far is destructive, but a future data-dropping
  migration will not reverse itself.
- **HSTS.** Browsers cache it and you cannot withdraw it on demand. This is
  why `SECURE_HSTS_SECONDS` starts at 3600 instead of a year.

Card data needs no rollback: re-running the load rebuilds it from Scryfall.

---

## Cost, and moving to paid

**$0/month** as configured.

If the trade-offs stop being worth it:

| Change | Cost | Buys |
|---|---|---|
| Database → `0.1c-256mb` | ~$6/mo | No 30-day expiry. Cold starts remain. |
| Web → `0.5c-512mb` | ~$7/mo | No cold starts, fast brews, shell access, and cron becomes available. |

Going paid on the web service is three edits to `render.yaml`: set `plan`,
add back `preDeployCommand: python manage.py migrate --noinput`, and add a
cron service running `python manage.py bootstrap --refresh` on `0 10 * * *`
for the nightly price refresh. Raise `WEB_CONCURRENCY` to `2` and
`BREW_THROTTLE_RATE` to `20/min` at the same time. The entrypoint keeps
working either way — it becomes redundant rather than wrong.

Approximate as of October 2026; check [render.com/pricing](https://render.com/pricing).

**Memory is not the constraint; CPU is.** Measured on a simulated free
instance: 61MiB idle, 135MiB peak during the first-boot data load, against
512MB available. On a paid instance with two workers, a burst of 12 concurrent
five-colour brews peaked at 262–274MiB.

---

## Keep it non-commercial

This is a hard constraint, not a preference:

- The **Wizards Fan Content Policy** requires fan projects to be
  non-commercial. No ads, no charging, no paywall.
- **Scryfall** separately forbids paywalling or reselling their data, and
  requires attribution with their card data and images. The app footer carries
  it.
- **Do not scrape EDHREC.** No API, no data export, and their Acceptable Use
  Policy prohibits automated queries. `edhrec_rank` reaches this app through
  Scryfall's licensed bulk data, which is fine.
