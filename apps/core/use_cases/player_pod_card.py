from django.db.models import Count, F

from apps.core.models import Deck, Game, Player
from apps.core.use_cases.base import BaseUseCase
from apps.core.use_cases.player_stats import favorite_color_combo, favorite_wincon
from apps.core.use_cases.pod_insights import POINTS_BY_PLACEMENT


def _points(performances):
    return sum(POINTS_BY_PLACEMENT.get(p.placement, 0) for p in performances)


class PlayerPodCardUseCase(BaseUseCase):
    """
    Números do card "Você no pod" do dashboard: performance do jogador e a
    zona de conforto dele. Sempre o histórico todo do jogador no pod (ignora
    o filtro 7/30 dias do dashboard).
    """

    def perform_request(self, player):
        performances = list(
            player.match_performances.select_related("game", "deck").order_by(
                F("game__date").desc(nulls_last=True), "-game__id"
            )
        )
        games = len(performances)
        wins = sum(1 for p in performances if p.placement == 1)

        return {
            "games": games,
            "wins": wins,
            "win_rate": round(wins / games * 100, 1) if games else 0,
            "points": _points(performances),
            "points_rank": self._points_rank(player),
            "streak": self._streak(performances),
            "first_bloods": Game.objects.filter(first_blood_player=player).count(),
            "comfort_deck": self._comfort_deck(player, games),
            "favorite_color_combo": favorite_color_combo(player),
            "favorite_wincon": favorite_wincon(player.match_performances.all()),
        }

    def _points_rank(self, player):
        """Posição no ranking de pontos do pod, em formato competição (1, 2, 2, 4)."""
        mine = None
        all_points = []
        for other in Player.objects.filter(pod_id=player.pod_id):
            points = _points(other.match_performances.all())
            all_points.append(points)
            if other.pk == player.pk:
                mine = points
        return 1 + sum(1 for points in all_points if points > mine)

    def _streak(self, performances):
        """Partidas da mais recente para a mais antiga (sem data por último)."""
        if not performances:
            return None
        if performances[0].placement == 1:
            count = 0
            for p in performances:
                if p.placement != 1:
                    break
                count += 1
            return {"kind": "wins", "count": count}
        count = 0
        for p in performances:
            if p.placement == 1:
                break
            count += 1
        return {"kind": "winless", "count": count}

    def _comfort_deck(self, player, games):
        top = (
            player.match_performances.exclude(deck__isnull=True)
            .values("deck")
            .annotate(games=Count("id"))
            .order_by("-games", "deck")
            .first()
        )
        if not top or not games:
            return None
        # O deck pode ser de outro jogador (partida registrada pelo admin com
        # deck emprestado): busca pelo id, não só entre os decks do jogador.
        deck = Deck.objects.prefetch_related("commanders").filter(pk=top["deck"]).first()
        if deck is None:
            return None
        return {
            "deck": deck,
            "games": top["games"],
            "share": round(top["games"] / games * 100, 1),
        }
