from django.urls import path

from cards import views

urlpatterns = [
    path("commanders/", views.CommanderSearchView.as_view(), name="commanders"),
    path("cards/", views.CardSearchView.as_view(), name="card-search"),
    path("cards/<uuid:oracle_id>/", views.CardDetailView.as_view(), name="card-detail"),
    path("brew/", views.BrewView.as_view(), name="brew"),
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
