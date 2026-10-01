"""Candidate pool construction.

Everything upstream -- legality, color identity, pricing, roles, scoring --
resolves here. The solver receives a clean list of `Candidate` objects and
nothing else.
"""

from dataclasses import dataclass
from decimal import Decimal

from cards.models import Card
from cards.scoring import Tier0PopularityStrategy

# Fields pulled from the database. Using .values() rather than model instances
# avoids constructing ~24k Card objects per brew.
POOL_FIELDS = (
    "oracle_id",
    "name",
    "price_cents",
    "cmc",
    "type_line",
    "primary_role",
    "secondary_role",
    "edhrec_rank",
    "is_land",
    "is_basic",
    "color_identity",
)


@dataclass(frozen=True)
class Candidate:
    """One card the solver may choose, with everything it needs to decide."""

    oracle_id: str
    name: str
    price_cents: int
    cmc: Decimal
    type_line: str
    primary_role: str
    secondary_role: str
    is_land: bool
    is_basic: bool
    score: float

    @property
    def score_per_dollar(self):
        """Value density, used by the greedy fill.

        Free cards (basic lands, cards already owned) would divide by zero, so
        they are treated as maximally efficient -- which is correct: a free
        card that fills a needed slot is always worth taking.
        """
        if self.price_cents <= 0:
            return float("inf")
        return self.score / (self.price_cents / 100.0)


@dataclass(frozen=True)
class CandidatePool:
    commander: Card
    candidates: list
    tier: int
    tier_label: str

    def __len__(self):
        return len(self.candidates)

    def by_role(self, role):
        return [c for c in self.candidates if c.primary_role == role]

    def filling_role(self, role):
        """Candidates whose primary *or* secondary role matches.

        Used when a role's floor cannot be met from primaries alone -- a card
        that ramps and draws can cover either slot.
        """
        return [
            c
            for c in self.candidates
            if c.primary_role == role or c.secondary_role == role
        ]

    @property
    def description(self):
        return f"Tier {self.tier} - {self.tier_label}"


def build_pool(commander, strategy=None, owned_free=False, partner=None):
    """Assemble the scored, filtered candidate pool for a commander.

    Filters, in order of selectivity:

      * commander-legal and not banned
      * color identity is a subset of the commander's (Postgres array
        containment, GIN-indexed -- the hottest query in the project)
      * has a USD price, since an unpriceable card is unbuyable
      * is not the commander or partner itself
    """
    strategy = strategy or Tier0PopularityStrategy()

    qs = (
        Card.objects.filter(
            legal_commander=True,
            is_banned=False,
            price_cents__isnull=False,
            color_identity__contained_by=commander.color_identity,
        )
        .exclude(pk=commander.pk)
        .values(*POOL_FIELDS)
    )
    if partner is not None:
        qs = qs.exclude(pk=partner.pk)

    rows = list(qs)
    scored = strategy.score(rows, commander)

    owned = _owned_oracle_ids() if owned_free else set()

    candidates = [
        Candidate(
            oracle_id=str(row["oracle_id"]),
            name=row["name"],
            # Basic lands are free in practice and own-it-already pricing
            # zeroes out cards already in the collection.
            price_cents=0
            if (row["is_basic"] or str(row["oracle_id"]) in owned)
            else row["price_cents"],
            cmc=row["cmc"],
            type_line=row["type_line"],
            primary_role=row["primary_role"],
            secondary_role=row["secondary_role"],
            is_land=row["is_land"],
            is_basic=row["is_basic"],
            score=scored.scores.get(str(row["oracle_id"]), 0.0),
        )
        for row in rows
    ]

    return CandidatePool(
        commander=commander,
        candidates=candidates,
        tier=scored.tier,
        tier_label=scored.label,
    )


def _owned_oracle_ids():
    """Oracle IDs of cards in the user's collection.

    Returns empty until CollectionItem lands in #4; wired here so own-it-already
    pricing needs no change to the pool once that model exists.
    """
    return set()
