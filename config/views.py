"""Views that belong to the deployment rather than to the card domain.

The health check is NOT here: it lives in config.middleware, because it has
to answer before ALLOWED_HOSTS validation and the HTTPS redirect get a
chance to reject it.
"""

from django.conf import settings
from django.http import HttpResponse, HttpResponseServerError
from django.views import View


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
