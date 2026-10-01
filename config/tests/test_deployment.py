"""Tests for the deployment surface: health check, static serving, SPA routes.

The SPA tests point FRONTEND_DIST at a temporary directory rather than relying
on `npm run build` having run, so they pass in CI without a Node step.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

SHELL = b'<!doctype html><html><body><div id="root"></div></body></html>'


class HealthCheckTests(TestCase):
    """The probe must answer 200 regardless of how the app is configured.

    These are regression tests for a real failed deploy: every health check
    returned 400 for 15 minutes while the app ran fine, and the platform
    cancelled the deploy.
    """

    def test_returns_ok(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_does_not_touch_the_database(self):
        """A probe that queries Postgres turns a DB blip into a restart loop."""
        with self.assertNumQueries(0):
            self.client.get("/healthz")

    @override_settings(ALLOWED_HOSTS=["example.com"])
    def test_survives_a_host_not_in_allowed_hosts(self):
        """The exact first-deploy failure.

        The platform probes over its internal network with a Host header that
        is not the public hostname. Host validation answered 400 every 10
        seconds until the deploy timed out.
        """
        response = self.client.get("/healthz", HTTP_HOST="10.233.26.121:10000")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_is_not_redirected_to_https(self):
        """The second bug, latent behind the first.

        The internal probe arrives as plain HTTP with no X-Forwarded-Proto,
        so SecurityMiddleware would answer 301 -- not a 2xx either. Fixing
        only ALLOWED_HOSTS would have swapped one failing status for another.
        """
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)

    @override_settings(ALLOWED_HOSTS=["example.com"], SECURE_SSL_REDIRECT=True)
    def test_survives_both_at_once(self):
        response = self.client.get("/healthz", HTTP_HOST="10.0.0.5")
        self.assertEqual(response.status_code, 200)

    def test_does_not_wait_for_card_data(self):
        """Liveness, not readiness.

        Waiting for the background card load would block the deploy for the
        ~5 minutes it takes, reintroducing the timeout the background design
        exists to avoid. Readiness is reported by /api/config/ instead.
        """
        from cards.models import Card

        self.assertEqual(Card.objects.count(), 0)
        self.assertEqual(self.client.get("/healthz").status_code, 200)

    def test_other_paths_are_unaffected(self):
        """The middleware must match only the health path."""
        self.assertNotEqual(self.client.get("/healthzzz").content, b"ok")


class RenderHostnameTests(SimpleTestCase):
    """Render sets RENDER_EXTERNAL_HOSTNAME; settings.py trusts it.

    Run in a subprocess because the derivation happens at settings import,
    which cannot be re-run meaningfully in-process. Worth the cost: the
    alternative -- prompting for the hostname -- is unfixable after a bad
    first deploy, so this wiring has to actually work.
    """

    def _settings_with(self, **extra_env):
        env = {
            **os.environ,
            "SECRET_KEY": "subprocess-only-key-0123456789-abcdefghij-klmnop",
            "DATABASE_URL": "postgres://u:p@localhost:5432/d",
            "SCRYFALL_USER_AGENT": "test/0.1",
            **extra_env,
        }
        code = (
            "import django, json; django.setup();"
            "from django.conf import settings as s;"
            "print(json.dumps({'hosts': list(s.ALLOWED_HOSTS),"
            " 'csrf': list(s.CSRF_TRUSTED_ORIGINS)}))"
        )
        env["DJANGO_SETTINGS_MODULE"] = "config.settings"
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path(__file__).resolve().parents[2]),
            check=True,
        )
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_render_hostname_is_added_to_allowed_hosts_and_csrf(self):
        result = self._settings_with(
            RENDER_EXTERNAL_HOSTNAME="edh-budget-brewer.onrender.com"
        )
        self.assertIn("edh-budget-brewer.onrender.com", result["hosts"])
        self.assertIn("https://edh-budget-brewer.onrender.com", result["csrf"])

    def test_absent_render_hostname_changes_nothing(self):
        """Local development must be unaffected."""
        result = self._settings_with(RENDER_EXTERNAL_HOSTNAME="")
        self.assertNotIn("", result["hosts"])
        self.assertEqual([h for h in result["hosts"] if "onrender" in h], [])


class SpaRoutingTests(SimpleTestCase):
    def setUp(self):
        self.dist = Path(tempfile.mkdtemp())
        (self.dist / "index.html").write_bytes(SHELL)
        override = override_settings(FRONTEND_DIST=self.dist)
        override.enable()
        self.addCleanup(override.disable)

    def test_root_serves_the_app_shell(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html")
        self.assertEqual(response.content, SHELL)

    def test_deep_link_serves_the_app_shell(self):
        """A shared link must survive a cold load rather than 404ing."""
        response = self.client.get("/decks/krenko-mob-boss?budget=100")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, SHELL)

    def test_catch_all_is_read_only(self):
        self.assertEqual(self.client.post("/anything").status_code, 405)

    def test_missing_build_explains_itself(self):
        """A blank page is the hardest deploy failure to diagnose."""
        with override_settings(FRONTEND_DIST=self.dist / "nope"):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 500)
        self.assertIn(b"npm run build", response.content)


class CatchAllScopeTests(SimpleTestCase):
    """The catch-all must not shadow the routes it is registered behind.

    Without the negative lookahead a mistyped API path returns the HTML shell
    with a 200, and the caller sees a page where it expected JSON.
    """

    def setUp(self):
        self.dist = Path(tempfile.mkdtemp())
        (self.dist / "index.html").write_bytes(SHELL)
        override = override_settings(FRONTEND_DIST=self.dist)
        override.enable()
        self.addCleanup(override.disable)

    def test_unknown_api_path_404s_rather_than_serving_html(self):
        response = self.client.get("/api/not-a-real-endpoint/")
        self.assertEqual(response.status_code, 404)
        self.assertNotEqual(response.content, SHELL)

    def test_unknown_static_path_404s_rather_than_serving_html(self):
        response = self.client.get("/static/not-a-real-asset.js")
        self.assertEqual(response.status_code, 404)
        self.assertNotEqual(response.content, SHELL)

    def test_healthz_is_not_shadowed(self):
        self.assertEqual(self.client.get("/healthz").content, b"ok")

    def test_admin_is_not_shadowed(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.content, SHELL)
