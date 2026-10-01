#!/bin/sh
# Container start-up: make the database usable, then serve.
#
# This exists because Render's free instance type has no shell and no
# pre-deploy command, so there is nowhere else to run migrations or the
# initial data load from. The app has to initialise itself or it is
# permanently empty.
#
# The data load runs in the BACKGROUND, which is the whole design decision
# here. Measured on a 0.1 CPU / 512MB instance -- the free tier -- loading
# 34.5k cards takes about 6.5 minutes, most of it classification. Render
# cancels a deploy whose health checks fail for 15 minutes and destroys the
# instance, so a synchronous load would spend half that budget before the
# port is even open, and a slow day at Scryfall would mean the service never
# initialises at all.
#
# Serving first turns that failure mode into a visible, self-healing one: the
# deploy succeeds in about a minute, `/healthz` passes, and the cards arrive a
# few minutes later. `/api/config/` reports `data_ready` so the UI can say so
# rather than looking broken.

set -e

# Fatal, and synchronous. Without a schema every request is a 500, and
# starting gunicorn first would only hide the reason behind application
# errors. Fast even on 0.1 CPU, and a no-op on every boot after the first.
python manage.py migrate --noinput

# Backgrounded. `--if-empty` is a migrate no-op plus one COUNT once the data
# is there, so restarts -- which a free instance does after every 15 minutes
# of inactivity -- cost nothing.
#
# A partial load left by a mid-sync restart is handled, but not by counting
# rows -- 31k of 34.5k looks plausible. Readiness means every card is
# classified, so an interrupted load is detected and restarted. See
# cards.models.card_data_is_loaded.
python manage.py bootstrap --if-empty || \
  echo "WARNING: card data load failed; a restart will retry it." >&2 &

exec "$@"
