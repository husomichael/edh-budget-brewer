from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from config.views import SpaView, healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("api/", include("cards.urls")),
]

# The admin is a write surface of its own, and the demo has no accounts to log
# into it with. Leave it unmounted rather than relying on there being no
# superuser.
if not settings.DEMO_MODE:
    urlpatterns.insert(0, path("admin/", admin.site.urls))

# Catch-all for client-side routes, so a shared deep link works on a cold
# load instead of 404ing. Registered last, so every real route above wins.
#
# The negative lookahead matters: without it a mistyped API path returns
# index.html with a 200, and the caller sees a page of HTML where it expected
# JSON -- which looks like a broken client rather than a wrong URL.
urlpatterns.append(
    re_path(r"^(?!api/|admin/|static/|healthz$).*$", SpaView.as_view(), name="spa")
)
