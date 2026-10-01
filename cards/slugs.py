"""Readable slugs for share URLs (#21).

A shared link carries the deck in its parameters rather than a stored id,
which works only because the solver is deterministic. The commander is
identified by a slug rather than an oracle_id so the link reads as a link:

    /?commander=krenko-mob-boss&budget=100

Slugs are derived from the full card name, never a prefix. `Krenko, Mob Boss`
and `Krenko, Tin Street Kingpin` have to stay distinct, and they do:
`krenko-mob-boss` and `krenko-tin-street-kingpin`.
"""

from django.utils.text import slugify

from cards.models import Card


def card_slug(name):
    """Slugify a card name. Accents fold, so `Lim-Dûl's Vault` is usable."""
    return slugify(name)[:320]


def resolve_commander_slug(slug):
    """Find the commander a slug refers to, or None.

    Verified against the full card set: all 3,441 commander-legal cards
    produce distinct slugs today, so this is a single-row lookup in practice.
    The tie-break exists because nothing in Scryfall's data *guarantees* that,
    and an ambiguous share link must still resolve to the same deck every
    time -- a link that alternates between two commanders is worse than one
    that picks the more likely of them and sticks to it.

    Most-played first, then oracle_id, matching the project convention that
    every sort key ends in oracle_id.
    """
    normalized = card_slug(slug or "")
    if not normalized:
        return None
    return (
        Card.objects.filter(
            slug=normalized, can_be_commander=True, legal_commander=True
        )
        .order_by("edhrec_rank", "oracle_id")
        .first()
    )
