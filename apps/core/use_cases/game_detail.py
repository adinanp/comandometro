from apps.core.models import Game
from apps.core.use_cases.base import BaseUseCase


class GameDetailUseCase(BaseUseCase):
    def perform_request(self, game: Game) -> dict:
        participants = (
            game.participants.select_related("player", "deck", "mvp_card")
            .prefetch_related("deck__commanders")
            .order_by("placement")
        )
        achievements = game.achievements.select_related("player").order_by("id")
        return {"participants": list(participants), "achievements": list(achievements)}
