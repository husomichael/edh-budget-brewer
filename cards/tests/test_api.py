"""Tests for the HTTP API."""

import uuid

from django.test import TestCase
from django.urls import reverse

from cards.classification import LAND, SYNERGY
from cards.models import Card, CollectionItem, Deck


def make_card(name, **kwargs):
    defaults = {
        "oracle_id": uuid.uuid4(),
        "scryfall_id": uuid.uuid4(),
        "name": name,
        "cmc": 2,
        "mana_cost": "{1}{R}",
        "type_line": "Creature",
        "color_identity": ["R"],
        "price_cents": 100,
        "legal_commander": True,
        "edhrec_rank": 500,
        "primary_role": SYNERGY,
    }
    defaults.update(kwargs)
    return Card.objects.create(**defaults)


class CommanderSearchTests(TestCase):
    def setUp(self):
        self.commander = make_card(
            "Krenko, Mob Boss",
            type_line="Legendary Creature — Goblin Warrior",
            can_be_commander=True,
            edhrec_rank=1088,
        )
        make_card("Lightning Bolt")  # not a commander

    def test_returns_only_valid_commanders(self):
        response = self.client.get(reverse("commanders"))
        names = [r["name"] for r in response.json()["results"]]
        self.assertIn("Krenko, Mob Boss", names)
        self.assertNotIn("Lightning Bolt", names)

    def test_filters_by_query(self):
        make_card(
            "Edgar Markov",
            type_line="Legendary Creature — Vampire Knight",
            can_be_commander=True,
        )
        response = self.client.get(reverse("commanders"), {"q": "krenko"})
        names = [r["name"] for r in response.json()["results"]]
        self.assertEqual(names, ["Krenko, Mob Boss"])

    def test_orders_most_played_first(self):
        make_card(
            "Obscure Legend",
            type_line="Legendary Creature — Goblin",
            can_be_commander=True,
            edhrec_rank=20_000,
        )
        response = self.client.get(reverse("commanders"))
        names = [r["name"] for r in response.json()["results"]]
        self.assertLess(names.index("Krenko, Mob Boss"), names.index("Obscure Legend"))


class BrewEndpointTests(TestCase):
    def setUp(self):
        self.commander = make_card(
            "Brew Cmdr",
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

    def _post(self, **overrides):
        payload = {
            "commander_oracle_id": str(self.commander.oracle_id),
            "budget_cents": 5_000,
        }
        payload.update(overrides)
        return self.client.post(
            reverse("brew"), payload, content_type="application/json"
        )

    def test_returns_a_complete_deck(self):
        data = self._post().json()
        self.assertEqual(data["card_count"], 100)
        self.assertLessEqual(data["total_cents"], 5_000)
        self.assertFalse(data["over_budget"])
        self.assertEqual(len(data["spells"]), 63)

    def test_reports_the_scoring_tier(self):
        """The UI must be able to tell a generic deck from a themed one."""
        data = self._post().json()
        self.assertIn("tier", data)
        self.assertIn("tier_label", data)

    def test_tier0_can_be_requested_explicitly(self):
        data = self._post(strategy="tier0").json()
        self.assertEqual(data["tier"], 0)

    def test_includes_a_paste_ready_decklist(self):
        data = self._post().json()
        lines = data["text_decklist"].splitlines()
        self.assertTrue(lines[0].startswith("1 Brew Cmdr"))
        self.assertEqual(sum(int(line.split()[0]) for line in lines), 100)

    def test_is_deterministic_across_requests(self):
        first = self._post().json()
        second = self._post().json()
        self.assertEqual(
            [c["name"] for c in first["spells"]],
            [c["name"] for c in second["spells"]],
        )

    def test_infeasible_budget_returns_400_with_the_minimum(self):
        response = self._post(budget_cents=1)
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["code"], "infeasible_budget")
        self.assertGreater(body["minimum_cents"], 0)

    def test_unknown_commander_returns_404(self):
        response = self._post(commander_oracle_id=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 404)

    def test_non_commander_card_is_rejected(self):
        plain = make_card("Just A Spell")
        response = self._post(commander_oracle_id=str(plain.oracle_id))
        self.assertEqual(response.status_code, 404)

    def test_negative_budget_is_rejected(self):
        self.assertEqual(self._post(budget_cents=-100).status_code, 400)

    def test_bad_strategy_is_rejected(self):
        self.assertEqual(self._post(strategy="telepathy").status_code, 400)

    def test_upgrade_path_is_opt_in(self):
        self.assertNotIn("upgrade_path", self._post().json())
        data = self._post(include_upgrade_path=True).json()
        self.assertIn("upgrade_path", data)
        self.assertTrue(data["upgrade_path"]["steps"])

    def test_save_endpoint_persists_the_deck(self):
        response = self.client.post(
            reverse("brew-save"),
            {
                "commander_oracle_id": str(self.commander.oracle_id),
                "budget_cents": 5_000,
                "name": "API Deck",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Deck.objects.count(), 1)
        self.assertEqual(response.json()["name"], "API Deck")


class CollectionImportTests(TestCase):
    def setUp(self):
        make_card("Sol Ring", price_cents=154)
        make_card("Lim-Dûl's Vault", price_cents=300)
        make_card("Fire // Ice", price_cents=100)

    def _import(self, text, replace=False):
        return self.client.post(
            reverse("collection-import"),
            {"text": text, "replace": replace},
            content_type="application/json",
        ).json()

    def test_imports_a_pasted_list(self):
        body = self._import("1 Sol Ring\n1x Fire // Ice")
        self.assertEqual(body["created"], 2)
        self.assertEqual(CollectionItem.objects.count(), 2)

    def test_skips_headers_comments_and_totals(self):
        body = self._import("// Commander\nDeck\n# note\n1 Sol Ring\nTotal: 1")
        self.assertEqual(body["created"], 1)

    def test_strips_set_codes_and_collector_numbers(self):
        self.assertEqual(self._import("1 Sol Ring (LTR) 123")["created"], 1)

    def test_folds_accents(self):
        """People paste 'Lim-Dul' for 'Lim-Dûl'."""
        body = self._import("1 Lim-Dul's Vault")
        self.assertEqual(body["created"], 1)
        self.assertEqual(body["unresolved"], [])

    def test_resolves_a_split_card_by_its_front_face(self):
        body = self._import("1 Fire")
        self.assertEqual(body["created"], 1)

    def test_unresolved_names_are_reported_not_dropped(self):
        """A bad paste must be obvious rather than silently thinning the
        collection."""
        body = self._import("1 Sol Ring\n1 Not A Real Card")
        self.assertEqual(body["created"], 1)
        self.assertEqual(body["unresolved"], ["Not A Real Card"])
        self.assertIn("1 name unresolved", body["detail"])

    def test_empty_paste_is_handled(self):
        body = self._import("\n\n// nothing here\n")
        self.assertEqual(body["parsed"], 0)
        self.assertIn("No card lines", body["detail"])

    def test_replace_clears_the_existing_collection(self):
        self._import("1 Sol Ring")
        self._import("1 Fire // Ice", replace=True)
        names = list(CollectionItem.objects.values_list("card__name", flat=True))
        self.assertEqual(names, ["Fire // Ice"])
