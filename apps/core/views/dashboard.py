from django.db.models import Count, Q
from django.views.generic import TemplateView
from apps.core.models import Achievement, Deck, Game, GameParticipant, Player


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        total_games = Game.objects.count()
        total_decks = Deck.objects.filter(is_active=True).count()

        # Ranking dos Jogadores (usando 'match_performances')
        players = Player.objects.annotate(
            total_games=Count("match_performances"),
            wins=Count(
                "match_performances",
                filter=Q(match_performances__placement=1),
            ),
        ).order_by("-wins", "-total_games")

        ranked_players = []
        for player in players:
            wr = (
                round((player.wins / player.total_games * 100), 1)
                if player.total_games > 0
                else 0
            )
            ranked_players.append(
                {
                    "name": player.name,
                    "wins": player.wins,
                    "total_games": player.total_games,
                    "win_rate": wr,
                }
            )

        top_player = ranked_players[0] if ranked_players else None

        # Wincon Modes
        wincon_counts = (
            Game.objects.values("win_condition")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        wincon_modes = []
        for wc in wincon_counts:
            pct = round((wc["count"] / total_games * 100), 1) if total_games > 0 else 0
            wincon_modes.append(
                {
                    "name": wc["win_condition"],
                    "count": wc["count"],
                    "percentage": pct,
                }
            )

        top_wincon = wincon_modes[0] if wincon_modes else None

        # Carta MVP
        top_mvp_query = (
            GameParticipant.objects.filter(mvp_card__isnull=False)
            .values("mvp_card__name")
            .annotate(count=Count("id"))
            .order_by("-count")
            .first()
        )

        top_mvp = {"name": top_mvp_query["mvp_card__name"]} if top_mvp_query else None

        # Achievements
        achievements = Achievement.objects.select_related("player").order_by(
            "-date", "-id"
        )[:5]

        context.update(
            {
                "total_games": total_games,
                "total_decks": total_decks,
                "top_player": top_player,
                "top_wincon": top_wincon,
                "top_mvp": top_mvp,
                "ranked_players": ranked_players,
                "wincon_modes": wincon_modes,
                "achievements": achievements,
            }
        )

        return context
