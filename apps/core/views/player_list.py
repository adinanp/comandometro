from django.views.generic import ListView
from apps.core.models import Player
from apps.pods.mixins import PodMemberRequiredMixin


class PlayerListView(PodMemberRequiredMixin, ListView):
    model = Player
    template_name = "core/player_list.html"
    context_object_name = "players"

    def get_queryset(self):
        return Player.objects.filter(pod=self.pod).order_by("name")
