from django.urls import reverse
from django.views.generic import DetailView

from apps.core.models import ThemeDraw
from apps.pods.mixins import PodMemberRequiredMixin


class ThemeDrawDetailView(PodMemberRequiredMixin, DetailView):
    template_name = "core/theme_draw_detail.html"
    context_object_name = "draw"

    def get_queryset(self):
        return ThemeDraw.objects.filter(pod=self.pod).prefetch_related(
            "seats__player", "seats__theme"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cards = []
        for seat in self.object.seats.all():
            theme = seat.theme
            cards.append(
                {
                    "player": seat.player,
                    "theme": theme,
                    "commanders": theme.top_commander_names(),
                    "summary_url": None
                    if theme.summary
                    else reverse(
                        "core:theme-summary",
                        kwargs={
                            "pod_slug": self.pod.slug,
                            "pk": self.object.pk,
                            "theme_id": theme.pk,
                        },
                    ),
                }
            )
        context["cards"] = cards
        return context
