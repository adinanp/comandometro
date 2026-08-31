from django.views.generic import ListView
from apps.core.models import Game, wincon_label
from apps.pods.mixins import PodMemberRequiredMixin


class GameListView(PodMemberRequiredMixin, ListView):
    """
    Lista de partidas do pod — aceita `?wincon=<valor>` e `?seat=<n>` como
    filtros opcionais (vêm dos links de "deep dive" do dashboard, ex:
    clicar numa linha de TOP 5 WINCONS ou de WIN RATE POR POSIÇÃO NA MESA).
    """

    model = Game
    template_name = "core/game_list.html"
    context_object_name = "games"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Game.objects.filter(pod=self.pod)
            .prefetch_related("participants__player")
            .order_by("-date", "-id")
        )
        wincon = self.request.GET.get("wincon")
        if wincon:
            qs = qs.filter(win_condition=wincon)
        seat = self.request.GET.get("seat")
        if seat:
            qs = qs.filter(participants__starting_seat=seat).distinct()
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wincon = self.request.GET.get("wincon")
        seat = self.request.GET.get("seat")
        context["active_wincon"] = wincon
        context["active_wincon_label"] = wincon_label(wincon) if wincon else None
        context["active_seat"] = seat
        return context
