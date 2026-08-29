from django.views.generic import DetailView
from apps.cards.use_cases import EnsureCardImageUseCase
from apps.core.models import Player
from apps.core.use_cases import PlayerProfileUseCase
from apps.pods.mixins import PodMemberRequiredMixin


class PlayerProfileView(PodMemberRequiredMixin, DetailView):
    model = Player
    template_name = "core/player_profile.html"
    context_object_name = "player"

    def get_queryset(self):
        return Player.objects.filter(pod=self.pod)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(PlayerProfileUseCase().execute(self.object))

        image_use_case = EnsureCardImageUseCase()
        for row in context["commander_stats"]:
            row["commander_images"] = [
                (card, image_use_case.execute(card))
                for card in row["deck"].commanders.all()
            ]

        return context
