"""Views that belong to the deployment rather than to the card domain."""

from django.conf import settings
from django.http import HttpResponse, HttpResponseServerError
from django.views import View


def healthz(request):
    """Liveness probe for the hosting platform.

    Deliberately does not touch the database. A health check that queries
    Postgres turns a database blip into a rolling restart of healthy app
    instances, which makes an outage worse rather than shorter.
    """
    return HttpResponse("ok", content_type="text/plain")


class SpaView(View):
    """Serve the built React app's entry point.

    Read from `frontend/dist` rather than STATIC_ROOT so this also works
    under `runserver`, where the staticfiles app serves STATICFILES_DIRS
    directly and collectstatic has not necessarily run. The hrefs inside
    point at /static/, which WhiteNoise serves in production.

    Not cached in memory: it is one ~500-byte file, and re-reading means a
    redeploy's new asset hashes take effect without a restart.
    """

    def get(self, request, *args, **kwargs):
        index = settings.FRONTEND_DIST / "index.html"
        if not index.is_file():
            # A blank page here is the hardest kind of deploy failure to
            # diagnose, so say exactly what is missing.
            return HttpResponseServerError(
                "The frontend has not been built. Run `npm run build` in "
                "frontend/, then `manage.py collectstatic`.",
                content_type="text/plain",
            )
        return HttpResponse(index.read_bytes(), content_type="text/html")
