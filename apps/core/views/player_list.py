from django.views.generic import ListView
from apps.core.models import Player


class PlayerListView(ListView):
    model = Player
    template_name = "core/player_list.html"
    context_object_name = "players"

    def get_queryset(self):
        return Player.objects.order_by("name")
