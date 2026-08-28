from django.views.generic import TemplateView
from apps.core.use_cases import get_dashboard_stats


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_dashboard_stats())
        return context
