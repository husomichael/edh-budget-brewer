"""Tests for the deployment surface: health check, static serving, SPA routes.

The SPA tests point FRONTEND_DIST at a temporary directory rather than relying
on `npm run build` having run, so they pass in CI without a Node step.
"""

import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

SHELL = b'<!doctype html><html><body><div id="root"></div></body></html>'


class HealthCheckTests(TestCase):
    def test_returns_ok(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_does_not_touch_the_database(self):
        """A probe that queries Postgres turns a DB blip into a restart loop."""
        with self.assertNumQueries(0):
            self.client.get("/healthz")


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
