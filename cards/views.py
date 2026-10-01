"""API views.

The brew endpoint is deterministic: identical inputs always produce an
identical deck, so it is safe to retry and safe to cache.
"""

from django.db.models import Q
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
from cards.solver import InfeasibleBudget, brew
from cards.tier1 import Tier1SynergyStrategy
from cards.upgrades import upgrade_path


class CommanderSearchView(generics.ListAPIView):
    """Commander autocomplete.

    Restricted to cards that may actually be a commander -- legendary
    creatures plus anything whose text says it can be -- rather than all
    34k cards.
    """

    serializer_class = CommanderSerializer

    def get_queryset(self):
        query = self.request.query_params.get("q", "").strip()
        queryset = Card.objects.filter(can_be_commander=True, legal_commander=True)
        if query:
            queryset = queryset.filter(name__icontains=query)
        # Most-played first, so "krenko" surfaces Mob Boss before the obscure
        # printings. Nulls last: unranked commanders are the rarest.
        return queryset.order_by("edhrec_rank", "name")[:25]


class CardDetailView(generics.RetrieveAPIView):
    serializer_class = CardSerializer
    lookup_field = "oracle_id"
    queryset = Card.objects.all()


class CardSearchView(generics.ListAPIView):
    serializer_class = CardSerializer

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
    operation is deterministic and side-effect free.
    """

    def post(self, request):
        form = BrewRequestSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data

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
            # budget instead of just saying "failed".
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
        return Response(payload)


class BrewSaveView(APIView):
    """Generate a deck and persist it."""

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
