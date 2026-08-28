from django.urls import path
from apps.core.views import DashboardView, GameDetailView, GameListView, PlayerProfileView

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("players/<int:pk>/", PlayerProfileView.as_view(), name="player-profile"),
    path("games/", GameListView.as_view(), name="game-list"),
    path("games/<int:pk>/", GameDetailView.as_view(), name="game-detail"),
]
