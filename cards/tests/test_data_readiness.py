"""Tests for card-data readiness and the self-initialising boot path.

The interesting case is a load interrupted part-way. On a free instance,
which spins down after 15 minutes of inactivity, a restart can land in the
middle of a six-minute first load -- and a row-count check accepts 31k of
34.5k rows as "loaded", freezing the database permanently incomplete.
"""

from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from cards.classification import SYNERGY
from cards.models import MINIMUM_PLAUSIBLE_CARDS, Card, card_data_is_loaded
from cards.tests.test_api import make_card

TARGET = "cards.management.commands.bootstrap.call_command"


def load_cards(n, *, classified=True):
    """Create n cards, mimicking sync_cards (unclassified) or a full load."""
    Card.objects.bulk_create(
        [
            Card(
                oracle_id=f"00000000-0000-0000-0000-{i:012d}",
                scryfall_id=f"10000000-0000-0000-0000-{i:012d}",
                name=f"card-{i}",
                slug=f"card-{i}",
                cmc=1,
                type_line="Creature",
                color_identity=["R"],
                price_cents=100,
                legal_commander=True,
                primary_role=SYNERGY if classified else "",
                # The completion marker: only classify_cards sets this.
                role_source="heuristic" if classified else "",
            )
            for i in range(n)
        ]
    )


class ReadinessTests(TestCase):
    def test_an_empty_table_is_not_ready(self):
        self.assertFalse(card_data_is_loaded())

    def test_a_complete_load_is_ready(self):
        load_cards(MINIMUM_PLAUSIBLE_CARDS + 10)
        self.assertTrue(card_data_is_loaded())

    def test_a_plausible_but_unclassified_load_is_NOT_ready(self):
        """The bug this check exists for.

        31k of 34.5k rows passes any count-based threshold, but none of them
        are classified, so the deck builder has no roles to work with.
        """
        load_cards(31_000, classified=False)
        self.assertGreater(Card.objects.count(), MINIMUM_PLAUSIBLE_CARDS)
        self.assertFalse(card_data_is_loaded())

    def test_a_single_unclassified_card_blocks_readiness(self):
        """classify_cards is the last step; if it did not finish, the load
        did not finish."""
        load_cards(MINIMUM_PLAUSIBLE_CARDS + 10)
        self.assertTrue(card_data_is_loaded())
        make_card("Straggler", role_source="")
        self.assertFalse(card_data_is_loaded())

    def test_too_few_cards_is_not_ready_even_when_classified(self):
        load_cards(50)
        self.assertFalse(card_data_is_loaded())


class BootstrapIfEmptyTests(TestCase):
    def test_migrates_then_skips_the_load_when_data_is_present(self):
        load_cards(MINIMUM_PLAUSIBLE_CARDS + 10)
        with patch(TARGET) as mock:
            call_command("bootstrap", "--if-empty")
        called = [c.args[0] for c in mock.call_args_list]
        self.assertEqual(called, ["migrate"])

    def test_loads_when_the_table_is_empty(self):
        with (
            patch(TARGET) as mock,
            patch(
                "cards.management.commands.bootstrap.Command._card_count",
                return_value=30_000,
            ),
        ):
            call_command("bootstrap", "--if-empty")
        called = [c.args[0] for c in mock.call_args_list]
        self.assertEqual(called, ["migrate", "sync_cards", "classify_cards"])

    def test_reloads_an_interrupted_load(self):
        """A restart mid-sync must not leave the database frozen part-way."""
        load_cards(31_000, classified=False)
        with (
            patch(TARGET) as mock,
            patch(
                "cards.management.commands.bootstrap.Command._card_count",
                return_value=31_000,
            ),
        ):
            call_command("bootstrap", "--if-empty")
        called = [c.args[0] for c in mock.call_args_list]
        self.assertIn("sync_cards", called)
        self.assertIn("classify_cards", called)

    def test_skips_sync_catalogs_on_boot(self):
        """They are checked-in fixtures read from disk, so refreshing them is
        a maintenance task, not something to do on every container start."""
        with (
            patch(TARGET) as mock,
            patch(
                "cards.management.commands.bootstrap.Command._card_count",
                return_value=30_000,
            ),
        ):
            call_command("bootstrap", "--if-empty")
        self.assertNotIn("sync_catalogs", [c.args[0] for c in mock.call_args_list])


class ConfigEndpointTests(TestCase):
    def setUp(self):
        # data_is_ready() caches a true result for the process lifetime.
        import cards.views

        cards.views._data_ready = False
        self.addCleanup(setattr, cards.views, "_data_ready", False)

    def test_reports_not_ready_while_loading(self):
        body = self.client.get(reverse("config")).json()
        self.assertFalse(body["data_ready"])

    def test_reports_ready_once_loaded(self):
        load_cards(MINIMUM_PLAUSIBLE_CARDS + 10)
        body = self.client.get(reverse("config")).json()
        self.assertTrue(body["data_ready"])

    def test_readiness_is_cached_once_true(self):
        """So /api/config/ does not COUNT on every page load, which on a
        0.1 CPU instance is not free."""
        load_cards(MINIMUM_PLAUSIBLE_CARDS + 10)
        self.assertTrue(self.client.get(reverse("config")).json()["data_ready"])
        Card.objects.all().delete()
        self.assertTrue(self.client.get(reverse("config")).json()["data_ready"])
