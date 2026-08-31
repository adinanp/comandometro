from django.views.generic import ListView
from apps.core.models import Deck
from apps.pods.mixins import PodMemberRequiredMixin


class DeckListView(PodMemberRequiredMixin, ListView):
    """
    Lista de decks do pod — aceita `?color_identity=<combo>` (ex: "WUR",
    "C") como filtro opcional, usado pelo "deep dive" de TOP 5 WIN RATE
    POR COLOR IDENTITY no dashboard.
    """

    model = Deck
    template_name = "core/deck_list.html"
    context_object_name = "decks"

    def get_queryset(self):
        qs = (
            Deck.objects.filter(player__pod=self.pod)
            .select_related("player")
            .prefetch_related("commanders")
        )
        identity = self.request.GET.get("color_identity")
        if identity:
            qs = qs.filter(color_identity=identity)
        return qs.order_by("player__name", "-is_active")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_color_identity"] = self.request.GET.get("color_identity")
        return context
