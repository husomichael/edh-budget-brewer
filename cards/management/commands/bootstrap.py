"""Take an environment from empty to serving brews, in one command.

A freshly deployed instance has an empty Card table, and every brew returns
`infeasible_budget` until the data is loaded. That is the single most common
way this deploy appears broken while being perfectly healthy, so the four
steps are wrapped here rather than left to the runbook: the order matters and
getting it wrong fails in ways that look like bugs.

    migrate          schema
    sync_catalogs    creature/land/artifact type catalogs
    sync_cards       ~25 MB from Scryfall, ~34.5k cards
    classify_cards   functional role per card

`classify_cards` has nothing to classify before `sync_cards`, and Tier 1 theme
detection needs the creature-type catalog from `sync_catalogs`.

Every step is idempotent, so re-running is safe and is the intended way to
refresh prices.

Usage:
    manage.py bootstrap              # first deploy: all four steps
    manage.py bootstrap --refresh    # nightly: prices and roles only
"""

import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from cards.models import Card

# Below this, something went wrong upstream even if every command exited 0.
# Scryfall's oracle set has been well above 30k for years, so a sync that
# lands under this is a truncated download or a changed bulk format, not a
# quiet year for Magic.
MINIMUM_PLAUSIBLE_CARDS = 25_000


class Command(BaseCommand):
    help = (
        "Load everything a new environment needs, in order: "
        "migrate, catalogs, cards, roles."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh",
            action="store_true",
            help=(
                "Skip migrate and sync_catalogs. For the nightly price "
                "refresh, where the schema and catalogs are already in place."
            ),
        )
        parser.add_argument(
            "--skip-sync",
            action="store_true",
            help=(
                "Skip the Scryfall download and reuse the file already on "
                "disk. For re-running classification after tuning rules."
            ),
        )

    def handle(self, *args, **options):
        refresh = options["refresh"]
        started = time.monotonic()

        steps = []
        if not refresh:
            steps.append(("migrate", {"interactive": False}))
            steps.append(("sync_catalogs", {}))
        if not options["skip_sync"]:
            steps.append(("sync_cards", {}))
        steps.append(("classify_cards", {}))

        before = self._card_count()
        plural = "" if len(steps) == 1 else "s"
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"{'Refreshing' if refresh else 'Bootstrapping'} "
                f"({len(steps)} step{plural}, {before} cards currently loaded)"
            )
        )

        for index, (name, kwargs) in enumerate(steps, start=1):
            self.stdout.write("")
            self.stdout.write(
                self.style.MIGRATE_HEADING(f"[{index}/{len(steps)}] {name}")
            )
            step_started = time.monotonic()
            # No try/except: a failure here must stop the run and exit
            # non-zero so the deploy or the cron job is marked failed. Half a
            # bootstrap that reports success is worse than a loud failure.
            #
            # Threading stdout/stderr through keeps the whole run on one
            # stream, so the deploy log reads in order instead of interleaving
            # each sub-command's output independently.
            call_command(name, stdout=self.stdout, stderr=self.stderr, **kwargs)
            self.stdout.write(f"    ({time.monotonic() - step_started:.1f}s)")

        after = self._card_count()
        elapsed = time.monotonic() - started

        # Log counts, so a silently failing sync is visible in the job output
        # rather than only showing up as every brew being infeasible.
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done in {elapsed:.1f}s. Cards: {before} -> {after} "
                f"({after - before:+d}), {self._classified()} classified."
            )
        )

        if after < MINIMUM_PLAUSIBLE_CARDS:
            raise CommandError(
                f"Only {after} cards loaded, expected at least "
                f"{MINIMUM_PLAUSIBLE_CARDS}. Every brew will return "
                f"infeasible_budget. Check the sync_cards output above."
            )

    def _card_count(self):
        return Card.objects.count()

    def _classified(self):
        return Card.objects.exclude(role_source="").count()
