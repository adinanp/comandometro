from datetime import timedelta

from django.utils import timezone
from django.views.generic import TemplateView
from apps.core.models import Card
from apps.core.use_cases import (
    DashboardStatsUseCase,
    EnsureCardImageUseCase,
    PodInsightsUseCase,
)

WINDOW_DAYS = {"7": 7, "30": 30}


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        window = self.request.GET.get("days")
        days = WINDOW_DAYS.get(window)
        since = timezone.now().date() - timedelta(days=days) if days else None

        context.update(DashboardStatsUseCase().execute(since=since))
        context.update(PodInsightsUseCase().execute(since=since))
        context["active_window"] = window if window in WINDOW_DAYS else ""

        top_mvp = context.get("top_mvp")
        if top_mvp:
            card = Card.objects.filter(pk=top_mvp["id"]).first()
            top_mvp["image_url"] = (
                EnsureCardImageUseCase().execute(card) if card else None
            )

        return context
