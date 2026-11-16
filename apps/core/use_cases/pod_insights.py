from django.db.models import Case, Count, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.db.models.functions import TruncMonth

from apps.core.models import Deck, Game, GameParticipant, Player, wincon_label
from apps.core.use_cases.base import BaseUseCase

POINTS_BY_PLACEMENT = {1: 4, 2: 2, 3: 1}


MIN_COMMANDER_GAMES = 5


class PodInsightsUseCase(BaseUseCase):
    def perform_request(self, pod, since=None) -> dict:
        return {
            "color_identity_stats": self._color_identity_combo_stats(pod, since),
            "wincon_trend": self._wincon_trend(pod, since),
            "points_ranking": self._points_ranking(pod, since),
            "top_commanders": self._top_commanders(pod, since),
            "seat_stats": self._seat_stats(pod, since),
        }

    def _color_identity_combo_stats(self, pod, since):
        """
        Top 5 win rate agrupado pela combinação exata de cores do deck (ex:
        "WUR", "UBG"), não por cor isolada — cada participação cai em um
        único grupo, então um deck de 5 cores não infla 5 contadores ao
        mesmo tempo. Mono-color (ex: "W" sozinho) e colorless ("C") também
        são combinações válidas aqui, não um caso à parte.
        """
        buckets = {}
        for deck in self._decks_with_totals(pod, since):
            games, wins = deck.games_count, deck.wins_count
            if games == 0:
                continue
            identity = deck.color_identity or "C"
            bucket = buckets.setdefault(identity, {"games": 0, "wins": 0})
            bucket["games"] += games
            bucket["wins"] += wins

        stats = []
        for identity, totals in buckets.items():
            win_rate = round((totals["wins"] / totals["games"] * 100), 1)
            stats.append(
                {
                    "identity": identity,
                    "games": totals["games"],
                    "wins": totals["wins"],
                    "win_rate": win_rate,
                }
            )
        stats.sort(key=lambda row: (-row["win_rate"], -row["games"]))
        return self._pad(stats[:5], 5)

    def _decks_with_totals(self, pod, since):
        """
        Decks do pod com partidas e vitórias já contadas pelo banco, numa
        query só. O banco fica em outra nuvem (app no App Engine, Postgres no
        Neon/AWS), então contar por deck custava 2 queries de ~30ms cada.
        """
        played = Q()
        if since:
            played = Q(match_performances__game__date__gte=since)
        return Deck.objects.filter(player__pod=pod).select_related("player").annotate(
            games_count=Count("match_performances", filter=played),
            wins_count=Count(
                "match_performances",
                filter=played & Q(match_performances__placement=1),
            ),
        )

    def _pad(self, rows, size):
        """Completa com linhas vazias (`{"empty": True}`) até `size` — ver
        DashboardStatsUseCase._pad, mesmo padrão de altura fixa nos TOP 5."""
        return rows + [{"empty": True}] * (size - len(rows))

    def _wincon_trend(self, pod, since):
        games = Game.objects.filter(pod=pod).exclude(date__isnull=True)
        if since:
            games = games.filter(date__gte=since)
        trend = (
            games.annotate(month=TruncMonth("date"))
            .values("month", "win_condition")
            .annotate(count=Count("id"))
            .order_by("month", "win_condition")
        )
        rows = list(trend)
        for row in rows:
            row["win_condition"] = wincon_label(row["win_condition"])
        return rows

    def _points_ranking(self, pod, since):
        placement_points = Case(
            *(
                When(match_performances__placement=placement, then=Value(points))
                for placement, points in POINTS_BY_PLACEMENT.items()
            ),
            default=Value(0),
            output_field=IntegerField(),
        )
        played = Q()
        if since:
            played = Q(match_performances__game__date__gte=since)
        players = Player.objects.filter(pod=pod).annotate(
            points=Coalesce(Sum(placement_points, filter=played), Value(0))
        )
        ranking = [{"player": player, "points": player.points} for player in players]
        ranking.sort(key=lambda row: row["points"], reverse=True)
        return ranking

    def _top_commanders(self, pod, since):
        """
        Top 5 comandantes por win rate, só entram decks com >=
        MIN_COMMANDER_GAMES aparições (desempate: mais aparições). O corte
        evita que um deck jogado 1 vez com 100% WR pareça "o melhor do pod".
        """
        rows = []
        for deck in self._decks_with_totals(pod, since):
            games, wins = deck.games_count, deck.wins_count
            if games < MIN_COMMANDER_GAMES:
                continue
            win_rate = round((wins / games * 100), 1)
            rows.append(
                {
                    "deck": deck,
                    "player": deck.player,
                    "games": games,
                    "wins": wins,
                    "win_rate": win_rate,
                }
            )
        rows.sort(key=lambda row: (-row["win_rate"], -row["games"]))
        return self._pad(rows[:5], 5)

    def _seat_stats(self, pod, since):
        performances = GameParticipant.objects.filter(game__pod=pod).exclude(
            starting_seat__isnull=True
        )
        if since:
            performances = performances.filter(game__date__gte=since)

        buckets = {}
        for performance in performances:
            seat = performance.starting_seat
            buckets.setdefault(seat, {"games": 0, "wins": 0})
            buckets[seat]["games"] += 1
            if performance.placement == 1:
                buckets[seat]["wins"] += 1

        stats = []
        for seat, totals in sorted(buckets.items()):
            win_rate = round((totals["wins"] / totals["games"] * 100), 1)
            stats.append(
                {
                    "seat": seat,
                    "games": totals["games"],
                    "wins": totals["wins"],
                    "win_rate": win_rate,
                }
            )
        return stats

