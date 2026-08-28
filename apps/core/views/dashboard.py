from django.views.generic import TemplateView
from apps.core.models import Card
from apps.core.use_cases import (
    DashboardStatsUseCase,
    EnsureCardImageUseCase,
    PodInsightsUseCase,
)


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(DashboardStatsUseCase().execute())
        context.update(PodInsightsUseCase().execute())

        top_mvp = context.get("top_mvp")
        if top_mvp:
            card = Card.objects.filter(pk=top_mvp["id"]).first()
            top_mvp["image_url"] = (
                EnsureCardImageUseCase().execute(card) if card else None
            )

        return context
