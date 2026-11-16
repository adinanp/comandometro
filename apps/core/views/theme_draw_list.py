from django.views.generic import ListView

from apps.core.models import ThemeDraw
from apps.pods.mixins import PodMemberRequiredMixin


class ThemeDrawListView(PodMemberRequiredMixin, ListView):
    """Histórico dos sorteios de temas do pod, do mais recente para o mais antigo."""

    template_name = "core/theme_draw_list.html"
    context_object_name = "draws"
    paginate_by = 20

    def get_queryset(self):
        return (
            ThemeDraw.objects.filter(pod=self.pod)
            .prefetch_related("seats__player", "seats__theme")
            .order_by("-created_at", "-id")
        )
