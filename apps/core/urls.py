from django.urls import path
from apps.core.views import DashboardView, PlayerProfileView

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("players/<int:pk>/", PlayerProfileView.as_view(), name="player-profile"),
]
