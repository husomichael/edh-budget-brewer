"""Django settings for edh-budget-brewer."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DEMO_MODE=(bool, False),
    HTTPS_ONLY=(bool, False),
    # Brew responses are cacheable because the solver is deterministic. 24h,
    # not longer: Scryfall prices move daily, and a week-old price is a lie.
    # 0 disables caching entirely.
    BREW_CACHE_SECONDS=(int, 86_400),
    BREW_THROTTLE_RATE=(str, "20/min"),
    READ_THROTTLE_RATE=(str, "120/min"),
    # Short on purpose. HSTS is cached by the browser and cannot be withdrawn
    # on demand, so a bad deploy pinned at a year is a long problem. Raise it
    # once the deployment has been good for a while.
    SECURE_HSTS_SECONDS=(int, 3600),
    CSRF_TRUSTED_ORIGINS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Read-only showcase mode for the public demo. When on, the write routes are
# never registered (so they 404 rather than 403) and the Django admin is not
# mounted, which means no request can change server state. Deliberately a
# separate switch from DEBUG: a private deployment with DEBUG=False still
# wants the collection and saved decks.
DEMO_MODE = env("DEMO_MODE")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "cards",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Directly after SecurityMiddleware and before everything else, per
    # WhiteNoise's docs: static files should not pay for session loading,
    # auth, or CSRF on every asset request.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation."
        "UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# The built React app. `npm run build` writes here, and collectstatic pulls it
# into STATIC_ROOT alongside Django's own assets, so one service serves both.
# Vite is configured with base="/static/" for production builds so the hrefs
# in its index.html point here.
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

# Conditional because a missing STATICFILES_DIRS entry raises staticfiles.W004,
# and CI runs `check --deploy --fail-level WARNING` without building the
# frontend. The catch-all view reports a clear error if the build is missing,
# which is a better failure than every management command refusing to start.
STATICFILES_DIRS = [FRONTEND_DIST] if FRONTEND_DIST.is_dir() else []

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        # Compressed: serves pre-built .gz/.br next to each file.
        # Manifest: appends a content hash, so assets can be cached forever.
        # Vite already hashes its own filenames; this covers Django's admin
        # assets, which are otherwise the only unhashed things served.
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- TLS and cookies -------------------------------------------------------
#
# One switch rather than four, because the four are only ever correct
# together: they all assume HTTPS is actually reachable. Set HTTPS_ONLY=True
# in any deployment with TLS in front of it, and leave it False locally --
# runserver speaks plain HTTP, and SECURE_SSL_REDIRECT would redirect every
# request to an https:// URL that nothing is listening on.
#
# Deliberately not keyed off `not DEBUG`: a local run with DEBUG=False (which
# is how you test the static-file pipeline) would otherwise become unusable.
HTTPS_ONLY = env("HTTPS_ONLY")

CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

if HTTPS_ONLY:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    SECURE_HSTS_SECONDS = env("SECURE_HSTS_SECONDS")
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # A PaaS load balancer terminates TLS and forwards plain HTTP, so Django
    # sees an insecure request and SECURE_SSL_REDIRECT redirects it to HTTPS
    # -- which arrives back as plain HTTP. That is an infinite redirect loop,
    # and it is the single most common way this deploy goes wrong.
    #
    # Only safe because the proxy overwrites this header on every request. If
    # this app is ever reachable directly, a client can set it themselves and
    # every secure-only protection above silently stops applying.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- Cache -----------------------------------------------------------------
#
# Locmem by default, which is per-process. With WEB_CONCURRENCY=2 that means
# two independent caches and two independent throttle counters: the brew hit
# rate is roughly halved and the effective request limit is double the
# configured rate. Both are acceptable for a demo, neither is a surprise.
#
# Point CACHE_URL at Redis to make them shared and the numbers exact:
#   CACHE_URL=rediscache://host:6379/0
CACHES = {"default": env.cache(default="locmemcache://")}

BREW_CACHE_SECONDS = env("BREW_CACHE_SECONDS")

REST_FRAMEWORK = {
    # The API is open because there are no accounts. That is safe only in the
    # two supported configurations:
    #
    #   local  (DEMO_MODE=False) -- write endpoints exist, bound to localhost
    #   demo   (DEMO_MODE=True)  -- public, and there are no write endpoints
    #
    # An open write API reachable from the internet is neither. If you add a
    # route that mutates state, add it to stateful_urlpatterns in cards/urls.py
    # so demo mode keeps excluding it.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    # Scoped rather than one global rate: a five-colour brew with an upgrade
    # path is ~1.1s of CPU, while autocomplete is a single indexed query.
    # Charging them the same rate either throttles typing or lets brews
    # saturate the instance.
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "brew": env("BREW_THROTTLE_RATE"),
        "read": env("READ_THROTTLE_RATE"),
    },
}

# --- Project settings -------------------------------------------------------

# Scryfall requires a descriptive User-Agent and an explicit Accept header.
SCRYFALL_USER_AGENT = env("SCRYFALL_USER_AGENT")
SCRYFALL_BULK_INDEX = "https://api.scryfall.com/bulk-data"

# Where bulk downloads land. Gitignored.
SCRYFALL_DATA_DIR = BASE_DIR / "data" / "scryfall"
