from django.db.models import Count
from apps.core.models import Achievement, Deck, Game, GameParticipant, Player
from apps.shared.use_cases import BaseUseCase


class DashboardStatsUseCase(BaseUseCase):
    def perform_request(self, since=None) -> dict:
        games = Game.objects.all()
        achievements_qs = Achievement.objects.select_related("player")
        participants = GameParticipant.objects.all()
        if since:
            games = games.filter(date__gte=since)
            achievements_qs = achievements_qs.filter(date__gte=since)
            participants = participants.filter(game__date__gte=since)

        total_games = games.count()
        total_decks = Deck.objects.filter(is_active=True).count()

        ranked_players = []
        for player in Player.objects.all():
            performances = player.match_performances.all()
            if since:
                performances = performances.filter(game__date__gte=since)
            total = performances.count()
            wins = performances.filter(placement=1).count()
            wr = round((wins / total * 100), 1) if total else 0
            ranked_players.append(
                {
                    "id": player.id,
                    "name": player.name,
                    "wins": wins,
                    "total_games": total,
                    "win_rate": wr,
                }
            )
        ranked_players.sort(key=lambda p: (-p["wins"], -p["total_games"]))

        top_player = (
            ranked_players[0]
            if ranked_players and ranked_players[0]["total_games"]
            else None
        )

        wincon_counts = (
            games.values("win_condition").annotate(count=Count("id")).order_by("-count")
        )

        wincon_modes = []
        for wc in wincon_counts:
            pct = round((wc["count"] / total_games * 100), 1) if total_games > 0 else 0
            wincon_modes.append(
                {"name": wc["win_condition"], "count": wc["count"], "percentage": pct}
            )

        top_wincon = wincon_modes[0] if wincon_modes else None

        top_mvp_query = (
            participants.filter(mvp_card__isnull=False)
            .values("mvp_card", "mvp_card__name")
            .annotate(count=Count("id"))
            .order_by("-count")
            .first()
        )
        top_mvp = (
            {"id": top_mvp_query["mvp_card"], "name": top_mvp_query["mvp_card__name"]}
            if top_mvp_query
            else None
        )

        achievements = achievements_qs.order_by("-date", "-id")[:5]

        return {
            "total_games": total_games,
            "total_decks": total_decks,
            "top_player": top_player,
            "top_wincon": top_wincon,
            "top_mvp": top_mvp,
            "ranked_players": ranked_players,
            "wincon_modes": wincon_modes,
            "achievements": achievements,
        }
