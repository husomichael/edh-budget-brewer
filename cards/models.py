"""Card data mirrored from Scryfall.

This table is read-only application data. It is populated by
`manage.py sync_cards` and must never be hand-edited -- the next sync would
silently overwrite the change.
"""

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models

from cards.classification import ROLE_CHOICES, SYNERGY

# Scryfall's WUBRG color codes.
COLOR_CHOICES = [
    ("W", "White"),
    ("U", "Blue"),
    ("B", "Black"),
    ("R", "Red"),
    ("G", "Green"),
]


class Card(models.Model):
    # oracle_id is stable across printings; scryfall_id identifies one printing.
    # We sync the `oracle_cards` bulk file, which is one row per logical card,
    # so oracle_id is the natural key.
    oracle_id = models.UUIDField(unique=True)
    # Not unique: this is whichever printing the oracle_cards file picked as
    # representative, and that choice can change between syncs. Making it
    # unique would make upserts fail on a second unique constraint.
    scryfall_id = models.UUIDField()

    name = models.CharField(max_length=300, db_index=True)
    mana_cost = models.CharField(max_length=100, blank=True)
    # Wide enough for Un-set absurdities: Gleemax costs {1000000}, so a
    # 5-digit field overflows on a real card in the bulk data.
    cmc = models.DecimalField(max_digits=12, decimal_places=1, default=0)
    type_line = models.CharField(max_length=300, blank=True)
    oracle_text = models.TextField(blank=True)

    # ArrayField rather than JSONField so color identity can be tested with
    # Postgres' array containment operator: a card is castable in a deck when
    # its color identity is a subset of the commander's.
    #   Card.objects.filter(color_identity__contained_by=["W", "U"])
    # which compiles to `color_identity <@ ARRAY['W','U']` and uses the GIN
    # index below. JSONField cannot do this without a sequential scan.
    color_identity = ArrayField(
        models.CharField(max_length=1, choices=COLOR_CHOICES),
        default=list,
        blank=True,
    )
    colors = ArrayField(
        models.CharField(max_length=1, choices=COLOR_CHOICES),
        default=list,
        blank=True,
    )

    # Money is stored as integer cents. The optimizer sums ~99 prices per
    # candidate deck across thousands of candidate swaps; float dollars
    # accumulate rounding error and produce decks that miss the budget by a
    # few dollars for no visible reason.
    price_cents = models.IntegerField(null=True, blank=True)
    price_updated = models.DateTimeField(null=True, blank=True)

    legal_commander = models.BooleanField(default=False)
    is_banned = models.BooleanField(default=False)

    # Global EDH popularity rank from Scryfall (lower is more popular). This is
    # the Tier 0 scoring signal; it is not commander-specific.
    edhrec_rank = models.IntegerField(null=True, blank=True, db_index=True)

    is_land = models.BooleanField(default=False)
    is_basic = models.BooleanField(default=False)

    # Legendary creatures and anything whose text says it can be a commander.
    can_be_commander = models.BooleanField(default=False)

    layout = models.CharField(max_length=40, blank=True)
    image_uri = models.URLField(max_length=500, blank=True)

    # Functional role, assigned by `manage.py classify_cards`. Stored rather
    # than computed so the candidate pool can filter and group on it in SQL.
    # Kept out of sync_cards because classification rules get tuned often and
    # re-downloading the bulk file to re-tune would be wasteful.
    primary_role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default=SYNERGY, db_index=True
    )
    secondary_role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, blank=True, default=""
    )
    role_source = models.CharField(
        max_length=10,
        default="",
        help_text="'heuristic' or 'override' -- where this role came from.",
    )

    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            GinIndex(fields=["color_identity"]),
            # Candidate-pool queries always filter on these two together.
            models.Index(
                fields=["legal_commander", "edhrec_rank"],
                name="card_legal_rank_idx",
            ),
            models.Index(fields=["can_be_commander"], name="card_is_commander_idx"),
            models.Index(
                fields=["primary_role", "edhrec_rank"], name="card_role_rank_idx"
            ),
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def price_dollars(self):
        """Price as a display string. None when Scryfall has no USD price."""
        if self.price_cents is None:
            return None
        return f"${self.price_cents / 100:.2f}"

    @property
    def is_priceable(self):
        """Whether this card can be bought, and so considered by the optimizer.

        A card with no USD price is unbuyable. It must not be treated as free,
        or the optimizer will happily 'afford' it.
        """
        return self.price_cents is not None
