from django.views.generic import ListView
from apps.core.models import Game


class GameListView(ListView):
    model = Game
    template_name = "core/game_list.html"
    context_object_name = "games"
    paginate_by = 20

    def get_queryset(self):
        return Game.objects.prefetch_related("participants__player").order_by(
            "-date", "-id"
        )
