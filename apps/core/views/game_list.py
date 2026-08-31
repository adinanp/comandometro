from django.views.generic import ListView
from apps.core.models import Game, Player, wincon_label
from apps.pods.mixins import PodMemberRequiredMixin


class GameListView(PodMemberRequiredMixin, ListView):
    """
    Lista de partidas do pod — aceita `?wincon=<valor>`, `?seat=<n>` e
    `?player=<id>` (com `&won=1` opcional) como filtros, vindos dos links
    de "deep dive" do dashboard e do perfil do jogador.
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
        player_id = self.request.GET.get("player")
        if player_id:
            if self.request.GET.get("won"):
                qs = qs.filter(participants__player_id=player_id, participants__placement=1)
            else:
                qs = qs.filter(participants__player_id=player_id)
            qs = qs.distinct()
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wincon = self.request.GET.get("wincon")
        seat = self.request.GET.get("seat")
        player_id = self.request.GET.get("player")
        won = self.request.GET.get("won")
        context["active_wincon"] = wincon
        context["active_wincon_label"] = wincon_label(wincon) if wincon else None
        context["active_seat"] = seat
        context["active_player"] = (
            Player.objects.filter(pk=player_id, pod=self.pod).first() if player_id else None
        )
        context["active_won"] = won
        return context
