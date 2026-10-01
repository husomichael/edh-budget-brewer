"""Tests for brew response caching and scoped rate limiting (#22)."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.throttling import SimpleRateThrottle

from cards.classification import LAND
from cards.models import Card
from cards.tests.test_api import make_card
from cards.views import BREW_CACHE_VERSION, brew_cache_key


def throttled(**rates):
    """Re-enable throttling, which conftest disables for every other test.

    Patches the class attribute, not the setting: DRF binds THROTTLE_RATES at
    import time, so override_settings(REST_FRAMEWORK=...) has no effect on an
    already-imported throttle class.
    """
    return patch.object(SimpleRateThrottle, "THROTTLE_RATES", rates)


class BrewFixture(TestCase):
    def setUp(self):
        self.commander = make_card(
            "Cache Cmdr",
            type_line="Legendary Creature — Goblin",
            oracle_text="Create a 1/1 red Goblin creature token.",
            can_be_commander=True,
        )
        make_card(
            "Mountain",
            type_line="Basic Land — Mountain",
            is_land=True,
            is_basic=True,
            primary_role=LAND,
            price_cents=None,
        )
        for i in range(90):
            make_card(f"filler-{i}", price_cents=5 + i, edhrec_rank=1000 + i)

    def post(self, **overrides):
        payload = {
            "commander_oracle_id": str(self.commander.oracle_id),
            "budget_cents": 5_000,
        }
        payload.update(overrides)
        return self.client.post(
            reverse("brew"), payload, content_type="application/json"
        )


class BrewCacheTests(BrewFixture):
    def test_first_request_misses_and_second_hits(self):
        self.assertEqual(self.post()["X-Cache"], "MISS")
        self.assertEqual(self.post()["X-Cache"], "HIT")

    def test_a_hit_is_served_without_touching_the_database(self):
        """The strongest proof it came from cache: delete every card first.

        A cache that quietly re-solved would return infeasible_budget here.
        """
        primed = self.post().json()
        Card.objects.all().delete()
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Cache"], "HIT")
        self.assertEqual(
            [c["name"] for c in response.json()["spells"]],
            [c["name"] for c in primed["spells"]],
        )

    def test_a_different_budget_is_a_different_entry(self):
        self.post()
        self.assertEqual(self.post(budget_cents=6_000)["X-Cache"], "MISS")

    def test_a_different_land_count_is_a_different_entry(self):
        self.post()
        self.assertEqual(self.post(lands=38)["X-Cache"], "MISS")

    def test_auto_and_tier1_share_an_entry(self):
        """They resolve to the same strategy, so they must not solve twice."""
        self.assertEqual(self.post(strategy="auto")["X-Cache"], "MISS")
        self.assertEqual(self.post(strategy="tier1")["X-Cache"], "HIT")

    def test_tier0_is_a_different_entry(self):
        self.post(strategy="auto")
        self.assertEqual(self.post(strategy="tier0")["X-Cache"], "MISS")

    def test_upgrade_path_is_part_of_the_key(self):
        """Otherwise a request asking for the path gets a cached reply
        without one."""
        self.post(include_upgrade_path=False)
        response = self.post(include_upgrade_path=True)
        self.assertEqual(response["X-Cache"], "MISS")
        self.assertIn("upgrade_path", response.json())

    def test_owned_free_is_never_cached(self):
        """It depends on the CollectionItem table, which can change without
        the key changing."""
        first = self.post(owned_free=True)
        second = self.post(owned_free=True)
        self.assertNotIn("X-Cache", first)
        self.assertNotIn("X-Cache", second)

    @override_settings(BREW_CACHE_SECONDS=0)
    def test_zero_ttl_disables_caching(self):
        self.assertNotIn("X-Cache", self.post())
        self.assertNotIn("X-Cache", self.post())

    def test_infeasible_budget_is_not_cached(self):
        """Cheap to recompute, and it depends on current prices."""
        response = self.post(budget_cents=1)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("X-Cache", response)

    def test_key_ignores_fields_that_cannot_change_the_deck(self):
        base = {
            "commander_oracle_id": self.commander.oracle_id,
            "budget_cents": 5_000,
            "strategy": "auto",
            "lands": 36,
            "include_upgrade_path": False,
        }
        self.assertEqual(
            brew_cache_key(base), brew_cache_key({**base, "strategy": "tier1"})
        )
        self.assertNotEqual(brew_cache_key(base), brew_cache_key({**base, "lands": 37}))

    def test_key_is_namespaced_and_versioned(self):
        """So the whole cache can be retired without waiting out the TTL."""
        key = brew_cache_key(
            {
                "commander_oracle_id": self.commander.oracle_id,
                "budget_cents": 5_000,
                "strategy": "auto",
                "lands": 36,
                "include_upgrade_path": False,
            }
        )
        # Against the constant, not a literal: bumping the version is the
        # supported way to retire the cache and must not break this test.
        self.assertTrue(key.startswith(f"brew:{BREW_CACHE_VERSION}:"))
        self.assertRegex(BREW_CACHE_VERSION, r"^v\d+$")


class ThrottleTests(BrewFixture):
    def test_exceeding_the_brew_rate_returns_429(self):
        with throttled(brew="2/min", read="100/min"):
            self.assertEqual(self.post()["X-Cache"], "MISS")
            self.assertEqual(self.post(budget_cents=5_100).status_code, 200)
            self.assertEqual(self.post(budget_cents=5_200).status_code, 429)

    def test_a_cached_hit_still_counts_against_the_limit(self):
        """The limit protects the instance, and serving a hit is still work."""
        with throttled(brew="2/min", read="100/min"):
            self.post()
            self.post()
            self.assertEqual(self.post().status_code, 429)

    def test_reads_are_not_throttled_at_the_brew_rate(self):
        """Autocomplete is one indexed query; a brew is ~1.1s of CPU."""
        with throttled(brew="1/min", read="100/min"):
            self.post()
            for _ in range(10):
                self.assertEqual(
                    self.client.get(reverse("commanders")).status_code, 200
                )

    def test_exceeding_the_read_rate_returns_429(self):
        with throttled(brew="100/min", read="2/min"):
            self.client.get(reverse("commanders"))
            self.client.get(reverse("commanders"))
            self.assertEqual(self.client.get(reverse("commanders")).status_code, 429)

    def test_config_endpoint_is_throttled_as_a_read(self):
        with throttled(brew="100/min", read="1/min"):
            self.assertEqual(self.client.get(reverse("config")).status_code, 200)
            self.assertEqual(self.client.get(reverse("config")).status_code, 429)


class ThrottleIsolationTests(TestCase):
    def test_throttling_is_off_by_default_in_tests(self):
        """Guards the conftest fixture.

        Reads the *effective* DRF value, not `settings.REST_FRAMEWORK`.
        Asserting the setting passes even when throttling is still live,
        because DRF never re-reads it.
        """
        self.assertIsNone(SimpleRateThrottle.THROTTLE_RATES["brew"])
        self.assertIsNone(SimpleRateThrottle.THROTTLE_RATES["read"])

    def test_the_shipped_defaults_are_scoped_and_reads_are_looser(self):
        """Checked against the real settings dict, which is what a deploy
        uses even though DRF snapshots it at import."""
        from django.conf import settings as dj

        rates = dj.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        self.assertEqual(rates["brew"], "20/min")
        self.assertEqual(rates["read"], "120/min")
