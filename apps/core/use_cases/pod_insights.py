from django.db.models import Count, Q
from django.db.models.functions import TruncMonth

from apps.core.models import Deck, Game, GameParticipant, Player
from apps.shared.use_cases import BaseUseCase

POINTS_BY_PLACEMENT = {1: 4, 2: 2, 3: 1}


class PodInsightsUseCase(BaseUseCase):
    def perform_request(self) -> dict:
        return {
            "color_identity_stats": self._color_identity_stats(),
            "color_count_stats": self._color_count_stats(),
            "wincon_trend": self._wincon_trend(),
            "points_ranking": self._points_ranking(),
            "top_commanders_qualified": self._top_commanders_qualified(),
            "records": self._records(),
        }

    def _color_identity_stats(self):
        stats = []
        for color in "WUBRG":
            decks_with_color = Deck.objects.filter(color_identity__contains=color)
            performances = GameParticipant.objects.filter(deck__in=decks_with_color)
            games = performances.count()
            wins = performances.filter(placement=1).count()
            win_rate = round((wins / games * 100), 1) if games else 0
            stats.append(
                {"color": color, "games": games, "wins": wins, "win_rate": win_rate}
            )
        return stats

    def _color_count_stats(self):
        decks = Deck.objects.annotate(
            games=Count("match_performances"),
            wins=Count(
                "match_performances", filter=Q(match_performances__placement=1)
            ),
        )
        buckets = {n: {"games": 0, "wins": 0} for n in range(6)}
        for deck in decks:
            num_colors = (
                0 if deck.color_identity in ("", "C") else len(deck.color_identity)
            )
            buckets[num_colors]["games"] += deck.games
            buckets[num_colors]["wins"] += deck.wins

        stats = []
        for num_colors, totals in sorted(buckets.items()):
            games = totals["games"]
            wins = totals["wins"]
            win_rate = round((wins / games * 100), 1) if games else 0
            stats.append(
                {
                    "colors": num_colors,
                    "games": games,
                    "wins": wins,
                    "win_rate": win_rate,
                }
            )
        return stats

    def _wincon_trend(self):
        trend = (
            Game.objects.exclude(date__isnull=True)
            .annotate(month=TruncMonth("date"))
            .values("month", "win_condition")
            .annotate(count=Count("id"))
            .order_by("month", "win_condition")
        )
        return list(trend)

    def _points_ranking(self):
        ranking = []
        for player in Player.objects.all():
            performances = player.match_performances.all()
            points = sum(
                POINTS_BY_PLACEMENT.get(p.placement, 0) for p in performances
            )
            ranking.append({"player": player, "points": points})
        ranking.sort(key=lambda row: row["points"], reverse=True)
        return ranking

    def _top_commanders_qualified(self):
        decks = Deck.objects.annotate(
            games=Count("match_performances"),
            wins=Count(
                "match_performances", filter=Q(match_performances__placement=1)
            ),
        ).filter(games__gte=5)

        qualified = []
        for deck in decks:
            win_rate = round((deck.wins / deck.games * 100), 1) if deck.games else 0
            if win_rate >= 20:
                qualified.append(
                    {
                        "deck": deck,
                        "games": deck.games,
                        "wins": deck.wins,
                        "win_rate": win_rate,
                    }
                )
        qualified.sort(key=lambda row: row["win_rate"], reverse=True)
        return qualified

    def _records(self):
        def top_by(field):
            obj = (
                GameParticipant.objects.select_related("player", "game")
                .order_by(f"-{field}")
                .first()
            )
            return obj if obj and getattr(obj, field) > 0 else None

        most_life = (
            GameParticipant.objects.select_related("player", "game")
            .exclude(peak_life_total__isnull=True)
            .order_by("-peak_life_total")
            .first()
        )
        biggest_creature = (
            GameParticipant.objects.select_related("player", "game", "biggest_creature")
            .exclude(biggest_creature__isnull=True)
            .order_by("-biggest_creature_power")
            .first()
        )
        fastest_game_no_combo = (
            Game.objects.exclude(win_condition="combo")
            .exclude(turn_count__isnull=True)
            .order_by("turn_count")
            .first()
        )
        fastest_game_combo = (
            Game.objects.filter(win_condition="combo")
            .exclude(turn_count__isnull=True)
            .order_by("turn_count")
            .first()
        )

        return {
            "board_wipes": top_by("board_wipes_count"),
            "counterspells": top_by("counterspell_count"),
            "complaints": top_by("complaint_count"),
            "most_life": most_life,
            "biggest_creature": biggest_creature,
            "self_eliminations_count": GameParticipant.objects.filter(
                is_self_elimination=True
            ).count(),
            "fastest_game_no_combo": fastest_game_no_combo,
            "fastest_game_combo": fastest_game_combo,
        }
