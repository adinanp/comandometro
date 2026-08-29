from django.urls import path
from apps.core.views import (
    DashboardView,
    DeckCreateAjaxView,
    DeckCreateView,
    DeckDetailView,
    GameCreateView,
    GameDetailView,
    GameListView,
    MyProfileRedirectView,
    PlayerCreateView,
    PlayerListView,
    PlayerProfileView,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("meu-perfil/", MyProfileRedirectView.as_view(), name="my-profile"),
    path("jogadores/", PlayerListView.as_view(), name="player-list"),
    path("jogadores/novo/", PlayerCreateView.as_view(), name="player-create"),
    path("jogadores/<int:pk>/", PlayerProfileView.as_view(), name="player-profile"),
    path("partidas/", GameListView.as_view(), name="game-list"),
    path("partidas/nova/", GameCreateView.as_view(), name="game-create"),
    path("partidas/<int:pk>/", GameDetailView.as_view(), name="game-detail"),
    path("decks/novo/", DeckCreateView.as_view(), name="deck-create"),
    path("decks/novo/ajax/", DeckCreateAjaxView.as_view(), name="deck-create-ajax"),
    path("decks/<int:pk>/", DeckDetailView.as_view(), name="deck-detail"),
]
