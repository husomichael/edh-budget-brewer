# Multi-stage: Node builds the frontend, Python runs the app and serves the
# built assets through WhiteNoise. One image, one service, no CDN.

# --- Stage 1: build the React app -------------------------------------------
FROM node:22-slim AS frontend

WORKDIR /build

# Copy the manifests alone first, so `npm ci` is cached and only re-runs when
# dependencies actually change -- not on every source edit.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Produces dist/ with base=/static/, matching where Django serves assets.
RUN npm run build


# --- Stage 2: the application -----------------------------------------------
FROM python:3.13-slim AS app

# PYTHONUNBUFFERED: without it, logs sit in a buffer and a crash loses the
# traceback that explains it.
# PYTHONDONTWRITEBYTECODE: the filesystem is immutable and read once.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# psycopg-binary ships its own libpq, so there is no libpq-dev or compiler to
# install here. That is most of why this image stays small.
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY manage.py docker-entrypoint.sh ./
COPY config/ ./config/
COPY cards/ ./cards/
COPY --from=frontend /build/dist/ ./frontend/dist/

# Run as a non-root user. Created before collectstatic so the static tree is
# owned by the user that reads it.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

# collectstatic at build time, not at boot: it is the same work on every
# start, it needs write access the runtime filesystem may not have, and a
# failure here should break the build rather than the deploy.
#
# The env vars are inline on this one RUN so they never persist into an image
# layer. Settings require them to import at all; none are used by
# collectstatic, and a baked SECRET_KEY would be a real one.
RUN SECRET_KEY=build-time-only-not-used \
    DATABASE_URL=postgres://build:build@localhost:5432/build \
    SCRYFALL_USER_AGENT=edh-budget-brewer-build/0.1 \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Migrate and load data before serving. See docker-entrypoint.sh for why this
# happens here rather than in a release or pre-deploy step.
ENTRYPOINT ["./docker-entrypoint.sh"]

# Memory, not CPU, is the binding constraint. Measured in this image under a
# burst of 12 concurrent five-colour brews with upgrade paths: 262-274MiB
# resident, about 54% of a 512MB instance, no timeouts.
#
# WEB_CONCURRENCY defaults to 1 because the free instance type is 0.1 CPU,
# where a second worker buys no parallelism and costs ~50MB. Set it to 2 on a
# paid instance.
#
# $PORT is whatever the platform assigns; sh -c is needed to expand it.
# --access-logfile - sends request logs to stdout, where the platform collects
# them. Without it gunicorn logs nothing and a 500 is invisible.
CMD ["sh", "-c", "gunicorn config.wsgi:application \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers ${WEB_CONCURRENCY:-1} \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -"]
