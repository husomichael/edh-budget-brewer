"""API serialization.

Brew results are plain dataclasses rather than models, so these are mostly
explicit dicts rather than ModelSerializers. That keeps the wire format stable
even as the solver's internals change.
"""

from rest_framework import serializers

from cards.formats import as_text
from cards.models import Card, CollectionItem, Deck


class CommanderSerializer(serializers.ModelSerializer):
    """Shape used by the commander autocomplete."""

    class Meta:
        model = Card
        fields = [
            "oracle_id",
            "name",
            "type_line",
            "color_identity",
            "image_uri",
            "edhrec_rank",
            "price_cents",
        ]


class CardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Card
        fields = [
            "oracle_id",
            "name",
            "mana_cost",
            "cmc",
            "type_line",
            "oracle_text",
            "color_identity",
            "price_cents",
            "edhrec_rank",
            "primary_role",
            "secondary_role",
            "is_land",
            "is_basic",
            "can_be_commander",
            "image_uri",
        ]


class BrewRequestSerializer(serializers.Serializer):
    """Validated input for POST /api/brew/."""

    commander_oracle_id = serializers.UUIDField()
    budget_cents = serializers.IntegerField(min_value=1, max_value=100_000_000)
    strategy = serializers.ChoiceField(
        choices=["auto", "tier0", "tier1"], default="auto"
    )
    owned_free = serializers.BooleanField(default=False)
    lands = serializers.IntegerField(min_value=20, max_value=48, default=36)
    include_upgrade_path = serializers.BooleanField(default=False)


class CollectionImportSerializer(serializers.Serializer):
    """A pasted decklist or collection export."""

    text = serializers.CharField(max_length=500_000)
    replace = serializers.BooleanField(default=False)


# -- brew output -------------------------------------------------------------


def serialize_candidate(cand, quantity=1):
    return {
        "oracle_id": cand.oracle_id,
        "name": cand.name,
        "quantity": quantity,
        "price_cents": cand.price_cents,
        "retail_cents": cand.retail_cents,
        "is_owned": cand.is_owned,
        "locked_in": cand.locked_in,
        "cmc": float(cand.cmc),
        "mana_cost": cand.mana_cost,
        "type_line": cand.type_line,
        "role": cand.primary_role,
        "secondary_role": cand.secondary_role,
        "score": round(cand.score, 4),
    }


def serialize_brew(result):
    return {
        "commander": {
            "oracle_id": str(result.commander.oracle_id),
            "name": result.commander.name,
            "type_line": result.commander.type_line,
            "color_identity": result.commander.color_identity,
            "image_uri": result.commander.image_uri,
        },
        "budget_cents": result.budget_cents,
        "total_cents": result.total_cents,
        "retail_cents": result.retail_cents,
        "land_cents": result.land_cents,
        "spell_cents": result.spell_cents,
        "over_budget": result.total_cents > result.budget_cents,
        "card_count": result.card_count,
        # Which engine produced this deck. The UI must show it: a tier 0 deck
        # is in the right colors but is not synergy-aware.
        "tier": result.tier,
        "tier_label": result.tier_label,
        "curve": result.curve,
        "role_counts": result.role_counts,
        "role_coverage": result.role_coverage,
        # Structured, not prose, so the UI can render each kind differently.
        "warnings": result.warnings,
        "owned_count": len(result.owned_cards),
        "spells": [serialize_candidate(c) for c in result.spells],
        "lands": [serialize_candidate(c, q) for c, q in result.lands],
        "text_decklist": as_text(result),
    }


def serialize_upgrade_path(path):
    return {
        "base_total_cents": path.base.total_cents,
        "base_score": round(path.base.total_score, 3),
        "best_next_buys": [serialize_candidate(c) for c in path.best_next_buys],
        "steps": [
            {
                "label": step.label,
                "budget_cents": step.budget_cents,
                "total_cents": step.total_cents,
                "score": round(step.score, 3),
                "score_delta": round(step.score_delta, 3),
                "spend_delta_cents": step.spend_delta_cents,
                "cost_per_point": (
                    round(step.cost_per_point, 2)
                    if step.cost_per_point is not None
                    else None
                ),
                "is_no_limit": step.is_no_limit,
                "added": [serialize_candidate(c) for c in step.added],
                "removed": [serialize_candidate(c) for c in step.removed],
            }
            for step in path.steps
        ],
    }


class DeckCardSerializer(serializers.Serializer):
    name = serializers.CharField(source="card.name")
    oracle_id = serializers.UUIDField(source="card.oracle_id")
    quantity = serializers.IntegerField()
    role = serializers.CharField()
    price_at_generation = serializers.IntegerField(allow_null=True)
    price_cents = serializers.IntegerField(source="card.price_cents", allow_null=True)
    image_uri = serializers.CharField(source="card.image_uri")


class DeckSerializer(serializers.ModelSerializer):
    commander_name = serializers.CharField(source="commander.name", read_only=True)
    card_count = serializers.IntegerField(read_only=True)
    total_cents = serializers.IntegerField(read_only=True)
    generation_cents = serializers.IntegerField(read_only=True)

    class Meta:
        model = Deck
        fields = [
            "id",
            "name",
            "commander",
            "commander_name",
            "partner",
            "is_assembled",
            "budget_cents",
            "scoring_tier",
            "generated_at",
            "created_at",
            "card_count",
            "total_cents",
            "generation_cents",
        ]
        read_only_fields = ["created_at", "generated_at", "scoring_tier"]


class DeckDetailSerializer(DeckSerializer):
    cards = DeckCardSerializer(many=True, read_only=True)

    class Meta(DeckSerializer.Meta):
        fields = DeckSerializer.Meta.fields + ["cards"]


class CollectionItemSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="card.name", read_only=True)
    price_cents = serializers.IntegerField(source="card.price_cents", read_only=True)

    class Meta:
        model = CollectionItem
        fields = ["id", "card", "name", "quantity", "price_cents", "added_at"]
