from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView
from apps.cards.models import Card
from apps.cards.use_cases import EnsureCardImageUseCase
from apps.core.models import Player
from apps.core.use_cases import (
    DashboardStatsUseCase,
    EnsureWeeklyThemeUseCase,
    PlayerPodCardUseCase,
    PodInsightsUseCase,
)
from apps.pods.mixins import PodMemberRequiredMixin

WINDOW_DAYS = {"7": 7, "30": 30}


class DashboardView(PodMemberRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        window = self.request.GET.get("days")
        days = WINDOW_DAYS.get(window)
        since = timezone.now().date() - timedelta(days=days) if days else None

        context.update(DashboardStatsUseCase().execute(self.pod, since=since))
        context.update(PodInsightsUseCase().execute(self.pod, since=since))
        context["active_window"] = window if window in WINDOW_DAYS else ""

        top_mvp = context.get("top_mvp")
        if top_mvp:
            card = Card.objects.filter(pk=top_mvp["id"]).first()
            top_mvp["image_url"] = (
                EnsureCardImageUseCase().execute(card) if card else None
            )

        context.update(self._player_card_context())
        return context

    def _player_card_context(self):
        """Card "Você no pod": só existe para quem tem um Player neste pod."""
        player = Player.objects.filter(pod=self.pod, user=self.request.user).first()
        if player is None:
            return {"player_card": None, "weekly_theme": None}
        weekly_theme = EnsureWeeklyThemeUseCase().execute(player)
        return {
            "player_card": PlayerPodCardUseCase().execute(player),
            "weekly_theme": weekly_theme,
            "weekly_theme_summary_url": reverse(
                "core:weekly-theme-summary", kwargs={"pod_slug": self.pod.slug}
            ),
        }
