from django.urls import path
from apps.core.views import (
    DashboardView,
    DeckDetailView,
    GameDetailView,
    GameListView,
    PlayerListView,
    PlayerProfileView,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("players/", PlayerListView.as_view(), name="player-list"),
    path("players/<int:pk>/", PlayerProfileView.as_view(), name="player-profile"),
    path("games/", GameListView.as_view(), name="game-list"),
    path("games/<int:pk>/", GameDetailView.as_view(), name="game-detail"),
    path("decks/<int:pk>/", DeckDetailView.as_view(), name="deck-detail"),
]
