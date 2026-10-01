"""Middleware that has to run before Django's request handling."""

from django.conf import settings
from django.http import HttpResponse


class HealthCheckMiddleware:
    """Answer the platform's liveness probe before anything can reject it.

    Registered first, ahead of SecurityMiddleware, which is the entire point.
    A probe that configuration can break is not a probe, and two settings
    break it:

    - **ALLOWED_HOSTS.** The platform health-checks over its internal
      network, with a Host header that is not the public hostname, so host
      validation answers 400. This is exactly how the first deploy of this
      app failed: `"GET /healthz HTTP/1.1" 400` every 10 seconds until the
      deploy timed out, while the app itself was running fine.

    - **SECURE_SSL_REDIRECT.** The internal probe arrives as plain HTTP with
      no X-Forwarded-Proto, so SecurityMiddleware would answer 301 -- which
      is not a 2xx either. Fixing only ALLOWED_HOSTS would have swapped one
      failing status for another.

    This is a **liveness** check, not readiness: it reports that the process
    is up, and deliberately does not touch the database or wait for card
    data. Those are separate questions, and conflating them is harmful here.
    A probe that queried Postgres would turn a database blip into a rolling
    restart of healthy instances, and one that waited for card data would
    block the deploy for the five minutes the background load takes --
    reintroducing the timeout this design exists to avoid. The UI asks
    `/api/config/` for `data_ready` instead.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # request.path deliberately, never request.get_host(): reading the
        # host is what triggers the ALLOWED_HOSTS validation being bypassed.
        if request.path == settings.HEALTH_CHECK_PATH:
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)
