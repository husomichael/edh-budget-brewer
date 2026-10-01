"""Tests for DEMO_MODE, the read-only public deployment.

These reload the URLconf rather than pointing `ROOT_URLCONF` at a mirror
defined here. A mirror would pass even if the `if not settings.DEMO_MODE`
guards were deleted, which is the one thing worth testing.
"""

import importlib

from django.test import TestCase, override_settings
from django.urls import clear_url_caches, reverse

import cards.urls
import config.urls
from cards.models import CollectionItem, Deck
from cards.tests.test_api import make_card

# Every stateful route, with arguments for the ones that take them, and the
# methods that must not reach a view. Checked for completeness against
# cards.urls.stateful_urlpatterns below, so a new stateful route cannot be
# added without a test for it.
STATEFUL_ROUTES = {
    "brew-save": ((), ("get", "post")),
    "deck-list": ((), ("get", "post")),
    "deck-detail": ((1,), ("get", "put", "patch", "delete")),
    "collection": ((), ("get", "post")),
    "collection-import": ((), ("get", "post")),
    "collection-item": ((1,), ("get", "delete")),
}


def reload_urlconf():
    """Rebuild both URLconfs against the current DEMO_MODE.

    Order matters: `cards.urls` first, because `config.urls` copies its
    `urlpatterns` list at `include()` time rather than reading it lazily.
    """
    importlib.reload(cards.urls)
    importlib.reload(config.urls)
    clear_url_caches()


class DemoModeOffTests(TestCase):
    """The local tool: everything is registered."""

    def test_stateful_routes_are_registered(self):
        names = {p.name for p in cards.urls.urlpatterns}
        self.assertTrue(set(STATEFUL_ROUTES) <= names)

    def test_admin_is_mounted(self):
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_config_reports_demo_mode_off(self):
        body = self.client.get(reverse("config")).json()
        self.assertFalse(body["demo_mode"])

    def test_route_table_covers_every_stateful_route(self):
        """Guards the test below: an untested stateful route is a hole."""
        self.assertEqual(
            {p.name for p in cards.urls.stateful_urlpatterns},
            set(STATEFUL_ROUTES),
        )


class DemoModeOnTests(TestCase):
    """The public demo: the stateful half does not exist."""

    def setUp(self):
        # Resolve against the full URLconf while it is still loaded -- under
        # demo mode these names do not reverse at all.
        self.paths = {
            name: reverse(name, urlconf="config.urls", args=args)
            for name, (args, _) in STATEFUL_ROUTES.items()
        }

        self.override = override_settings(DEMO_MODE=True)
        self.override.enable()
        reload_urlconf()
        self.addCleanup(reload_urlconf)
        self.addCleanup(self.override.disable)

        self.commander = make_card(
            "Demo Cmdr",
            type_line="Legendary Creature — Goblin",
            oracle_text="Create a 1/1 red Goblin creature token.",
            can_be_commander=True,
        )
        make_card(
            "Mountain",
            type_line="Basic Land — Mountain",
            is_land=True,
            is_basic=True,
            primary_role="land",
            price_cents=None,
        )
        for i in range(90):
            make_card(f"filler-{i}", price_cents=5 + i, edhrec_rank=1000 + i)

    def test_every_stateful_route_404s(self):
        for name, (_, methods) in STATEFUL_ROUTES.items():
            for method in methods:
                with self.subTest(route=name, method=method):
                    response = getattr(self.client, method)(self.paths[name])
                    self.assertEqual(
                        response.status_code,
                        404,
                        f"{method.upper()} {self.paths[name]} is reachable",
                    )

    def test_no_request_to_a_stateful_route_changes_state(self):
        """The headline guarantee: the demo cannot be written to."""
        body = {
            "commander_oracle_id": str(self.commander.oracle_id),
            "budget_cents": 5_000,
            "name": "Should Not Exist",
        }
        self.client.post(self.paths["brew-save"], body, content_type="application/json")
        self.client.post(
            self.paths["collection-import"],
            {"text": "1 Mountain", "replace": False},
            content_type="application/json",
        )
        self.client.post(
            self.paths["collection"],
            {"card": "Mountain"},
            content_type="application/json",
        )
        self.assertEqual(Deck.objects.count(), 0)
        self.assertEqual(CollectionItem.objects.count(), 0)

    def test_admin_is_not_mounted(self):
        self.assertEqual(self.client.get("/admin/").status_code, 404)

    def test_brew_still_works(self):
        response = self.client.post(
            reverse("brew"),
            {
                "commander_oracle_id": str(self.commander.oracle_id),
                "budget_cents": 5_000,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["card_count"], 100)

    def test_reads_still_work(self):
        self.assertEqual(self.client.get(reverse("commanders")).status_code, 200)
        self.assertEqual(self.client.get(reverse("card-search")).status_code, 200)

    def test_config_reports_demo_mode_on(self):
        self.assertTrue(self.client.get(reverse("config")).json()["demo_mode"])
