from django.views.generic import DetailView
from apps.core.models import Game
from apps.core.use_cases import EnsureCardImageUseCase, GameDetailUseCase


class GameDetailView(DetailView):
    model = Game
    template_name = "core/game_detail.html"
    context_object_name = "game"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = GameDetailUseCase().execute(self.object)
        image_use_case = EnsureCardImageUseCase()

        rows = []
        for participant in data["participants"]:
            commander_images = (
                [
                    (card, image_use_case.execute(card))
                    for card in participant.deck.commanders.all()
                ]
                if participant.deck
                else []
            )
            mvp_image_url = (
                image_use_case.execute(participant.mvp_card)
                if participant.mvp_card
                else None
            )
            rows.append(
                {
                    "participant": participant,
                    "commander_images": commander_images,
                    "mvp_image_url": mvp_image_url,
                }
            )

        context["rows"] = rows
        return context
