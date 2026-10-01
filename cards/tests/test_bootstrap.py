"""Tests for the bootstrap command.

The step list is mocked rather than executed: the point of this command is
the *order* of the four steps and the guard on the result, not re-testing
sync_cards. A real run downloads 25 MB from Scryfall.
"""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from cards.tests.test_api import make_card

TARGET = "cards.management.commands.bootstrap.call_command"


def run(*args, cards=30_000, **kwargs):
    """Run bootstrap with its steps mocked and the plausibility guard passing."""
    out = StringIO()
    with (
        patch(TARGET) as mock,
        patch(
            "cards.management.commands.bootstrap.Command._card_count",
            return_value=cards,
        ),
    ):
        call_command("bootstrap", *args, stdout=out, **kwargs)
    return mock, out.getvalue()


class StepOrderTests(TestCase):
    def test_full_run_executes_all_four_steps_in_order(self):
        """classify_cards has nothing to classify before sync_cards, and
        Tier 1 needs the catalogs, so the order is load-bearing."""
        mock, _ = run()
        self.assertEqual(
            [c.args[0] for c in mock.call_args_list],
            ["migrate", "sync_catalogs", "sync_cards", "classify_cards"],
        )
        self.assertEqual(mock.call_args_list[0].kwargs["interactive"], False)

    def test_refresh_skips_migrate_and_catalogs(self):
        """The nightly job only needs prices and roles."""
        mock, _ = run("--refresh")
        self.assertEqual(
            [c.args[0] for c in mock.call_args_list],
            ["sync_cards", "classify_cards"],
        )

    def test_skip_sync_reuses_the_file_on_disk(self):
        mock, _ = run("--skip-sync")
        self.assertNotIn("sync_cards", [c.args[0] for c in mock.call_args_list])

    def test_refresh_with_skip_sync_only_classifies(self):
        mock, _ = run("--refresh", "--skip-sync")
        self.assertEqual([c.args[0] for c in mock.call_args_list], ["classify_cards"])


class ReportingTests(TestCase):
    def test_reports_card_counts(self):
        """A silently failing sync must be visible in the job output rather
        than only showing up as every brew being infeasible."""
        _, output = run(cards=34_558)
        self.assertIn("34558", output)
        self.assertIn("classified", output)

    def test_counts_are_singular_for_a_one_step_run(self):
        _, output = run("--refresh", "--skip-sync")
        self.assertIn("1 step,", output)


class PlausibilityGuardTests(TestCase):
    def test_an_implausibly_small_sync_fails_loudly(self):
        """Every command can exit 0 and still leave the app unusable: a
        truncated download or a changed bulk format."""
        with self.assertRaises(CommandError) as ctx:
            run(cards=12)
        self.assertIn("infeasible_budget", str(ctx.exception))

    def test_an_empty_database_fails_rather_than_reporting_success(self):
        with self.assertRaises(CommandError):
            run(cards=0)


class RealClassificationTests(TestCase):
    """One unmocked run, to prove the steps actually compose."""

    def test_classify_step_runs_against_real_rows(self):
        make_card("Sol Ring", type_line="Artifact", oracle_text="Add {C}{C}.")
        out = StringIO()
        with patch(
            "cards.management.commands.bootstrap.Command._card_count",
            return_value=30_000,
        ):
            call_command("bootstrap", "--refresh", "--skip-sync", stdout=out)
        output = out.getvalue()
        # Threaded through bootstrap's own stream, so a deploy log is one
        # readable sequence rather than interleaved sub-command output.
        self.assertIn("Classified 1 by heuristic", output)
        self.assertIn("[1/1] classify_cards", output)
        self.assertIn("1 classified", output)
