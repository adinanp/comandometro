from django.db.models import Count, Q

from apps.core.models import Deck, Player
from apps.core.use_cases.pod_insights import POINTS_BY_PLACEMENT
from apps.shared.use_cases import BaseUseCase


class PlayerProfileUseCase(BaseUseCase):
    def perform_request(self, player: Player) -> dict:
        performances = player.match_performances.select_related(
            "game", "deck", "biggest_creature"
        )

        total_games = performances.count()
        wins = performances.filter(placement=1).count()
        win_rate = round((wins / total_games * 100), 1) if total_games else 0
        points = sum(POINTS_BY_PLACEMENT.get(p.placement, 0) for p in performances)

        decks = (
            Deck.objects.filter(player=player)
            .prefetch_related("commanders")
            .annotate(
                deck_games=Count("match_performances"),
                deck_wins=Count(
                    "match_performances",
                    filter=Q(match_performances__placement=1),
                ),
            )
        )
        commander_stats = []
        for deck in decks:
            deck_win_rate = (
                round((deck.deck_wins / deck.deck_games * 100), 1)
                if deck.deck_games
                else 0
            )
            commander_stats.append(
                {
                    "deck": deck,
                    "games": deck.deck_games,
                    "wins": deck.deck_wins,
                    "win_rate": deck_win_rate,
                }
            )

        def top_by(field):
            obj = performances.order_by(f"-{field}").first()
            return obj if obj and getattr(obj, field) > 0 else None

        records = {
            "board_wipes": top_by("board_wipes_count"),
            "counterspells": top_by("counterspell_count"),
            "complaints": top_by("complaint_count"),
            "most_life": performances.exclude(peak_life_total__isnull=True)
            .order_by("-peak_life_total")
            .first(),
            "biggest_creature": performances.exclude(biggest_creature__isnull=True)
            .order_by("-biggest_creature_power")
            .first(),
        }

        return {
            "total_games": total_games,
            "wins": wins,
            "win_rate": win_rate,
            "points": points,
            "commander_stats": commander_stats,
            "records": records,
        }
