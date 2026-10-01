"""API routes.

Split into two lists so demo mode can drop the stateful half wholesale. The
routes are not *registered* under `DEMO_MODE` rather than being permission
guarded, so the public demo 404s instead of advertising a feature it refuses.
"""

from django.conf import settings
from django.urls import path

from cards import views

# Safe to expose publicly: reads, plus a brew that has no side effects.
public_urlpatterns = [
    path("config/", views.ConfigView.as_view(), name="config"),
    path("commanders/", views.CommanderSearchView.as_view(), name="commanders"),
    path(
        "commanders/<slug:slug>/",
        views.CommanderBySlugView.as_view(),
        name="commander-by-slug",
    ),
    path("cards/", views.CardSearchView.as_view(), name="card-search"),
    path("cards/<uuid:oracle_id>/", views.CardDetailView.as_view(), name="card-detail"),
    path("brew/", views.BrewView.as_view(), name="brew"),
]

# Everything that touches server state. Decks and the collection are global --
# there is no owner field -- so even their read routes are local-only: they
# expose one shared collection to every visitor.
stateful_urlpatterns = [
    path("brew/save/", views.BrewSaveView.as_view(), name="brew-save"),
    path("decks/", views.DeckListView.as_view(), name="deck-list"),
    path("decks/<int:pk>/", views.DeckDetailView.as_view(), name="deck-detail"),
    path("collection/", views.CollectionListView.as_view(), name="collection"),
    path(
        "collection/import/",
        views.CollectionImportView.as_view(),
        name="collection-import",
    ),
    path(
        "collection/<int:pk>/",
        views.CollectionItemView.as_view(),
        name="collection-item",
    ),
]

urlpatterns = list(public_urlpatterns)
if not settings.DEMO_MODE:
    urlpatterns += stateful_urlpatterns
