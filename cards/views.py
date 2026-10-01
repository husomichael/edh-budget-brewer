"""API views.

The brew endpoint is deterministic: identical inputs always produce an
identical deck, so it is safe to retry and safe to cache.
"""

import hashlib

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from cards.decks import save_brew
from cards.importers import import_collection
from cards.models import Card, CollectionItem, Deck
from cards.pool import build_pool
from cards.scoring import Tier0PopularityStrategy
from cards.serializers import (
    BrewRequestSerializer,
    CardSerializer,
    CollectionImportSerializer,
    CollectionItemSerializer,
    CommanderSerializer,
    DeckDetailSerializer,
    DeckSerializer,
    serialize_brew,
    serialize_upgrade_path,
)
from cards.slugs import resolve_commander_slug
from cards.solver import InfeasibleBudget, brew
from cards.tier1 import Tier1SynergyStrategy
from cards.upgrades import upgrade_path

# Bump when the brew payload shape or the solver changes, to retire every
# cached response in one move rather than waiting out the TTL.
BREW_CACHE_VERSION = "v2"


def brew_cache_key(data):
    """Cache key for a brew request, from the full determinism key.

    Every input that can change the output is included. `owned_free` is
    handled by the caller, which declines to cache at all when it is set --
    those results depend on the CollectionItem table, which can change under
    us, and a 24h stale deck priced against someone else's collection would
    be wrong rather than merely old.

    `auto` and `tier1` are normalized together because they resolve to the
    same strategy, so the two spellings share a cache entry.
    """
    strategy = "tier0" if data["strategy"] == "tier0" else "tier1"
    parts = (
        str(data["commander_oracle_id"]),
        data["budget_cents"],
        strategy,
        data["lands"],
        data["include_upgrade_path"],
    )
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return f"brew:{BREW_CACHE_VERSION}:{digest}"


class ConfigView(APIView):
    """Runtime feature flags for the frontend.

    Exists so one built bundle serves both the local tool and the public demo:
    the UI asks which it is talking to instead of being compiled per
    deployment.
    """

    throttle_scope = "read"

    def get(self, request):
        return Response({"demo_mode": settings.DEMO_MODE})


class CommanderSearchView(generics.ListAPIView):
    """Commander autocomplete.

    Restricted to cards that may actually be a commander -- legendary
    creatures plus anything whose text says it can be -- rather than all
    34k cards.
    """

    serializer_class = CommanderSerializer
    throttle_scope = "read"

    def get_queryset(self):
        query = self.request.query_params.get("q", "").strip()
        queryset = Card.objects.filter(can_be_commander=True, legal_commander=True)
        if query:
            queryset = queryset.filter(name__icontains=query)
        # Most-played first, so "krenko" surfaces Mob Boss before the obscure
        # printings. Nulls last: unranked commanders are the rarest.
        return queryset.order_by("edhrec_rank", "name")[:25]


class CommanderBySlugView(APIView):
    """Resolve a share-URL slug to a commander (#21).

    Separate from the autocomplete because a share link needs an exact
    answer, not a ranked list of near-matches.
    """

    throttle_scope = "read"

    def get(self, request, slug):
        commander = resolve_commander_slug(slug)
        if commander is None:
            # A specific message, because the alternative is a blank page and
            # no way to tell a typo from a card that cannot be a commander.
            return Response(
                {
                    "detail": (
                        f"No commander matches '{slug}'. It may be "
                        f"misspelled, or not legal as a commander."
                    ),
                    "code": "commander_slug_not_found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(CommanderSerializer(commander).data)


class CardDetailView(generics.RetrieveAPIView):
    serializer_class = CardSerializer
    throttle_scope = "read"
    lookup_field = "oracle_id"
    queryset = Card.objects.all()


class CardSearchView(generics.ListAPIView):
    serializer_class = CardSerializer
    throttle_scope = "read"

    def get_queryset(self):
        query = self.request.query_params.get("q", "").strip()
        queryset = Card.objects.filter(legal_commander=True)
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(type_line__icontains=query)
            )
        return queryset.order_by("edhrec_rank", "name")[:50]


class BrewView(APIView):
    """Generate a deck.

    POST rather than GET because the input is a structured body, but the
    operation is deterministic and side-effect free -- which is exactly what
    makes the response cacheable.
    """

    throttle_scope = "brew"

    def post(self, request):
        form = BrewRequestSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data

        # Not cached when pricing against a collection: the result depends on
        # the CollectionItem table, which can change without the key changing.
        cacheable = settings.BREW_CACHE_SECONDS > 0 and not data["owned_free"]
        key = brew_cache_key(data) if cacheable else None

        if key is not None:
            hit = cache.get(key)
            if hit is not None:
                response = Response(hit)
                response["X-Cache"] = "HIT"
                return response

        commander = Card.objects.filter(
            oracle_id=data["commander_oracle_id"], can_be_commander=True
        ).first()
        if commander is None:
            return Response(
                {
                    "detail": "No commander with that oracle_id.",
                    "code": "commander_not_found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        strategy = (
            Tier0PopularityStrategy()
            if data["strategy"] == "tier0"
            else Tier1SynergyStrategy()
        )
        pool = build_pool(commander, strategy=strategy, owned_free=data["owned_free"])

        try:
            result = brew(pool, data["budget_cents"], land_count=data["lands"])
        except InfeasibleBudget as exc:
            # 400 with the real minimum, so the UI can offer to raise the
            # budget instead of just saying "failed". Deliberately not cached:
            # it is cheap to recompute and depends on current prices.
            return Response(
                {
                    "detail": str(exc),
                    "code": "infeasible_budget",
                    "minimum_cents": exc.minimum_cents,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = serialize_brew(result)
        if data["include_upgrade_path"]:
            payload["upgrade_path"] = serialize_upgrade_path(
                upgrade_path(pool, data["budget_cents"])
            )

        # When this deck was priced. Set before caching, so a cached response
        # keeps the timestamp of the solve that produced it rather than
        # claiming to be fresh -- which is what makes a shared link honest
        # about prices having moved. Accurate to within a day: card prices
        # come from the nightly Scryfall refresh.
        payload["priced_at"] = timezone.now().isoformat()

        if key is not None:
            cache.set(key, payload, settings.BREW_CACHE_SECONDS)

        response = Response(payload)
        if key is not None:
            response["X-Cache"] = "MISS"
        return response


class BrewSaveView(APIView):
    """Generate a deck and persist it."""

    # Same solve cost as BrewView, so the same budget. Not cached: it writes.
    throttle_scope = "brew"

    def post(self, request):
        form = BrewRequestSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data

        commander = Card.objects.filter(
            oracle_id=data["commander_oracle_id"], can_be_commander=True
        ).first()
        if commander is None:
            return Response(
                {"detail": "No commander with that oracle_id."},
                status=status.HTTP_404_NOT_FOUND,
            )

        strategy = (
            Tier0PopularityStrategy()
            if data["strategy"] == "tier0"
            else Tier1SynergyStrategy()
        )
        pool = build_pool(commander, strategy=strategy, owned_free=data["owned_free"])
        try:
            result = brew(pool, data["budget_cents"], land_count=data["lands"])
        except InfeasibleBudget as exc:
            return Response(
                {
                    "detail": str(exc),
                    "code": "infeasible_budget",
                    "minimum_cents": exc.minimum_cents,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        deck = save_brew(result, name=request.data.get("name") or None)
        return Response(DeckDetailSerializer(deck).data, status=status.HTTP_201_CREATED)


class DeckListView(generics.ListAPIView):
    serializer_class = DeckSerializer

    def get_queryset(self):
        return Deck.objects.select_related("commander", "partner").prefetch_related(
            "cards__card"
        )


class DeckDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DeckDetailSerializer
    queryset = Deck.objects.select_related("commander").prefetch_related("cards__card")


class CollectionListView(generics.ListCreateAPIView):
    serializer_class = CollectionItemSerializer
    queryset = CollectionItem.objects.select_related("card")


class CollectionItemView(generics.RetrieveDestroyAPIView):
    serializer_class = CollectionItemSerializer
    queryset = CollectionItem.objects.select_related("card")


class CollectionImportView(APIView):
    """Bulk-load a pasted collection list."""

    def post(self, request):
        form = CollectionImportSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        summary = import_collection(
            form.validated_data["text"], replace=form.validated_data["replace"]
        )
        return Response(summary)
