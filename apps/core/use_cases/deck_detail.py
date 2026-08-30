from django.db.models import Count

from apps.core.models import Deck, Game, GameParticipant, wincon_label
from apps.core.use_cases.base import BaseUseCase


class DeckDetailUseCase(BaseUseCase):
    def perform_request(self, deck: Deck) -> dict:
        performances = GameParticipant.objects.filter(deck=deck).select_related(
            "game", "player"
        )

        total_games = performances.count()
        wins = performances.filter(placement=1).count()
        win_rate = round((wins / total_games * 100), 1) if total_games else 0

        losses = performances.exclude(placement=1)
        salty_count = losses.filter(felt_salty=True).count()
        salt_percentage = (
            round((salty_count / losses.count() * 100), 1) if losses.count() else 0
        )

        fun_ratings = list(
            performances.exclude(fun_rating__isnull=True).values_list(
                "fun_rating", flat=True
            )
        )
        avg_fun_rating = (
            round(sum(fun_ratings) / len(fun_ratings), 1) if fun_ratings else None
        )

        matchups = self._matchups(deck, performances)

        recent_games = (
            Game.objects.filter(participants__deck=deck)
            .distinct()
            .order_by("-date", "-id")[:10]
        )

        return {
            "total_games": total_games,
            "wins": wins,
            "win_rate": win_rate,
            "wincon_breakdown": self._wincon_breakdown(performances),
            "matchups": matchups,
            "arch_enemy": matchups[0] if matchups else None,
            "salt_percentage": salt_percentage,
            "avg_fun_rating": avg_fun_rating,
            "recent_games": recent_games,
        }

    def _wincon_breakdown(self, performances):
        game_ids = performances.filter(placement=1).values_list("game_id", flat=True)
        counts = (
            Game.objects.filter(id__in=game_ids)
            .values("win_condition")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        total = sum(row["count"] for row in counts)
        breakdown = []
        for row in counts:
            pct = round((row["count"] / total * 100), 1) if total else 0
            breakdown.append(
                {
                    "name": wincon_label(row["win_condition"]),
                    "count": row["count"],
                    "percentage": pct,
                }
            )
        return breakdown

    def _matchups(self, deck, performances):
        game_ids = list(performances.values_list("game_id", flat=True))
        opponents = (
            GameParticipant.objects.filter(game_id__in=game_ids)
            .exclude(deck=deck)
            .exclude(deck__isnull=True)
            .select_related("deck")
        )

        stats = {}
        for opponent in opponents:
            key = opponent.deck_id
            if key not in stats:
                stats[key] = {"deck": opponent.deck, "games": 0, "opponent_wins": 0}
            stats[key]["games"] += 1
            if opponent.placement == 1:
                stats[key]["opponent_wins"] += 1

        matchups = []
        for row in stats.values():
            opponent_win_rate = round((row["opponent_wins"] / row["games"] * 100), 1)
            matchups.append(
                {
                    "deck": row["deck"],
                    "games": row["games"],
                    "opponent_wins": row["opponent_wins"],
                    "opponent_win_rate": opponent_win_rate,
                }
            )
        matchups.sort(key=lambda row: row["opponent_win_rate"], reverse=True)
        return matchups
