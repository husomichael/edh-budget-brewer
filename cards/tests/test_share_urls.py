"""Tests for share-URL slug resolution and priced_at (#21)."""

from django.test import TestCase
from django.urls import reverse

from cards.classification import LAND
from cards.models import Card
from cards.slugs import card_slug, resolve_commander_slug
from cards.tests.test_api import make_card


def make_commander(name, **kwargs):
    kwargs.setdefault("type_line", "Legendary Creature — Goblin Warrior")
    kwargs.setdefault("can_be_commander", True)
    card = make_card(name, **kwargs)
    # sync_cards sets the slug; make_card bypasses it.
    card.slug = card_slug(name)
    card.save(update_fields=["slug"])
    return card


class CardSlugTests(TestCase):
    def test_slugifies_a_full_name(self):
        self.assertEqual(card_slug("Krenko, Mob Boss"), "krenko-mob-boss")

    def test_two_krenkos_do_not_collide(self):
        """The whole reason the slug is the full name and not a prefix."""
        self.assertNotEqual(
            card_slug("Krenko, Mob Boss"), card_slug("Krenko, Tin Street Kingpin")
        )

    def test_folds_accents(self):
        """So a shared link is typeable and survives a copy-paste."""
        self.assertEqual(card_slug("Lim-Dûl's Vault"), "lim-duls-vault")

    def test_a_nameless_card_slugs_to_empty(self):
        """The `_____` joke cards. Never commanders, but must not crash."""
        self.assertEqual(card_slug("_____"), "")


class SlugResolutionTests(TestCase):
    def setUp(self):
        self.mob_boss = make_commander("Krenko, Mob Boss", edhrec_rank=1088)
        self.kingpin = make_commander("Krenko, Tin Street Kingpin", edhrec_rank=2500)

    def test_resolves_each_krenko_to_itself(self):
        self.assertEqual(resolve_commander_slug("krenko-mob-boss"), self.mob_boss)
        self.assertEqual(
            resolve_commander_slug("krenko-tin-street-kingpin"), self.kingpin
        )

    def test_unknown_slug_is_none(self):
        self.assertIsNone(resolve_commander_slug("not-a-real-commander"))

    def test_empty_slug_is_none(self):
        """Must not match the nameless cards, whose slug is also empty."""
        self.assertIsNone(resolve_commander_slug(""))
        self.assertIsNone(resolve_commander_slug(None))

    def test_a_non_commander_does_not_resolve(self):
        sol_ring = make_card("Sol Ring", type_line="Artifact")
        Card.objects.filter(pk=sol_ring.pk).update(slug="sol-ring")
        self.assertIsNone(resolve_commander_slug("sol-ring"))

    def test_an_illegal_commander_does_not_resolve(self):
        make_commander("Banned Legend", legal_commander=False, is_banned=True)
        self.assertIsNone(resolve_commander_slug("banned-legend"))

    def test_a_collision_resolves_deterministically(self):
        """Nothing guarantees slugs stay unique, and a share link that
        alternates between two commanders is worse than one that picks."""
        Card.objects.filter(pk=self.kingpin.pk).update(slug="krenko-mob-boss")
        first = resolve_commander_slug("krenko-mob-boss")
        second = resolve_commander_slug("krenko-mob-boss")
        self.assertEqual(first, second)
        # Most-played wins: Mob Boss at rank 1088 over Kingpin at 2500.
        self.assertEqual(first, self.mob_boss)

    def test_input_is_normalized_before_lookup(self):
        """A hand-typed link with odd casing or spacing still resolves."""
        self.assertEqual(resolve_commander_slug("Krenko, Mob Boss"), self.mob_boss)


class SlugEndpointTests(TestCase):
    def setUp(self):
        self.commander = make_commander("Krenko, Mob Boss", edhrec_rank=1088)

    def test_returns_the_commander_with_its_slug(self):
        url = reverse("commander-by-slug", args=["krenko-mob-boss"])
        body = self.client.get(url).json()
        self.assertEqual(body["name"], "Krenko, Mob Boss")
        self.assertEqual(body["slug"], "krenko-mob-boss")
        self.assertEqual(body["oracle_id"], str(self.commander.oracle_id))

    def test_unknown_slug_404s_with_an_explanation(self):
        """A blank page gives no way to tell a typo from an illegal card."""
        url = reverse("commander-by-slug", args=["nonsense-commander"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertEqual(body["code"], "commander_slug_not_found")
        self.assertIn("nonsense-commander", body["detail"])

    def test_autocomplete_exposes_the_slug_for_building_links(self):
        results = self.client.get(reverse("commanders")).json()["results"]
        self.assertEqual(results[0]["slug"], "krenko-mob-boss")


class PricedAtTests(TestCase):
    def setUp(self):
        self.commander = make_commander(
            "Priced Cmdr", oracle_text="Create a 1/1 red Goblin creature token."
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

    def test_brew_reports_when_it_was_priced(self):
        self.assertIn("priced_at", self.post().json())

    def test_a_cached_result_keeps_its_original_timestamp(self):
        """Otherwise a day-old cached deck claims to be priced right now."""
        first = self.post()
        second = self.post()
        self.assertEqual(first["X-Cache"], "MISS")
        self.assertEqual(second["X-Cache"], "HIT")
        self.assertEqual(first.json()["priced_at"], second.json()["priced_at"])
