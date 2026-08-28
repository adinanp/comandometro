from django.views.generic import TemplateView
from apps.core.use_cases import DashboardStatsUseCase


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(DashboardStatsUseCase().execute())
        return context
