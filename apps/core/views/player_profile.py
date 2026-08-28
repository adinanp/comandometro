from django.views.generic import DetailView
from apps.core.models import Player
from apps.core.use_cases import PlayerProfileUseCase


class PlayerProfileView(DetailView):
    model = Player
    template_name = "core/player_profile.html"
    context_object_name = "player"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(PlayerProfileUseCase().execute(self.object))
        return context
