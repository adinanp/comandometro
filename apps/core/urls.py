from django.urls import path
from apps.core.views import (
    DashboardView,
    DeckCreateAjaxView,
    DeckCreateView,
    DeckDeleteView,
    DeckDetailView,
    DeckListView,
    GameCreateView,
    GameDetailView,
    GameListView,
    GameUpdateView,
    MyDecksView,
    MyProfileView,
    PlayerListView,
    PlayerProfileView,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("meu-perfil/", MyProfileView.as_view(), name="my-profile"),
    path("meus-decks/", MyDecksView.as_view(), name="my-decks"),
    path("jogadores/", PlayerListView.as_view(), name="player-list"),
    path("jogadores/<int:pk>/", PlayerProfileView.as_view(), name="player-profile"),
    path("partidas/", GameListView.as_view(), name="game-list"),
    path("partidas/nova/", GameCreateView.as_view(), name="game-create"),
    path("partidas/<int:pk>/", GameDetailView.as_view(), name="game-detail"),
    path("partidas/<int:pk>/editar/", GameUpdateView.as_view(), name="game-update"),
    path("decks/", DeckListView.as_view(), name="deck-list"),
    path("decks/novo/", DeckCreateView.as_view(), name="deck-create"),
    path("decks/novo/ajax/", DeckCreateAjaxView.as_view(), name="deck-create-ajax"),
    path("decks/<int:pk>/", DeckDetailView.as_view(), name="deck-detail"),
    path("decks/<int:pk>/excluir/", DeckDeleteView.as_view(), name="deck-delete"),
]
